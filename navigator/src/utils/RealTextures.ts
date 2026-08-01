import * as THREE from 'three';

/**
 * Map of available real PBR texture sets.
 * Each entry maps to files in public/textures/real/<name>_<map>.jpg
 */
const TEXTURE_SETS = ['grass', 'ground', 'wood', 'bricks'] as const;
type TextureSetName = (typeof TEXTURE_SETS)[number];

export interface PBRTextureSet {
  color: THREE.Texture;
  normal?: THREE.Texture;
  roughness?: THREE.Texture;
  ao?: THREE.Texture;
}

/**
 * Loader and cache for real PBR textures.
 */
export class RealTextures {

  private static loader = new THREE.TextureLoader();
  private static cache = new Map<string, PBRTextureSet>();

  /** Preload all available texture sets. Returns promise resolved when done. */
  static async preloadAll(): Promise<void> {
    const promises = TEXTURE_SETS.map(name => RealTextures.loadSet(name));
    await Promise.all(promises);
  }

  /** Load a single texture set (with caching) */
  static async loadSet(name: TextureSetName | string): Promise<PBRTextureSet> {
    const cached = RealTextures.cache.get(name);
    if (cached) return cached;

    const basePath = `/textures/real/${name}`;

    const loadTex = (suffix: string): Promise<THREE.Texture | undefined> => {
      const url = `${basePath}_${suffix}.jpg`;
      return new Promise((resolve) => {
        RealTextures.loader.load(
          url,
          (tex) => {
            tex.wrapS = THREE.RepeatWrapping;
            tex.wrapT = THREE.RepeatWrapping;
            tex.colorSpace = THREE.SRGBColorSpace;
            resolve(tex);
          },
          undefined,
          () => resolve(undefined), // On error, resolve undefined (texture not available)
        );
      });
    };

    const [color, normal, roughness, ao] = await Promise.all([
      loadTex('Color'),
      loadTex('NormalGL'),
      loadTex('Roughness'),
      loadTex('AmbientOcclusion'),
    ]);

    if (!color) throw new Error(`Failed to load base color for ${name}`);

    const set: PBRTextureSet = { color, normal, roughness, ao };
    RealTextures.cache.set(name, set);
    return set;
  }

  /** Synchronous get — returns from cache or undefined (call preloadAll first!) */
  static get(name: string): PBRTextureSet | undefined {
    return RealTextures.cache.get(name);
  }

  /** Create a MeshStandardMaterial using the PBR set (with fallback to procedural) */
  static createMaterial(
    name: string,
    colorFallback?: string,
    repeat?: [number, number],
  ): THREE.MeshStandardMaterial {
    const set = RealTextures.get(name);

    if (!set) {
      // Fallback: solid color or procedural
      return new THREE.MeshStandardMaterial({
        color: colorFallback ? new THREE.Color(colorFallback) : undefined,
        roughness: 0.8,
        metalness: 0.1,
      });
    }

    if (repeat) {
      set.color.repeat.set(repeat[0], repeat[1]);
      if (set.normal) set.normal.repeat.set(repeat[0], repeat[1]);
      if (set.roughness) set.roughness.repeat.set(repeat[0], repeat[1]);
      if (set.ao) set.ao.repeat.set(repeat[0], repeat[1]);
    }

    return new THREE.MeshStandardMaterial({
      map: set.color,
      normalMap: set.normal,
      roughnessMap: set.roughness,
      aoMap: set.ao,
      roughness: set.roughness ? 1.0 : 0.8,
      metalness: 0.05,
    });
  }
}

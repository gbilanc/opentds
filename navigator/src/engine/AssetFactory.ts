import * as THREE from 'three';
import { ProceduralTextures } from '../utils/ProceduralTextures.js';
import { RealTextures } from '../utils/RealTextures.js';
import type { WorldObject, TextureKind, PrimitiveKind } from '../world/WorldDescription.js';

/**
 * Create a flat octagonal IPSC target shape (like the classic cardboard target).
 * The shape is a polygon with: narrow head, angled shoulders, wide body.
 * s.x = total width, s.y = total height.
 */
function createIpscTargetShape(width: number, height: number): THREE.BufferGeometry {
  const hw = width / 2;
  const hh = height / 2;

  // Perfect regular octagon
  const shape = new THREE.Shape();
  const segments = 8;
  for (let i = 0; i < segments; i++) {
    const angle = (i / segments) * Math.PI * 2 - Math.PI / 2; // start from top
    const x = Math.cos(angle) * hw;
    const y = Math.sin(angle) * hh;
    if (i === 0) shape.moveTo(x, y);
    else shape.lineTo(x, y);
  }
  shape.closePath();

  const geo = new THREE.ExtrudeGeometry(shape, { depth: 0.005, bevelEnabled: false });
  geo.translate(0, -hh, -0.0025);
  return geo;
}

/**
 * Factory that creates Three.js meshes from world object descriptions.
 */
export class AssetFactory {

  private textureCache = new Map<string, THREE.Texture>();

  /** Create a single mesh from a WorldObject description */
  createMesh(obj: WorldObject): THREE.Mesh {
    const geometry = this.createGeometry(obj.kind, obj.scale);
    const material = this.createMaterial(obj);
    const mesh = new THREE.Mesh(geometry, material);

    mesh.position.set(obj.position.x, obj.position.y, obj.position.z);

    if (obj.rotation) {
      mesh.rotation.set(
        THREE.MathUtils.degToRad(obj.rotation.x),
        THREE.MathUtils.degToRad(obj.rotation.y),
        THREE.MathUtils.degToRad(obj.rotation.z),
      );
    }

    // Store metadata on userData
    mesh.userData = {
      id: obj.id,
      collision: obj.collision ?? false,
      interactable: obj.interactable ?? false,
      interactLabel: obj.interactLabel ?? obj.id,
    };

    mesh.castShadow = true;
    mesh.receiveShadow = true;

    return mesh;
  }

  private createGeometry(kind: PrimitiveKind, scale?: { x: number; y: number; z: number }): THREE.BufferGeometry {
    const s = scale ?? { x: 1, y: 1, z: 1 };

    switch (kind) {
      case 'box':
        return new THREE.BoxGeometry(s.x, s.y, s.z);
      case 'cylinder':
        // s.x = radius, s.y = height, s.z = radius (unused for uniform cylinder)
        return new THREE.CylinderGeometry(s.x, s.x, s.y, 16);
      case 'sphere':
        return new THREE.SphereGeometry(s.x, 24, 16);
      case 'cone':
        return new THREE.ConeGeometry(s.x, s.y, 12);
      case 'plane':
        return new THREE.PlaneGeometry(s.x, s.z);
      case 'octagon':
        // IPSC target shape: flat octagon, s.x = width (0.45m), s.y = height (0.75m)
        return createIpscTargetShape(s.x, s.y);
      default:
        return new THREE.BoxGeometry(1, 1, 1);
    }
  }

  private createMaterial(obj: WorldObject): THREE.Material {
    const texture = obj.texture ?? 'solid';

    // Real PBR textures (e.g. "real:grass", "real:wood")
    if (texture.startsWith('real:')) {
      const name = texture.slice(5); // strip "real:" prefix
      const repeat = obj.textureRepeat;
      return RealTextures.createMaterial(name, obj.color, repeat as [number, number] | undefined);
    }

    if (texture === 'solid') {
      const color = obj.color ?? '#808080';
      return new THREE.MeshStandardMaterial({
        color: new THREE.Color(color),
        flatShading: obj.flatShading ?? false,
      });
    }

    // Procedural texture (fallback)
    const tex = this.getProceduralTexture(texture as TextureKind);

    return new THREE.MeshStandardMaterial({
      map: tex,
      roughness: 0.8,
      metalness: 0.1,
      flatShading: obj.flatShading ?? false,
    });
  }

  private getProceduralTexture(kind: TextureKind): THREE.Texture {
    if (this.textureCache.has(kind)) {
      return this.textureCache.get(kind)!;
    }

    let texture: THREE.Texture;
    switch (kind) {
      case 'grass':  texture = ProceduralTextures.grass(); break;
      case 'wood':   texture = ProceduralTextures.wood(); break;
      case 'stone':  texture = ProceduralTextures.stone(); break;
      case 'dirt':   texture = ProceduralTextures.dirt(); break;
      case 'gravel': texture = ProceduralTextures.gravel(); break;
      case 'roof':   texture = ProceduralTextures.roof(); break;
      default:       texture = ProceduralTextures.grass(); break;
    }

    this.textureCache.set(kind, texture);
    return texture;
  }
}

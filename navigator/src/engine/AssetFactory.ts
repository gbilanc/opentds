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
  const hw = width / 2;   // half width (body)
  const hh = height / 2;  // half height
  const headW = hw * 0.33; // head is ~1/3 of body width
  const headH = hh * 0.4;  // head top portion

  const shape = new THREE.Shape();
  // Start at bottom-left
  shape.moveTo(-hw, -hh);
  // Bottom right
  shape.lineTo(hw, -hh);
  // Body right up to shoulder
  shape.lineTo(hw, -hh + hh * 0.8);
  // Shoulder angled cut (body → neck)
  shape.lineTo(headW, -hh + hh * 0.9);
  // Neck right
  shape.lineTo(headW, hh - headH * 0.6);
  // Head right top  
  shape.lineTo(headW * 0.6, hh);
  // Head top
  shape.lineTo(-headW * 0.6, hh);
  // Head left
  shape.lineTo(-headW, hh - headH * 0.6);
  // Neck left
  shape.lineTo(-headW, -hh + hh * 0.9);
  // Shoulder left
  shape.lineTo(-hw, -hh + hh * 0.8);
  shape.closePath();

  // Extrude with small depth so both sides are visible
  const geo = new THREE.ExtrudeGeometry(shape, { depth: 0.005, bevelEnabled: false });
  // Center the geometry vertically
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
      case 'roof':   texture = ProceduralTextures.roof(); break;
      default:       texture = ProceduralTextures.grass(); break;
    }

    this.textureCache.set(kind, texture);
    return texture;
  }
}

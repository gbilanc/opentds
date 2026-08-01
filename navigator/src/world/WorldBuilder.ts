import * as THREE from 'three';
import { AssetFactory } from '../engine/AssetFactory.js';
import { ProceduralTextures } from '../utils/ProceduralTextures.js';
import { RealTextures } from '../utils/RealTextures.js';
import type {
  WorldDescription,
  CompositeObject,
  WorldLight,
} from './WorldDescription.js';

export interface BuiltWorld {
  scene: THREE.Scene;
  collisionObjects: THREE.Object3D[];
  interactableObjects: THREE.Mesh[];
  groundHeight: number;
  spawnPosition: THREE.Vector3;
  /** Initial yaw in degrees (0 = look -Z, 90 = look -X) */
  playerYaw: number;
  /** Vertices of the shooting area polygon for player containment */
  shootingAreaPolygon?: Array<{x: number; z: number}>;
}

/**
 * Builds a complete Three.js scene from a WorldDescription.
 */
export class WorldBuilder {

  private factory = new AssetFactory();

  build(desc: WorldDescription): BuiltWorld {
    const scene = new THREE.Scene();
    const collisionObjects: THREE.Object3D[] = [];
    const interactableObjects: THREE.Mesh[] = [];

    // ── Sky & Fog ──────────────────────────────────────────
    scene.background = new THREE.Color(desc.skyColor);
    scene.fog = new THREE.FogExp2(
      desc.groundColor,
      desc.fogDensity ?? 0.015
    );

    // Hemisphere light (sky/ground) for natural outdoor lighting
    const hemiLight = new THREE.HemisphereLight(
      desc.skyColor,      // sky color (top)
      desc.groundColor,   // ground color (bottom)
      0.5,                // intensity
    );
    scene.add(hemiLight);

    // ── Ground ─────────────────────────────────────────────
    this.buildGround(scene, desc);

    // ── Objects ────────────────────────────────────────────
    for (const obj of desc.objects) {
      const mesh = this.factory.createMesh(obj);
      scene.add(mesh);

      if (obj.collision) {
        collisionObjects.push(mesh);
      }
      if (obj.interactable) {
        interactableObjects.push(mesh);
      }
    }

    // ── Composites ─────────────────────────────────────────
    for (const comp of desc.composites) {
      const group = this.buildComposite(comp);
      scene.add(group);

      if (comp.collision) {
        collisionObjects.push(group);
      }
      if (comp.interactable) {
        // Mark all child meshes as interactable
        group.traverse((child) => {
          if (child instanceof THREE.Mesh) {
            child.userData.interactable = true;
            child.userData.interactLabel = comp.interactLabel ?? comp.id;
            interactableObjects.push(child);
          }
        });
      }
    }

    // ── Lights ─────────────────────────────────────────────
    for (const light of desc.lights) {
      scene.add(this.buildLight(light));
    }

    return {
      scene,
      collisionObjects,
      interactableObjects,
      groundHeight: desc.groundLevel,
      spawnPosition: new THREE.Vector3(
        desc.playerSpawn.x,
        desc.playerSpawn.y,
        desc.playerSpawn.z
      ),
      playerYaw: desc.playerYaw ?? 0,
      shootingAreaPolygon: desc.shootingAreaPolygon,
    };
  }

  private buildGround(scene: THREE.Scene, desc: WorldDescription): void {
    const sizeX = desc.size.x;
    const sizeZ = desc.size.z;

    const texKind = desc.groundTexture ?? 'real:grass';
    const repeat = desc.groundTextureRepeat ?? [Math.ceil(sizeX), Math.ceil(sizeZ)];

    let groundMat: THREE.MeshStandardMaterial;

    if (texKind.startsWith('real:')) {
      const name = texKind.slice(5);
      groundMat = RealTextures.createMaterial(name, undefined, repeat as [number, number]);
    } else {
      // Procedural fallback
      let texture: THREE.Texture;
      switch (texKind) {
        case 'grass': texture = ProceduralTextures.grass(); break;
        case 'stone': texture = ProceduralTextures.stone(); break;
        case 'dirt':  texture = ProceduralTextures.dirt(); break;
        default:      texture = ProceduralTextures.grass(); break;
      }
      texture.wrapS = THREE.RepeatWrapping;
      texture.wrapT = THREE.RepeatWrapping;
      texture.repeat.set(repeat[0], repeat[1]);
      texture.colorSpace = THREE.SRGBColorSpace;
      groundMat = new THREE.MeshStandardMaterial({
        map: texture,
        roughness: 0.9,
        metalness: 0.0,
      });
    }

    const groundGeo = new THREE.PlaneGeometry(sizeX, sizeZ);
    const ground = new THREE.Mesh(groundGeo, groundMat);
    ground.rotation.x = -Math.PI / 2; // Lay flat
    ground.position.y = desc.groundLevel;
    ground.receiveShadow = true;
    ground.userData = { id: 'ground', collision: false, interactable: false };

    scene.add(ground);
  }

  private buildComposite(comp: CompositeObject): THREE.Group {
    const group = new THREE.Group();
    group.position.set(comp.position.x, comp.position.y, comp.position.z);
    group.userData = {
      id: comp.id,
      collision: comp.collision ?? false,
      interactable: comp.interactable ?? false,
      interactLabel: comp.interactLabel ?? comp.id,
    };

    for (const part of comp.parts) {
      const mesh = this.factory.createMesh(part);
      group.add(mesh);
    }

    return group;
  }

  private buildLight(light: WorldLight): THREE.Light {
    const color = new THREE.Color(light.color ?? '#ffffff');
    const intensity = light.intensity ?? 1;

    switch (light.kind) {
      case 'ambient': {
        const l = new THREE.AmbientLight(color, intensity);
        return l;
      }

      case 'directional': {
        const l = new THREE.DirectionalLight(color, intensity);
        const pos = light.position ?? { x: 5, y: 10, z: 5 };
        l.position.set(pos.x, pos.y, pos.z);

        if (light.castShadow) {
          l.castShadow = true;
          const mapSize = light.shadowMapSize ?? 2048;
          l.shadow.mapSize.width = mapSize;
          l.shadow.mapSize.height = mapSize;
          const camSize = light.shadowCameraSize ?? 15;
          l.shadow.camera.left = -camSize;
          l.shadow.camera.right = camSize;
          l.shadow.camera.top = camSize;
          l.shadow.camera.bottom = -camSize;
          l.shadow.camera.near = 0.5;
          l.shadow.camera.far = 50;
          l.shadow.bias = -0.0001;
        }
        return l;
      }

      case 'point': {
        const l = new THREE.PointLight(color, intensity, light.distance ?? 10);
        if (light.position) {
          l.position.set(light.position.x, light.position.y, light.position.z);
        }
        if (light.castShadow) {
          l.castShadow = true;
          l.shadow.mapSize.width = light.shadowMapSize ?? 512;
          l.shadow.mapSize.height = light.shadowMapSize ?? 512;
        }
        return l;
      }

      default:
        return new THREE.AmbientLight(color, intensity);
    }
  }
}

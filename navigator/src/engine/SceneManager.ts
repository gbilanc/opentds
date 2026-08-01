import * as THREE from 'three';
import { PlayerController } from './PlayerController.js';
import { InteractionSystem } from '../ui/InteractionSystem.js';
import { HUD } from '../ui/HUD.js';
import { RealTextures } from '../utils/RealTextures.js';
import type { BuiltWorld } from '../world/WorldBuilder.js';

/**
 * Central scene manager: renderer, animation loop, wiring.
 */
export class SceneManager {

  private renderer: THREE.WebGLRenderer;
  private clock = new THREE.Clock();
  private player: PlayerController;
  private interaction: InteractionSystem;
  private hud: HUD;
  private world: BuiltWorld;
  private static initPromise: Promise<void> | null = null;
  private selectedMesh: THREE.Object3D | null = null;

  /** Preload shared assets before building any scene */
  static preloadAssets(): Promise<void> {
    if (!SceneManager.initPromise) {
      SceneManager.initPromise = RealTextures.preloadAll();
    }
    return SceneManager.initPromise;
  }

  constructor(world: BuiltWorld) {
    this.world = world;

    // Renderer
    this.renderer = new THREE.WebGLRenderer({ antialias: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setSize(window.innerWidth, window.innerHeight);
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.1;

    document.getElementById('app')!.appendChild(this.renderer.domElement);

    // Camera (created outside so PlayerController owns it)
    const camera = new THREE.PerspectiveCamera(
      70, // FOV
      window.innerWidth / window.innerHeight,
      0.1,
      50,
    );

    // Player
    this.player = new PlayerController(camera, this.renderer.domElement);
    this.player.camera.position.copy(world.spawnPosition);

    // Apply initial yaw so the player faces the intended direction
    if (world.playerYaw) {
      this.player.setYaw(world.playerYaw);
    }

    // Interaction
    this.interaction = new InteractionSystem();
    this.interaction.setInteractCallback((label) => {
      this.hud.showMessage(`Hai interagito con: ${label}`);
    });

    // HUD
    this.hud = new HUD();

    // Keyboard: E for interact
    document.addEventListener('keydown', (e) => {
      if (e.code === 'KeyE' && this.player.isLocked()) {
        const result = this.interaction.handleInteract(
          this.player.camera,
          this.world.interactableObjects,
        );
        if (result) {
          this.hud.showMessage(`Hai interagito con: ${result}`);
        }
      }
    });

    // Resize handler
    window.addEventListener('resize', () => this.onResize());

    // Start editor↔3D sync polling
    this.startSyncPolling();

    // Start loop
    this.animate();
  }

  private animate = (): void => {
    requestAnimationFrame(this.animate);

    const delta = this.clock.getDelta();

    // Update player
    this.player.update(
      delta,
      this.world.groundHeight,
      this.world.collisionObjects,
    );

    // Check interaction target
    const interactLabel = this.interaction.checkInteraction(
      this.player.camera,
      this.world.interactableObjects,
    );

    if (interactLabel) {
      this.hud.showInteraction(interactLabel);
    } else {
      this.hud.hideInteraction();
    }

    // Render
    this.renderer.render(this.world.scene, this.player.camera);
  };

  private onResize(): void {
    this.player.camera.aspect = window.innerWidth / window.innerHeight;
    this.player.camera.updateProjectionMatrix();
    this.renderer.setSize(window.innerWidth, window.innerHeight);
  }

  /** Poll selection.json for editor↔3D sync */
  private startSyncPolling(): void {
    window.setInterval(() => this.pollSelection(), 500);
  }

  private async pollSelection(): Promise<void> {
    try {
      const resp = await fetch('/selection.json', { cache: 'no-store' });
      if (!resp.ok) return;
      const data = await resp.json();
      const id = data.selected_id;
      if (id === undefined || id === null) return;

      // Find mesh by userData id pattern: "target-{id}-..." or "wall-{id}" etc.
      const targetPatterns = [
        `target-${id}-board`, `target-${id}-pole`,
        `steel-${id}-plate`, `steel-${id}-pole`,
        `metal-${id}-plate`, `metal-${id}-pole`,
        `wall-${id}`, `barrier-${id}`, `hard-cover-${id}`,
      ];

      let found: THREE.Object3D | null = null;
      this.world.scene.traverse((obj) => {
        if (found) return;
        const uid = obj.userData?.id as string | undefined;
        if (uid && targetPatterns.some(p => uid === p || uid.startsWith(`target-${id}-`))) {
          found = obj;
        }
      });

      // Remove highlight from previous
      if (this.selectedMesh && this.selectedMesh !== found) {
        this.unhighlightMesh(this.selectedMesh);
      }

      // Highlight new
      if (found && found !== this.selectedMesh) {
        this.highlightMesh(found);
      }

      this.selectedMesh = found;
    } catch {
      // Silently ignore — editor may not be running
    }
  }

  private highlightMesh(mesh: THREE.Object3D): void {
    mesh.traverse((child) => {
      if (child instanceof THREE.Mesh) {
        const mat = child.material as THREE.MeshStandardMaterial;
        if (mat.emissive) {
          (child.userData as any)._origEmissive = mat.emissive.getHex();
          mat.emissive = new THREE.Color('#ffcc00');
          mat.emissiveIntensity = 0.5;
        }
      }
    });
  }

  private unhighlightMesh(mesh: THREE.Object3D): void {
    mesh.traverse((child) => {
      if (child instanceof THREE.Mesh) {
        const mat = child.material as THREE.MeshStandardMaterial;
        const orig = (child.userData as any)._origEmissive;
        if (mat.emissive && orig !== undefined) {
          mat.emissive = new THREE.Color(orig);
          mat.emissiveIntensity = 0;
        }
      }
    });
  }
}

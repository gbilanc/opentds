import * as THREE from 'three';
import { PlayerController } from './PlayerController.js';
import { InteractionSystem } from '../ui/InteractionSystem.js';
import { HUD } from '../ui/HUD.js';
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
}

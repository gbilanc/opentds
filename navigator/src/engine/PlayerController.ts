import * as THREE from 'three';
import { PointerLockControls } from 'three/examples/jsm/controls/PointerLockControls.js';

/**
 * First-person player controller: WASD movement, mouse look, jumping.
 */
export class PlayerController {
  public readonly camera: THREE.PerspectiveCamera;
  public readonly controls: PointerLockControls;

  // Movement state
  private moveForward = false;
  private moveBackward = false;
  private moveLeft = false;
  private moveRight = false;

  // Velocity
  private velocity = new THREE.Vector3();
  private direction = new THREE.Vector3();

  // Config
  private readonly moveSpeed = 4.0;
  private readonly jumpHeight = 4.0;

  // Physics
  private gravity = -9.8;
  private onGround = false;
  private readonly STANDING_HEIGHT = 1.70;
  private readonly CROUCH_HEIGHT = 0.40;
  private readonly CROUCH_SPEED = 4.0; // meters per second transition
  private currentHeight = this.STANDING_HEIGHT;
  private crouchActive = false;
  private playerRadius = 0.3;

  constructor(camera: THREE.PerspectiveCamera, domElement: HTMLElement) {
    this.camera = camera;
    this.camera.position.set(1, this.currentHeight, 1);

    this.controls = new PointerLockControls(camera, domElement);

    // Click to lock pointer
    domElement.addEventListener('click', () => {
      this.controls.lock();
    });

    this.controls.addEventListener('lock', () => {
      document.getElementById('instructions')?.classList.add('hidden');
    });

    this.controls.addEventListener('unlock', () => {
      document.getElementById('instructions')?.classList.remove('hidden');
    });

    // Keyboard listeners
    document.addEventListener('keydown', (e) => this.onKeyDown(e));
    document.addEventListener('keyup', (e) => this.onKeyUp(e));
  }

  update(deltaTime: number, groundHeight: number, collisionMeshes: THREE.Object3D[]): void {
    if (!this.controls.isLocked) return;

    // Clamp delta to avoid huge jumps on tab-away
    const dt = Math.min(deltaTime, 0.1);

    // Deceleration / friction
    this.velocity.x -= this.velocity.x * 10.0 * dt;
    this.velocity.z -= this.velocity.z * 10.0 * dt;

    // Apply gravity
    this.velocity.y += this.gravity * dt;

    // Movement direction from input
    this.direction.set(0, 0, 0);
    if (this.moveForward) this.direction.z += 1;
    if (this.moveBackward) this.direction.z -= 1;
    if (this.moveRight) this.direction.x += 1;
    if (this.moveLeft) this.direction.x -= 1;
    this.direction.normalize();

    // Apply movement relative to camera facing
    const forward = new THREE.Vector3();
    this.camera.getWorldDirection(forward);
    forward.y = 0;
    forward.normalize();

    const right = new THREE.Vector3();
    right.crossVectors(forward, new THREE.Vector3(0, 1, 0)).normalize();

    if (this.direction.z !== 0) {
      this.velocity.x += forward.x * this.direction.z * this.moveSpeed * dt * 10;
      this.velocity.z += forward.z * this.direction.z * this.moveSpeed * dt * 10;
    }
    if (this.direction.x !== 0) {
      this.velocity.x += right.x * this.direction.x * this.moveSpeed * dt * 10;
      this.velocity.z += right.z * this.direction.x * this.moveSpeed * dt * 10;
    }

    // Calculate new position
    const oldPosition = this.camera.position.clone();
    const newPosition = oldPosition.clone();
    newPosition.x += this.velocity.x * dt;
    newPosition.z += this.velocity.z * dt;
    newPosition.y += this.velocity.y * dt;

    // Smooth crouch transition
    const targetHeight = this.crouchActive ? this.CROUCH_HEIGHT : this.STANDING_HEIGHT;
    if (Math.abs(this.currentHeight - targetHeight) > 0.001) {
      const sign = targetHeight > this.currentHeight ? 1 : -1;
      this.currentHeight += sign * this.CROUCH_SPEED * dt;
      if (sign > 0 ? this.currentHeight > targetHeight : this.currentHeight < targetHeight) {
        this.currentHeight = targetHeight;
      }
    }

    // Ground collision
    const minY = groundHeight + this.currentHeight;
    if (newPosition.y < minY) {
      this.velocity.y = 0;
      newPosition.y = minY;
      this.onGround = true;
    } else {
      this.onGround = false;
    }

    // Obstacle collision (simple AABB + cylinder)
    const adjustedPosition = this.resolveCollisions(oldPosition, newPosition, collisionMeshes);

    this.camera.position.copy(adjustedPosition);
  }

  jump(): void {
    if (this.onGround) {
      this.velocity.y = this.jumpHeight;
      this.onGround = false;
    }
  }

  isLocked(): boolean {
    return this.controls.isLocked;
  }

  /** Set the initial yaw angle (degrees) — rotates camera around world Y axis. */
  setYaw(degrees: number): void {
    const rad = THREE.MathUtils.degToRad(degrees);
    // Rotate the camera direction around world Y
    const dir = new THREE.Vector3(0, 0, -1);
    dir.applyAxisAngle(new THREE.Vector3(0, 1, 0), rad);
    this.camera.lookAt(this.camera.position.clone().add(dir));
  }

  getPosition(): THREE.Vector3 {
    return this.camera.position.clone();
  }

  private resolveCollisions(
    oldPos: THREE.Vector3,
    newPos: THREE.Vector3,
    obstacles: THREE.Object3D[]
  ): THREE.Vector3 {
    const result = newPos.clone();

    for (const obj of obstacles) {
      const box = new THREE.Box3().setFromObject(obj);
      // Expand box by player radius
      box.expandByScalar(this.playerRadius);

      // Player point (at center of body)
      const playerPoint = new THREE.Vector3(result.x, result.y - this.currentHeight * 0.5, result.z);

      if (box.containsPoint(playerPoint)) {
        // Push player out — try to restore X and Z from old position
        const oldPlayerPoint = new THREE.Vector3(
          oldPos.x,
          oldPos.y - this.currentHeight * 0.5,
          oldPos.z
        );

        // Try keeping X, using old Z
        const testX = new THREE.Vector3(result.x, oldPlayerPoint.y, oldPlayerPoint.z);
        if (!box.containsPoint(testX)) {
          result.z = oldPos.z;
          this.velocity.z = 0;
        } else {
          // Try keeping Z, using old X
          const testZ = new THREE.Vector3(oldPlayerPoint.x, oldPlayerPoint.y, result.z);
          if (!box.containsPoint(testZ)) {
            result.x = oldPos.x;
            this.velocity.x = 0;
          } else {
            // Full block — revert both
            result.x = oldPos.x;
            result.z = oldPos.z;
            this.velocity.x = 0;
            this.velocity.z = 0;
          }
        }
      }
    }

    return result;
  }

  private onKeyDown(event: KeyboardEvent): void {
    if (!this.controls.isLocked) return;

    switch (event.code) {
      case 'KeyW': case 'ArrowUp':    this.moveForward = true; break;
      case 'KeyS': case 'ArrowDown':  this.moveBackward = true; break;
      case 'KeyA': case 'ArrowLeft':  this.moveLeft = true; break;
      case 'KeyD': case 'ArrowRight': this.moveRight = true; break;
      case 'Space':                    this.jump(); break;
      case 'KeyC': case 'ControlLeft': case 'ControlRight':
        this.crouchActive = true; break;
    }
  }

  private onKeyUp(event: KeyboardEvent): void {
    switch (event.code) {
      case 'KeyW': case 'ArrowUp':    this.moveForward = false; break;
      case 'KeyS': case 'ArrowDown':  this.moveBackward = false; break;
      case 'KeyA': case 'ArrowLeft':  this.moveLeft = false; break;
      case 'KeyD': case 'ArrowRight': this.moveRight = false; break;
      case 'KeyC': case 'ControlLeft': case 'ControlRight':
        this.crouchActive = false; break;
    }
  }
}

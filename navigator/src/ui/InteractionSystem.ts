import * as THREE from 'three';

/**
 * Detects what the player is looking at and handles E-key interactions.
 */
export class InteractionSystem {

  private raycaster = new THREE.Raycaster();
  private readonly maxDistance = 3.0;
  private currentTarget: THREE.Mesh | null = null;
  private callback: ((label: string) => void) | null = null;

  setInteractCallback(cb: (label: string) => void): void {
    this.callback = cb;
  }

  /**
   * Cast a ray from the camera center. Returns the interactable mesh hit, or null.
   */
  update(
    camera: THREE.Camera,
    interactables: THREE.Mesh[],
  ): THREE.Mesh | null {
    this.raycaster.setFromCamera(new THREE.Vector2(0, 0), camera);
    this.raycaster.far = this.maxDistance;

    const hits = this.raycaster.intersectObjects(interactables, true);

    if (hits.length > 0) {
      // Walk up to find the mesh that has interactable userData
      let obj: THREE.Object3D | null = hits[0].object;
      while (obj) {
        if (obj.userData?.interactable) {
          return obj as THREE.Mesh;
        }
        obj = obj.parent;
      }
    }

    return null;
  }

  /**
   * Called by main loop with the current interactable target.
   * Returns the label if any, or null.
   */
  checkInteraction(
    camera: THREE.Camera,
    interactables: THREE.Mesh[],
  ): string | null {
    const target = this.update(camera, interactables);

    if (target !== this.currentTarget) {
      this.currentTarget = target;
    }

    if (target) {
      return target.userData?.interactLabel ?? 'Interagisci';
    }
    return null;
  }

  /** Handle E-key press */
  handleInteract(
    camera: THREE.Camera,
    interactables: THREE.Mesh[],
  ): string | null {
    const target = this.update(camera, interactables);
    if (target && this.callback) {
      const label = target.userData?.interactLabel ?? target.userData?.id ?? 'oggetto';
      this.callback(label);
      return label;
    }
    return null;
  }
}

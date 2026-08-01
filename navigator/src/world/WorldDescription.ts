/**
 * DSL (Domain Specific Language) for describing a 3D world.
 * Everything is defined declaratively — no manual modeling.
 */

// ─── Primitives ────────────────────────────────────────────

export interface Vec3 {
  x: number;
  y: number;
  z: number;
}

export type PrimitiveKind =
  | 'box'
  | 'cylinder'
  | 'sphere'
  | 'cone'
  | 'plane'
  | 'octagon';  // flat octagonal IPSC target shape

export type TextureKind =
  | 'grass'
  | 'wood'
  | 'stone'
  | 'dirt'
  | 'roof'
  | 'solid'  // solid color (no texture)
  | `real:${string}`; // PBR texture from public/textures/real/ (e.g. "real:grass", "real:wood")

// ─── Object Definition ─────────────────────────────────────

export interface WorldObject {
  id: string;
  kind: PrimitiveKind;
  /** Position in world space */
  position: Vec3;
  /** Scale (default 1,1,1) */
  scale?: Vec3;
  /** Rotation in degrees */
  rotation?: Vec3;
  /** Color when texture is 'solid' */
  color?: string;
  /** Procedural texture type */
  texture?: TextureKind;
  /** Repeat factor for texture (default [1,1]) */
  textureRepeat?: [number, number];
  /** Whether this object blocks the player */
  collision?: boolean;
  /** Whether the player can interact with this */
  interactable?: boolean;
  /** Label shown on interaction */
  interactLabel?: string;
  /** Flat shading */
  flatShading?: boolean;
}

// ─── Composite Object ──────────────────────────────────────

/** A composite is a group of primitives positioned relative to a common origin */
export interface CompositeObject {
  id: string;
  /** Position of the whole composite */
  position: Vec3;
  collision?: boolean;
  interactable?: boolean;
  interactLabel?: string;
  parts: Omit<WorldObject, 'collision' | 'interactable' | 'interactLabel'>[];
}

// ─── Light ─────────────────────────────────────────────────

export interface WorldLight {
  kind: 'ambient' | 'directional' | 'point';
  color?: string;
  intensity?: number;
  /** For directional: direction; for point: position */
  position?: Vec3;
  castShadow?: boolean;
  /** Shadow map size */
  shadowMapSize?: number;
  /** Shadow camera frustum size */
  shadowCameraSize?: number;
  /** Max distance for point light */
  distance?: number;
}

// ─── World Description ─────────────────────────────────────

export interface WorldDescription {
  name: string;
  /** World size in meters (centered at origin) */
  size: Vec3;
  /** Sky color (top) */
  skyColor: string;
  /** Ground level color (for fog) */
  groundColor: string;
  /** Fog density */
  fogDensity?: number;
  /** Ground plane height */
  groundLevel: number;
  /** Ground texture override */
  groundTexture?: TextureKind;
  /** Ground texture repeat */
  groundTextureRepeat?: [number, number];
  /** Player spawn position */
  playerSpawn: Vec3;
  /** Initial yaw (degrees) — derived from start shooting position angle */
  playerYaw?: number;
  /** Primitives */
  objects: WorldObject[];
  /** Composites (trees, buildings, etc.) */
  composites: CompositeObject[];
  /** Lights */
  lights: WorldLight[];
  /** Shooting area polygon vertices [x, z] for player containment */
  shootingAreaPolygon?: Array<{x: number; z: number}>;
}

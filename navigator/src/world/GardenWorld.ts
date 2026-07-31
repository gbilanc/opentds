import type { WorldDescription } from './WorldDescription.js';

/**
 * Demo world: a small fenced garden with a cabin, tree, and path.
 * Approximately 8x8 meters.
 */
export const GardenWorld: WorldDescription = {
  name: 'Giardino Recintato',
  size: { x: 8, y: 1, z: 8 },
  skyColor: '#87CEEB',
  groundColor: '#b8d4b8',
  fogDensity: 0.01,
  groundLevel: 0,
  groundTexture: 'grass',
  groundTextureRepeat: [8, 8],
  playerSpawn: { x: 2, y: 1.7, z: 2 },

  // ── Primitives ───────────────────────────────────────────

  objects: [
    // Path: dirt strip from gate to cabin
    {
      id: 'path',
      kind: 'plane',
      position: { x: 0, y: 0.01, z: 0 },
      scale: { x: 1.2, y: 1, z: 5 },
      texture: 'dirt',
      textureRepeat: [1, 5],
      collision: false,
    },

    // Fence posts & rails — back (z = -3.5)
    ...buildFence('back',  0, 0, -3.5, 8, 'z'),
    // Front (z = 3.5) — with a gap in the middle for the gate
    ...buildFence('front-left',  -4, 0, 3.5, 3, 'z'),
    ...buildFence('front-right', 1, 0, 3.5, 3, 'z'),
    // Left side (x = -3.5)
    ...buildFence('left',  -3.5, 0, 0, 7, 'x'),
    // Right side (x = 3.5)
    ...buildFence('right', 3.5, 0, 0, 7, 'x'),
  ],

  // ── Composites ───────────────────────────────────────────

  composites: [
    // Cabin at the back
    buildCabin('cabin', 0, 0, -2),

    // Big tree near center
    buildTree('oak-tree', -1.5, 0, 1.5, 1.8),

    // Small bush near cabin
    buildBush('bush-1', 1.5, 0, -1.5, 0.5),
    buildBush('bush-2', -2, 0, -0.5, 0.4),

    // Bench
    buildBench('bench', -2.5, 0, 2.5),
  ],

  // ── Lights ───────────────────────────────────────────────

  lights: [
    {
      kind: 'ambient',
      color: '#b1c9e8',
      intensity: 0.6,
    },
    {
      kind: 'directional',
      color: '#fff4e0',
      intensity: 1.2,
      position: { x: 8, y: 12, z: 3 },
      castShadow: true,
      shadowMapSize: 2048,
      shadowCameraSize: 12,
    },
    {
      kind: 'point',
      color: '#ffcc88',
      intensity: 1.5,
      position: { x: 0, y: 2.2, z: -1.8 },
      distance: 6,
      castShadow: true,
      shadowMapSize: 512,
    },
  ],
};

// ─── Composite Builders ────────────────────────────────────

function buildCabin(
  id: string,
  x: number,
  y: number,
  z: number,
) {
  return {
    id,
    position: { x, y, z },
    collision: true,
    interactable: true,
    interactLabel: 'Capanna di legno',
    parts: [
      // Floor
      {
        id: `${id}-floor`,
        kind: 'box' as const,
        position: { x: 0, y: 0.05, z: 0 },
        scale: { x: 2, y: 0.1, z: 2 },
        texture: 'wood' as const,
        textureRepeat: [2, 2] as [number, number],
      },
      // Back wall
      {
        id: `${id}-back-wall`,
        kind: 'box' as const,
        position: { x: 0, y: 1, z: -0.95 },
        scale: { x: 2, y: 2, z: 0.1 },
        texture: 'wood' as const,
        textureRepeat: [2, 2] as [number, number],
      },
      // Left wall
      {
        id: `${id}-left-wall`,
        kind: 'box' as const,
        position: { x: -0.95, y: 1, z: 0 },
        scale: { x: 0.1, y: 2, z: 2 },
        texture: 'wood' as const,
        textureRepeat: [2, 2] as [number, number],
      },
      // Right wall
      {
        id: `${id}-right-wall`,
        kind: 'box' as const,
        position: { x: 0.95, y: 1, z: 0 },
        scale: { x: 0.1, y: 2, z: 2 },
        texture: 'wood' as const,
        textureRepeat: [2, 2] as [number, number],
      },
      // Front wall (left half)
      {
        id: `${id}-front-left`,
        kind: 'box' as const,
        position: { x: -0.5, y: 1, z: 0.95 },
        scale: { x: 0.9, y: 2, z: 0.1 },
        texture: 'wood' as const,
        textureRepeat: [1, 2] as [number, number],
      },
      // Front wall (right half)
      {
        id: `${id}-front-right`,
        kind: 'box' as const,
        position: { x: 0.5, y: 1, z: 0.95 },
        scale: { x: 0.9, y: 2, z: 0.1 },
        texture: 'wood' as const,
        textureRepeat: [1, 2] as [number, number],
      },
      // Roof (cone / pyramid shape approximated)
      {
        id: `${id}-roof-left`,
        kind: 'box' as const,
        position: { x: -0.5, y: 2.15, z: 0 },
        scale: { x: 1.1, y: 0.1, z: 2.2 },
        rotation: { x: 0, y: 0, z: 25 },
        texture: 'roof' as const,
        textureRepeat: [1, 2] as [number, number],
      },
      {
        id: `${id}-roof-right`,
        kind: 'box' as const,
        position: { x: 0.5, y: 2.15, z: 0 },
        scale: { x: 1.1, y: 0.1, z: 2.2 },
        rotation: { x: 0, y: 0, z: -25 },
        texture: 'roof' as const,
        textureRepeat: [1, 2] as [number, number],
      },
      // Chimney
      {
        id: `${id}-chimney`,
        kind: 'box' as const,
        position: { x: 0.4, y: 2.5, z: -0.4 },
        scale: { x: 0.2, y: 0.7, z: 0.2 },
        color: '#666666',
        texture: 'solid' as const,
      },
      // Door frame (dark)
      {
        id: `${id}-door-left`,
        kind: 'box' as const,
        position: { x: 0.05, y: 0.5, z: 0.96 },
        scale: { x: 0.08, y: 1, z: 0.12 },
        color: '#4a3120',
        texture: 'solid' as const,
      },
      {
        id: `${id}-door-right`,
        kind: 'box' as const,
        position: { x: -0.05, y: 0.5, z: 0.96 },
        scale: { x: 0.08, y: 1, z: 0.12 },
        color: '#4a3120',
        texture: 'solid' as const,
      },
      {
        id: `${id}-door-top`,
        kind: 'box' as const,
        position: { x: 0, y: 1, z: 0.96 },
        scale: { x: 0.25, y: 0.05, z: 0.12 },
        color: '#4a3120',
        texture: 'solid' as const,
      },
      // Window (left wall)
      {
        id: `${id}-window`,
        kind: 'box' as const,
        position: { x: -0.96, y: 1.2, z: -0.3 },
        scale: { x: 0.12, y: 0.4, z: 0.4 },
        color: '#aaddee',
        texture: 'solid' as const,
      },
    ],
  };
}

function buildTree(
  id: string,
  x: number,
  y: number,
  z: number,
  height: number,
) {
  return {
    id,
    position: { x, y, z },
    collision: true,
    interactable: true,
    interactLabel: 'Una vecchia quercia',
    parts: [
      // Trunk
      {
        id: `${id}-trunk`,
        kind: 'cylinder' as const,
        position: { x: 0, y: height * 0.3, z: 0 },
        scale: { x: 0.2, y: height * 0.6, z: 0.2 },
        color: '#6B4226',
        texture: 'solid' as const,
        flatShading: true,
      },
      // Foliage layers (cones stacked)
      {
        id: `${id}-foliage-1`,
        kind: 'cone' as const,
        position: { x: 0, y: height * 0.55, z: 0 },
        scale: { x: 1.0, y: height * 0.4, z: 1.0 },
        color: '#3d6b2e',
        texture: 'solid' as const,
        flatShading: true,
      },
      {
        id: `${id}-foliage-2`,
        kind: 'cone' as const,
        position: { x: 0, y: height * 0.7, z: 0 },
        scale: { x: 0.75, y: height * 0.35, z: 0.75 },
        color: '#4a7c3f',
        texture: 'solid' as const,
        flatShading: true,
      },
      {
        id: `${id}-foliage-3`,
        kind: 'cone' as const,
        position: { x: 0, y: height * 0.83, z: 0 },
        scale: { x: 0.5, y: height * 0.25, z: 0.5 },
        color: '#5a8c4f',
        texture: 'solid' as const,
        flatShading: true,
      },
    ],
  };
}

function buildBush(
  id: string,
  x: number,
  y: number,
  z: number,
  size: number,
) {
  return {
    id,
    position: { x, y, z },
    collision: true,
    interactable: false,
    parts: [
      {
        id: `${id}-main`,
        kind: 'sphere' as const,
        position: { x: 0, y: size * 0.5, z: 0 },
        scale: { x: size, y: size * 0.7, z: size },
        color: '#3d6b2e',
        texture: 'solid' as const,
        flatShading: true,
      },
      {
        id: `${id}-small`,
        kind: 'sphere' as const,
        position: { x: size * 0.4, y: size * 0.4, z: size * 0.3 },
        scale: { x: size * 0.6, y: size * 0.5, z: size * 0.6 },
        color: '#4a7c3f',
        texture: 'solid' as const,
        flatShading: true,
      },
    ],
  };
}

function buildBench(
  id: string,
  x: number,
  y: number,
  z: number,
) {
  return {
    id,
    position: { x, y, z },
    collision: true,
    interactable: true,
    interactLabel: 'Una panchina di legno',
    parts: [
      // Seat
      {
        id: `${id}-seat`,
        kind: 'box' as const,
        position: { x: 0, y: 0.4, z: 0 },
        scale: { x: 1.2, y: 0.08, z: 0.4 },
        texture: 'wood' as const,
        textureRepeat: [2, 1] as [number, number],
      },
      // Left legs
      {
        id: `${id}-leg-left`,
        kind: 'box' as const,
        position: { x: -0.45, y: 0.2, z: 0 },
        scale: { x: 0.08, y: 0.4, z: 0.35 },
        color: '#5a3a1a',
        texture: 'solid' as const,
      },
      // Right legs
      {
        id: `${id}-leg-right`,
        kind: 'box' as const,
        position: { x: 0.45, y: 0.2, z: 0 },
        scale: { x: 0.08, y: 0.4, z: 0.35 },
        color: '#5a3a1a',
        texture: 'solid' as const,
      },
      // Backrest
      {
        id: `${id}-backrest`,
        kind: 'box' as const,
        position: { x: 0, y: 0.7, z: 0.18 },
        scale: { x: 1.2, y: 0.35, z: 0.06 },
        texture: 'wood' as const,
        textureRepeat: [2, 1] as [number, number],
      },
    ],
  };
}

// ─── Fence Helper ──────────────────────────────────────────

function buildFence(
  id: string,
  x: number,
  y: number,
  z: number,
  length: number,
  axis: 'x' | 'z',
): WorldDescription['objects'] {
  const objects: WorldDescription['objects'] = [];
  const half = length / 2;
  const postSpacing = 1.0;
  const postCount = Math.floor(length / postSpacing) + 1;

  for (let i = 0; i < postCount; i++) {
    const t = -half + i * postSpacing;
    const px = axis === 'x' ? x + t : x;
    const pz = axis === 'z' ? z + t : z;

    // Post
    objects.push({
      id: `${id}-post-${i}`,
      kind: 'cylinder',
      position: { x: px, y: y + 0.5, z: pz },
      scale: { x: 0.06, y: 1, z: 0.06 },
      color: '#8B6914',
      texture: 'solid',
      collision: true,
    });

    // Horizontal rail (between posts)
    if (i < postCount - 1) {
      const nextT = -half + (i + 1) * postSpacing;
      const midX = axis === 'x' ? x + (t + nextT) / 2 : x;
      const midZ = axis === 'z' ? z + (t + nextT) / 2 : z;
      const railLen = Math.abs(nextT - t);

      const railX = axis === 'x' ? railLen : 0.04;
      const railZ = axis === 'z' ? railLen : 0.04;

      // Top rail
      objects.push({
        id: `${id}-rail-top-${i}`,
        kind: 'box',
        position: { x: midX, y: y + 0.75, z: midZ },
        scale: { x: railX, y: 0.04, z: railZ },
        color: '#A0784C',
        texture: 'solid',
        collision: true,
      });

      // Bottom rail
      objects.push({
        id: `${id}-rail-bottom-${i}`,
        kind: 'box',
        position: { x: midX, y: y + 0.3, z: midZ },
        scale: { x: railX, y: 0.04, z: railZ },
        color: '#A0784C',
        texture: 'solid',
        collision: true,
      });
    }
  }

  return objects;
}

import type { WorldDescription, WorldObject, CompositeObject } from './WorldDescription.js';

// ─── OpenTDS JSON types ────────────────────────────────────

interface OpenTDSItem {
  id: number;
  type: string;
  x: number;
  y: number;
  width: number;
  height: number;
  rotation: number;
  color: string;
  label: string;
  properties: Record<string, unknown>;
}

interface OpenTDSShootingPosition {
  id: number;
  x: number;
  y: number;
  label: string;
  is_start: boolean;
  angle: number;
  properties: Record<string, unknown>;
}

interface OpenTDSStage {
  version: number;
  name: string;
  width: number;
  depth: number;
  course_type?: string;
  items: OpenTDSItem[];
  shooting_positions: OpenTDSShootingPosition[];
  properties: Record<string, unknown>;
}

// ─── Mapping ────────────────────────────────────────────────

/** Convert OpenTDS item to one or more WorldObjects */
function itemToObjects(item: OpenTDSItem): WorldObject[] {
  const base: Pick<WorldObject, 'position' | 'rotation' | 'collision'> = {
    position: { x: item.x, y: 0, z: item.y },
    rotation: { x: 0, y: item.rotation, z: 0 },
    collision: false,
  };

  switch (item.type) {
    // ── Structural ──────────────────────────────────────────
    case 'WALL':
      return [{
        ...base,
        id: `wall-${item.id}`,
        kind: 'box',
        scale: { x: item.width, y: 2.0, z: Math.max(item.height, 0.15) },
        color: item.color,
        texture: 'solid',
        collision: true,
        interactable: false,
      }];

    case 'BARRIER':
      return [{
        ...base,
        id: `barrier-${item.id}`,
        kind: 'box',
        scale: { x: item.width, y: 1.0, z: Math.max(item.height, 0.15) },
        color: item.color,
        texture: 'solid',
        collision: true,
        interactable: false,
      }];

    case 'HARD_COVER':
      return [{
        ...base,
        id: `hard-cover-${item.id}`,
        kind: 'box',
        scale: { x: item.width, y: 2.0, z: Math.max(item.height, 0.2) },
        color: item.color,
        texture: 'solid',
        collision: true,
        interactable: false,
      }];

    case 'SOFT_COVER':
      return [{
        ...base,
        id: `soft-cover-${item.id}`,
        kind: 'box',
        scale: { x: item.width, y: 1.5, z: Math.max(item.height, 0.15) },
        color: item.color,
        texture: 'solid',
        collision: false,
        interactable: false,
      }];

    case 'DOOR':
      return [{
        ...base,
        id: `door-${item.id}`,
        kind: 'box',
        scale: { x: item.width, y: 2.0, z: Math.max(item.height, 0.1) },
        color: '#8B6914',
        texture: 'wood',
        collision: true,
        interactable: true,
        interactLabel: item.label || 'Porta',
      }];

    // ── Fault Lines ─────────────────────────────────────────
    case 'FAULT_LINE': {
      const isPerimeter = item.properties?.perimeter === true;
      // All fault lines: thin red line on the ground (0.5 cm tall)
      return [{
        ...base,
        id: isPerimeter ? `fence-${item.id}` : `fault-${item.id}`,
        kind: 'box',
        scale: { x: item.width, y: 0.005, z: 0.06 },
        position: { x: item.x, y: 0.0025, z: item.y },
        rotation: { x: 0, y: item.rotation, z: 0 },
        color: isPerimeter ? '#b91c1c' : '#dc2626',
        texture: 'solid',
        collision: isPerimeter,  // only perimeter lines block movement
        interactable: false,
      }];
    }

    // ── Targets ─────────────────────────────────────────────
    case 'PAPER_TARGET':
    case 'MINI_TARGET':
    case 'MICRO_TARGET':
    case 'NO_SHOOT':
      return buildTarget(item);

    case 'STEEL_TARGET':
    case 'POPPER':
      return buildSteelTarget(item);

    case 'METAL_PLATE':
      return buildMetalTarget(item);

    // ── Mobile targets: represent as static for now ─────────
    case 'SWINGER':
    case 'DROP_TURNER':
    case 'MOVER':
      return buildTarget(item);

    // ── Composite targets ───────────────────────────────────
    case 'DOUBLET_SIDE':
      return buildDoublet(item, 'side');
    case 'DOUBLET_OVERLAP':
      return buildDoublet(item, 'overlap');
    case 'DOUBLET_SIDE_HOSTAGE':
      return buildDoubletWithHostage(item, 'side');
    case 'DOUBLET_OVERLAP_HOSTAGE':
      return buildDoubletWithHostage(item, 'overlap');
    case 'BOBBER_PLATE':
      return buildSteelTarget(item);
    case 'DOUBLE_BOBBER':
      return buildSteelTarget(item);
    case 'TARGET_PLUS_NOSHOOT':
      return buildTargetWithNoShoot(item);

    default:
      console.warn(`Unknown item type: ${item.type}`);
      return [];
  }
}

/** Build a paper target: pole + target board */
function buildTarget(item: OpenTDSItem): WorldObject[] {
  const isNoShoot = item.type === 'NO_SHOOT';
  const targetColor = isNoShoot ? '#eab308' : item.color;
  const targetHeight = 0.75; // IPSC paper target height
  const targetWidth = item.width; // usually 0.45
  const poleHeight = 1.5;

  return [
    // Pole
    {
      id: `target-${item.id}-pole`,
      kind: 'cylinder',
      position: { x: item.x, y: poleHeight / 2, z: item.y },
      scale: { x: 0.03, y: poleHeight, z: 0.03 },
      color: '#666666',
      texture: 'solid',
      collision: false,
    },
    // Target board — faces shooter: 2D rotation→3D with -90° offset
    {
      id: `target-${item.id}-board`,
      kind: 'box',
      position: { x: item.x, y: poleHeight + targetHeight / 2 - 0.1, z: item.y },
      scale: { x: targetWidth, y: targetHeight, z: 0.02 },
      rotation: { x: 0, y: item.rotation - 90, z: 0 },
      color: targetColor,
      texture: 'solid',
      collision: false,
      interactable: true,
      interactLabel: isNoShoot ? 'No-Shoot (penalità)' : item.label || 'Bersaglio',
    },
  ];
}

/** Build a steel popper target — vertical disc on a pole */
function buildSteelTarget(item: OpenTDSItem): WorldObject[] {
  const poleHeight = 1.2;
  const discRadius = 0.15;
  const discThickness = 0.04;

  return [
    // Pole
    {
      id: `steel-${item.id}-pole`,
      kind: 'cylinder',
      position: { x: item.x, y: poleHeight / 2, z: item.y },
      scale: { x: 0.04, y: poleHeight, z: 0.04 },
      color: '#666666',
      texture: 'solid',
      collision: false,
    },
    // Vertical disc — X=90 stands it up, Y rotation faces the shooter
    {
      id: `steel-${item.id}-plate`,
      kind: 'cylinder',
      position: { x: item.x, y: poleHeight + 0.05, z: item.y },
      scale: { x: discRadius, y: discThickness, z: discRadius },
      rotation: { x: 90, y: item.rotation - 90, z: 0 },
      color: item.color || '#d1d5db',
      texture: 'solid',
      collision: false,
      interactable: true,
      interactLabel: item.label || 'Metallico',
    },
  ];
}

/** Build a small metal plate — vertical disc on a short pole */
function buildMetalTarget(item: OpenTDSItem): WorldObject[] {
  const poleHeight = 0.8;
  const discRadius = item.width; // e.g. 0.20 for metal plate
  const discThickness = 0.03;

  return [
    {
      id: `metal-${item.id}-pole`,
      kind: 'cylinder',
      position: { x: item.x, y: poleHeight / 2, z: item.y },
      scale: { x: 0.03, y: poleHeight, z: 0.03 },
      color: '#666666',
      texture: 'solid',
      collision: false,
    },
    {
      id: `metal-${item.id}-plate`,
      kind: 'cylinder',
      position: { x: item.x, y: poleHeight + 0.03, z: item.y },
      scale: { x: discRadius, y: discThickness, z: discRadius },
      rotation: { x: 90, y: item.rotation - 90, z: 0 },
      color: item.color || '#e5e7eb',
      texture: 'solid',
      collision: false,
      interactable: true,
      interactLabel: item.label || 'Piatto metallico',
    },
  ];
}

/** Build a doublet (two targets side by side or overlapping) */
function buildDoublet(item: OpenTDSItem, mode: 'side' | 'overlap'): WorldObject[] {
  const results: WorldObject[] = [];
  const spacing = mode === 'side' ? 0.3 : 0.05;

  // Two paper targets next to each other
  for (let i = 0; i < 2; i++) {
    const offsetX = (i - 0.5) * spacing;
    const rad = (item.rotation * Math.PI) / 180;
    const dx = offsetX * Math.cos(rad);
    const dz = offsetX * Math.sin(rad);

    results.push(...buildTarget({
      ...item,
      id: item.id * 100 + i,
      x: item.x + dx,
      y: item.y + dz,
      label: `${item.label || 'Paper'} ${i + 1}`,
    }));
  }
  return results;
}

/** Build two targets with a no-shoot in between */
function buildDoubletWithHostage(item: OpenTDSItem, mode: 'side' | 'overlap'): WorldObject[] {
  const results: WorldObject[] = [];
  const spacing = mode === 'side' ? 0.3 : 0.05;
  const rad = (item.rotation * Math.PI) / 180;

  // No-shoot in the middle
  results.push(...buildTarget({
    ...item,
    id: item.id * 100 + 99,
    type: 'NO_SHOOT',
    label: 'No-Shoot',
  }));

  // Two papers on sides
  for (let i = 0; i < 2; i++) {
    const offsetX = (i - 0.5) * spacing * 2;
    const dx = offsetX * Math.cos(rad);
    const dz = offsetX * Math.sin(rad);
    results.push(...buildTarget({
      ...item,
      id: item.id * 100 + i,
      x: item.x + dx,
      y: item.y + dz,
      label: `${item.label || 'Paper'} ${i + 1}`,
    }));
  }
  return results;
}

/** Build a paper target with no-shoot overlay */
function buildTargetWithNoShoot(item: OpenTDSItem): WorldObject[] {
  return [
    ...buildTarget({ ...item, id: item.id * 100, type: 'PAPER_TARGET', label: 'Paper + No-Shoot' }),
    ...buildTarget({ ...item, id: item.id * 101, type: 'NO_SHOOT', label: 'No-Shoot' }),
  ];
}

/** Build shooting position markers */
function buildShootingPosition(sp: OpenTDSShootingPosition): WorldObject[] {
  const rad = (sp.angle * Math.PI) / 180;
  const arrowLen = 0.5;
  const color = sp.is_start ? '#22c55e' : '#3b82f6';

  return [
    // Ground circle
    {
      id: `sp-${sp.id}-circle`,
      kind: 'cylinder',
      position: { x: sp.x, y: 0.005, z: sp.y },
      scale: { x: 0.4, y: 0.01, z: 0.4 },
      color,
      texture: 'solid',
      collision: false,
      interactable: false,
    },
    // Direction arrow — angle 0°=+X, 90°=+Z (down-range)
    {
      id: `sp-${sp.id}-arrow`,
      kind: 'box',
      position: {
        x: sp.x + (arrowLen / 2) * Math.cos(rad),
        y: 0.01,
        z: sp.y + (arrowLen / 2) * Math.sin(rad),
      },
      scale: { x: 0.08, y: 0.01, z: arrowLen },
      rotation: { x: 0, y: 90 - sp.angle, z: 0 },
      color,
      texture: 'solid',
      collision: false,
      interactable: false,
    },
  ];
}

// ─── Public API ─────────────────────────────────────────────

/**
 * Parse an OpenTDS JSON object into a WorldDescription
 * that can be fed to WorldBuilder.
 */
export function parseOpenTDS(json: OpenTDSStage): WorldDescription {
  const objects: WorldObject[] = [];
  const composites: CompositeObject[] = [];

  // ── Items ─────────────────────────────────────────────────
  for (const item of json.items) {
    objects.push(...itemToObjects(item));
  }

  // ── Shooting positions ────────────────────────────────────
  for (const sp of json.shooting_positions) {
    objects.push(...buildShootingPosition(sp));
  }

  // ── Ground border (terrain extension beyond the stage) ────
  const margin = 6; // meters of extra terrain around the stage
  const worldWidth = json.width + margin * 2;
  const worldDepth = json.depth + margin * 2;
  const halfW = worldWidth / 2;
  const halfD = worldDepth / 2;

  // ── Shooting area overlay (lighter rectangle on the ground) ──
  // Offset so the stage area is centered in the world
  const stageOffsetX = margin;
  const stageOffsetZ = margin;

  objects.push({
    id: 'shooting-area',
    kind: 'plane',
    position: { x: stageOffsetX + json.width / 2, y: 0.006, z: stageOffsetZ + json.depth / 2 },
    scale: { x: json.width, y: 1, z: json.depth },
    color: '#e8e0d0',
    texture: 'dirt',
    textureRepeat: [Math.ceil(json.width / 2), Math.ceil(json.depth / 2)],
    collision: false,
  });

  // ── Offset all items into the centered stage area ──────────
  for (const obj of objects) {
    obj.position.x += stageOffsetX;
    obj.position.z += stageOffsetZ;
  }

  // ── Boundary walls (around world perimeter) ───────────────
  const bw = 0.2; // thickness
  const bh = 3.0; // height
  objects.push(
    { id: 'boundary-n', kind: 'box', position: { x: halfW, y: bh / 2, z: 0 }, scale: { x: worldWidth, y: bh, z: bw }, color: '#5a5a5a', texture: 'stone', collision: true },
    { id: 'boundary-s', kind: 'box', position: { x: halfW, y: bh / 2, z: worldDepth }, scale: { x: worldWidth, y: bh, z: bw }, color: '#5a5a5a', texture: 'stone', collision: true },
    { id: 'boundary-w', kind: 'box', position: { x: 0, y: bh / 2, z: halfD }, scale: { x: bw, y: bh, z: worldDepth }, color: '#5a5a5a', texture: 'stone', collision: true },
    { id: 'boundary-e', kind: 'box', position: { x: worldWidth, y: bh / 2, z: halfD }, scale: { x: bw, y: bh, z: worldDepth }, color: '#5a5a5a', texture: 'stone', collision: true },
  );

  // ── Player spawn ──────────────────────────────────────────
  const playerSpawnPos = json.shooting_positions.find(sp => sp.is_start) ?? json.shooting_positions[0];
  const spawnX = (playerSpawnPos?.x ?? json.width / 2) + stageOffsetX;
  const spawnZ = (playerSpawnPos?.y ?? json.depth / 2) + stageOffsetZ;

  // Convert 2D angle (0°=+X, 90°=+Y/down-range) to Three.js yaw
  // Default camera forward is -Z; yaw rotates it: -Z + yaw → look direction
  const spawnAngle = playerSpawnPos?.angle ?? 0;
  const playerYaw = -(spawnAngle + 90);

  return {
    name: json.name || 'Stage IPSC',
    size: { x: worldWidth, y: 1, z: worldDepth },
    skyColor: '#87CEEB',
    groundColor: '#c8d8c8',
    fogDensity: 0.008,
    groundLevel: 0,
    groundTexture: 'grass',
    groundTextureRepeat: [Math.ceil(worldWidth), Math.ceil(worldDepth)],
    playerSpawn: { x: spawnX, y: 1.7, z: spawnZ },
    playerYaw,
    objects,
    composites,
    lights: [
      {
        kind: 'ambient',
        color: '#b1c9e8',
        intensity: 0.7,
      },
      {
        kind: 'directional',
        color: '#fff8e8',
        intensity: 1.4,
        position: { x: json.width / 2, y: 15, z: json.depth + 5 },
        castShadow: true,
        shadowMapSize: 2048,
        shadowCameraSize: Math.max(json.width, json.depth) + 10,
      },
    ],
  };
}

/**
 * Load an OpenTDS JSON file from a URL and return a WorldDescription.
 */
export async function loadOpenTDS(url: string): Promise<WorldDescription> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to load OpenTDS file: ${response.status}`);
  }
  const json: OpenTDSStage = await response.json();
  return parseOpenTDS(json);
}

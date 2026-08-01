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

/** Compute angle from point to area center (degrees, 0=+X) */
function autoFaceAngle(x: number, y: number, center: {x: number; z: number}): number {
  return Math.atan2(center.z - y, center.x - x) * 180 / Math.PI;
}

/** Convert OpenTDS item to one or more WorldObjects */
function itemToObjects(item: OpenTDSItem, areaCenter: {x: number; z: number}): WorldObject[] {
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
        texture: 'real:bricks',
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
        texture: 'real:wood',
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
        texture: 'real:wood',
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
        texture: 'solid' as const,
        collision: false,  // perimeter is enforced via 2D polygon containment
        interactable: false,
      }];
    }

    // ── Targets ─────────────────────────────────────────────
    case 'PAPER_TARGET':
    case 'MINI_TARGET':
    case 'MICRO_TARGET':
    case 'NO_SHOOT':
      return buildTarget({
        ...item,
        rotation: autoFaceAngle(item.x, item.y, areaCenter),
      });

    case 'STEEL_TARGET':
    case 'POPPER':
      return buildSteelTarget({
        ...item,
        rotation: autoFaceAngle(item.x, item.y, areaCenter),
      });

    case 'METAL_PLATE':
      return buildMetalTarget({
        ...item,
        rotation: autoFaceAngle(item.x, item.y, areaCenter),
      });

    // ── Mobile targets: represent as static for now ─────────
    case 'SWINGER':
    case 'DROP_TURNER':
    case 'MOVER':
      return buildTarget({
        ...item,
        rotation: autoFaceAngle(item.x, item.y, areaCenter),
      });

    // ── Composite targets ───────────────────────────────────
    case 'DOUBLET_SIDE':
      return buildDoublet({ ...item, rotation: autoFaceAngle(item.x, item.y, areaCenter) }, 'side');
    case 'DOUBLET_OVERLAP':
      return buildDoublet({ ...item, rotation: autoFaceAngle(item.x, item.y, areaCenter) }, 'overlap');
    case 'DOUBLET_SIDE_HOSTAGE':
      return buildDoubletWithHostage({ ...item, rotation: autoFaceAngle(item.x, item.y, areaCenter) }, 'side');
    case 'DOUBLET_OVERLAP_HOSTAGE':
      return buildDoubletWithHostage({ ...item, rotation: autoFaceAngle(item.x, item.y, areaCenter) }, 'overlap');
    case 'BOBBER_PLATE':
      return buildSteelTarget({ ...item, rotation: autoFaceAngle(item.x, item.y, areaCenter) });
    case 'DOUBLE_BOBBER':
      return buildSteelTarget({ ...item, rotation: autoFaceAngle(item.x, item.y, areaCenter) });
    case 'TARGET_PLUS_NOSHOOT':
      return buildTargetWithNoShoot({ ...item, rotation: autoFaceAngle(item.x, item.y, areaCenter) });

    default:
      console.warn(`Unknown item type: ${item.type}`);
      return [];
  }
}

/** Build a paper target: two side wooden sticks + octagonal board */
function buildTarget(item: OpenTDSItem): WorldObject[] {
  const isNoShoot = item.type === 'NO_SHOOT';
  const targetColor = isNoShoot ? '#eab308' : item.color;
  const targetHeight = 0.75; // IPSC paper target height
  const targetWidth = 0.45;  // body width
  const stickHeight = 1.5;   // height of the side sticks
  const stickOffset = targetWidth / 2 + 0.02; // sticks just outside the board
  const boardY = stickHeight - targetHeight / 2 + 0.05; // board center Y

  // Compute stick positions rotated according to item.rotation
  const rotRad = ((item.rotation - 90) * Math.PI) / 180;
  const perpX = Math.cos(rotRad) * stickOffset;
  const perpZ = Math.sin(rotRad) * stickOffset;

  return [
    // Left wooden stick
    {
      id: `target-${item.id}-stick-l`,
      kind: 'cylinder' as const,
      position: { x: item.x - perpX, y: stickHeight / 2, z: item.y - perpZ },
      scale: { x: 0.02, y: stickHeight, z: 0.02 },
      color: '#8B6914',
      texture: 'wood' as const,
      collision: false,
    },
    // Right wooden stick
    {
      id: `target-${item.id}-stick-r`,
      kind: 'cylinder' as const,
      position: { x: item.x + perpX, y: stickHeight / 2, z: item.y + perpZ },
      scale: { x: 0.02, y: stickHeight, z: 0.02 },
      color: '#8B6914',
      texture: 'wood' as const,
      collision: false,
    },
    // Octagonal target board
    {
      id: `target-${item.id}-board`,
      kind: 'octagon' as const,
      position: { x: item.x, y: boardY, z: item.y },
      scale: { x: targetWidth, y: targetHeight, z: 1 },
      rotation: { x: 0, y: item.rotation - 90, z: 0 },
      color: targetColor,
      texture: 'solid' as const,
      collision: false,
      interactable: true,
      interactLabel: isNoShoot ? 'No-Shoot (penalità)' : item.label || 'Bersaglio',
    },
  ];
}

/** Build a steel popper target — light blue vertical disc on a pole */
function buildSteelTarget(item: OpenTDSItem): WorldObject[] {
  const poleHeight = 1.2;
  const discRadius = 0.15;
  const discThickness = 0.04;

  return [
    // Pole
    {
      id: `steel-${item.id}-pole`,
      kind: 'cylinder' as const,
      position: { x: item.x, y: poleHeight / 2, z: item.y },
      scale: { x: 0.04, y: poleHeight, z: 0.04 },
      color: '#666666',
      texture: 'solid' as const,
      collision: false,
    },
    // Vertical disc — light blue, faces the shooter
    {
      id: `steel-${item.id}-plate`,
      kind: 'cylinder' as const,
      position: { x: item.x, y: poleHeight + 0.05, z: item.y },
      scale: { x: discRadius, y: discThickness, z: discRadius },
      rotation: { x: 90, y: item.rotation - 90, z: 0 },
      color: '#87CEEB',
      texture: 'solid' as const,
      collision: false,
      interactable: true,
      interactLabel: item.label || 'Metallico',
    },
  ];
}

/** Build a small metal plate — light blue disc on a short pole */
function buildMetalTarget(item: OpenTDSItem): WorldObject[] {
  const poleHeight = 0.8;
  const discRadius = item.width; // e.g. 0.20 for metal plate
  const discThickness = 0.03;

  return [
    {
      id: `metal-${item.id}-pole`,
      kind: 'cylinder' as const,
      position: { x: item.x, y: poleHeight / 2, z: item.y },
      scale: { x: 0.03, y: poleHeight, z: 0.03 },
      color: '#666666',
      texture: 'solid' as const,
      collision: false,
    },
    {
      id: `metal-${item.id}-plate`,
      kind: 'cylinder' as const,
      position: { x: item.x, y: poleHeight + 0.03, z: item.y },
      scale: { x: discRadius, y: discThickness, z: discRadius },
      rotation: { x: 90, y: item.rotation - 90, z: 0 },
      color: '#87CEEB',
      texture: 'solid' as const,
      collision: false,
      interactable: true,
      interactLabel: item.label || 'Piatto metallico',
    },
  ];
}

/** Build a doublet (two targets side by side or overlapping vertically) */
function buildDoublet(item: OpenTDSItem, mode: 'side' | 'overlap'): WorldObject[] {
  if (mode === 'overlap') {
    // Vertical overlap: targets offset by ±10cm in world Y (20cm total)
    const results: WorldObject[] = [];
    const offsets = [-0.10, 0.10]; // bottom, top
    for (let i = 0; i < 2; i++) {
      const objs = buildTarget({
        ...item,
        id: item.id * 100 + i,
        x: item.x, y: item.y,
        label: `${item.label || 'Paper'} ${i + 1}`,
      });
      for (const obj of objs) {
        obj.position.y += offsets[i];
      }
      results.push(...objs);
    }
    return results;
  }

  // Side by side: offset perpendicular to rotation
  const spacing = 0.3;
  const perpAngle = (item.rotation + 90) * Math.PI / 180;
  const results: WorldObject[] = [];
  for (let i = 0; i < 2; i++) {
    const dist = (i - 0.5) * spacing;
    results.push(...buildTarget({
      ...item,
      id: item.id * 100 + i,
      x: item.x + dist * Math.cos(perpAngle),
      y: item.y + dist * Math.sin(perpAngle),
      label: `${item.label || 'Paper'} ${i + 1}`,
    }));
  }
  return results;
}

/** Build two targets with a no-shoot in between */
function buildDoubletWithHostage(item: OpenTDSItem, mode: 'side' | 'overlap'): WorldObject[] {
  if (mode === 'overlap') {
    // Vertical overlap with no-shoot at center (no Y offset)
    const results: WorldObject[] = [];
    const offsets = [-0.10, 0.10];
    for (let i = 0; i < 2; i++) {
      const objs = buildTarget({
        ...item,
        id: item.id * 100 + i,
        x: item.x, y: item.y,
        label: `${item.label || 'Paper'} ${i + 1}`,
      });
      for (const obj of objs) obj.position.y += offsets[i];
      results.push(...objs);
    }
    results.push(...buildTarget({ ...item, id: item.id * 100 + 99, type: 'NO_SHOOT', label: 'No-Shoot' }));
    return results;
  }

  // Side by side with no-shoot in the middle
  const spacing = 0.3;
  const perpAngle = (item.rotation + 90) * Math.PI / 180;
  const results: WorldObject[] = [];
  // No-shoot at center
  results.push(...buildTarget({ ...item, id: item.id * 100 + 99, type: 'NO_SHOOT', label: 'No-Shoot' }));
  // Two papers on sides
  for (let i = 0; i < 2; i++) {
    const dist = (i - 0.5) * spacing;
    results.push(...buildTarget({
      ...item,
      id: item.id * 100 + i,
      x: item.x + dist * Math.cos(perpAngle),
      y: item.y + dist * Math.sin(perpAngle),
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

/** Build the shooting area polygon from perimeter fault lines */
function buildShootingAreaPolygon(
  json: OpenTDSStage,
  offsetX: number,
  offsetZ: number
): Array<{x: number; z: number}> | undefined {
  // Use pre-computed perimeter_poly if available
  const poly = json.properties?.perimeter_poly as [number, number][] | undefined;
  if (poly && poly.length >= 3) {
    return poly.map(([x, y]) => ({ x: x + offsetX, z: y + offsetZ }));
  }

  // Reconstruct from perimeter fault lines
  const faultLines = json.items.filter(
    it => it.type === 'FAULT_LINE' && it.properties?.perimeter === true
  );
  if (faultLines.length < 3) return undefined;

  // Compute endpoints of each segment
  const segments: Array<{p1: [number, number]; p2: [number, number]}> = [];
  for (const fl of faultLines) {
    const rad = (fl.rotation * Math.PI) / 180;
    const half = fl.width / 2;
    const dx = Math.cos(rad) * half;
    const dy = Math.sin(rad) * half;
    segments.push({
      p1: [fl.x - dx + offsetX, fl.y - dy + offsetZ],
      p2: [fl.x + dx + offsetX, fl.y + dy + offsetZ],
    });
  }

  // Chain segments into polygon
  const used = new Set<number>();
  const chain: Array<{x: number; z: number}> = [];
  let [x, y] = segments[0].p1;
  chain.push({ x, z: y });
  [x, y] = segments[0].p2;
  chain.push({ x, z: y });
  used.add(0);

  while (used.size < segments.length) {
    const last = chain[chain.length - 1];
    let found = false;
    for (let i = 0; i < segments.length; i++) {
      if (used.has(i)) continue;
      const s = segments[i];
      const d1 = Math.hypot(s.p1[0] - last.x, s.p1[1] - last.z);
      const d2 = Math.hypot(s.p2[0] - last.x, s.p2[1] - last.z);
      if (d1 < 0.15) {
        chain.push({ x: s.p1[0], z: s.p1[1] });
        chain.push({ x: s.p2[0], z: s.p2[1] });
        used.add(i);
        found = true;
        break;
      } else if (d2 < 0.15) {
        chain.push({ x: s.p2[0], z: s.p2[1] });
        chain.push({ x: s.p1[0], z: s.p1[1] });
        used.add(i);
        found = true;
        break;
      }
    }
    if (!found) break;
  }

  // Close: remove last point if it matches first
  if (chain.length >= 3) {
    const first = chain[0];
    const last = chain[chain.length - 1];
    if (Math.hypot(last.x - first.x, last.z - first.z) < 0.15) {
      chain.pop();
    }
  }

  return chain.length >= 3 ? chain : undefined;
}
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

  // ── Layout constants (needed early for polygon and area center) ──
  const margin = 6;
  const stageOffsetX = margin;
  const stageOffsetZ = margin;
  const worldWidth = json.width + margin * 2;
  const worldDepth = json.depth + margin * 2;
  const halfW = worldWidth / 2;
  const halfD = worldDepth / 2;

  // ── Shooting area polygon & center (for containment + auto-facing) ──
  const shootingAreaPolygon = buildShootingAreaPolygon(json, stageOffsetX, stageOffsetZ);
  let areaCenter = { x: stageOffsetX + json.width / 2, z: stageOffsetZ + json.depth / 2 };
  if (shootingAreaPolygon && shootingAreaPolygon.length >= 3) {
    let cx = 0, cz = 0;
    for (const v of shootingAreaPolygon) { cx += v.x; cz += v.z; }
    areaCenter = { x: cx / shootingAreaPolygon.length, z: cz / shootingAreaPolygon.length };
  }

  // ── Items (targets auto-face the area center) ────────────
  for (const item of json.items) {
    objects.push(...itemToObjects(item, areaCenter));
  }

  // ── Shooting positions ────────────────────────────────────
  for (const sp of json.shooting_positions) {
    objects.push(...buildShootingPosition(sp));
  }

  // ── Shooting area overlay ─────────────────────────────────
  objects.push({
    id: 'shooting-area',
    kind: 'plane',
    position: { x: stageOffsetX + json.width / 2, y: 0.006, z: stageOffsetZ + json.depth / 2 },
    scale: { x: json.width, y: 1, z: json.depth },
    color: '#e8e0d0',
    texture: 'real:ground',
    textureRepeat: [Math.ceil(json.width / 2), Math.ceil(json.depth / 2)],
    collision: false,
  });

  // ── Offset all items into the centered stage area ──────────
  for (const obj of objects) {
    obj.position.x += stageOffsetX;
    obj.position.z += stageOffsetZ;
  }

  // ── Boundary walls ────────────────────────────────────────
  const bw = 0.2;
  const bh = 3.0;
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
    shootingAreaPolygon,
    lights: [
      {
        kind: 'ambient',
        color: '#b1c9e8',
        intensity: 0.5,
      },
      {
        kind: 'directional',
        color: '#fff8e8',
        intensity: 1.8,
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

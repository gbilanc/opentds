import './style.css';
import { WorldBuilder } from './world/WorldBuilder.js';
import { loadOpenTDS } from './world/OpenTDSLoader.js';
import { SceneManager } from './engine/SceneManager.js';

/**
 * Boot the 3D environment from an OpenTDS JSON file.
 *
 * To switch stages, change the filename below or pass it via URL parameter ?stage=name
 */
async function main(): Promise<void> {
  // Detect stage from URL param, default to stage_short.json
  const params = new URLSearchParams(window.location.search);
  const stageFile = params.get('stage') ?? 'stage_short.json';

  try {
    // Preload PBR textures (non-blocking but renders after load)
    SceneManager.preloadAssets();

    const world = await loadOpenTDS(`/${stageFile}`);
    const builder = new WorldBuilder();
    const built = builder.build(world);
    new SceneManager(built);
  } catch (err) {
    document.getElementById('app')!.innerHTML = `
      <div style="color:white;text-align:center;padding:40px;font-family:sans-serif;">
        <h2>Errore caricamento stage</h2>
        <p>${err instanceof Error ? err.message : 'Errore sconosciuto'}</p>
        <p>File: <code>${stageFile}</code></p>
        <p style="margin-top:20px;">Prova con:</p>
        <ul style="list-style:none;padding:0;">
          <li><a href="?stage=stage_short.json" style="color:#4af;">stage_short.json</a></li>
          <li><a href="?stage=stage_short_barriers.json" style="color:#4af;">stage_short_barriers.json</a></li>
          <li><a href="?stage=stage_medium.json" style="color:#4af;">stage_medium.json</a></li>
          <li><a href="?stage=stage_long.json" style="color:#4af;">stage_long.json</a></li>
        </ul>
      </div>
    `;
  }
}

main();

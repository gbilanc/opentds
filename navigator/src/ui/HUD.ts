/**
 * Minimal HUD: crosshair, interaction hints, temporary messages.
 */
export class HUD {

  private crosshair: HTMLElement;
  private interactionHint: HTMLElement;
  private messageEl: HTMLElement;
  private instructionsEl: HTMLElement;

  private messageTimer: number | null = null;

  constructor() {
    // Create HUD container
    const hud = document.createElement('div');
    hud.id = 'hud';
    document.body.appendChild(hud);

    // Crosshair
    this.crosshair = document.createElement('div');
    this.crosshair.id = 'crosshair';
    hud.appendChild(this.crosshair);

    // Interaction hint
    this.interactionHint = document.createElement('div');
    this.interactionHint.id = 'interaction-hint';
    hud.appendChild(this.interactionHint);

    // Message
    this.messageEl = document.createElement('div');
    this.messageEl.id = 'message';
    hud.appendChild(this.messageEl);

    // Instructions overlay
    this.instructionsEl = document.createElement('div');
    this.instructionsEl.id = 'instructions';
    this.instructionsEl.innerHTML = `
      <h1>🏔️ Giardino Recintato</h1>
      <div class="controls">
        <span class="key">W A S D</span><span>Muoviti</span>
        <span class="key">Mouse</span><span>Guarda intorno</span>
        <span class="key">Spazio</span><span>Salta</span>
        <span class="key">E</span><span>Interagisci</span>
        <span class="key">ESC</span><span>Rilascia mouse</span>
      </div>
      <button id="start-btn">🎮 Clicca per giocare</button>
    `;
    hud.appendChild(this.instructionsEl);

    // Start button
    this.instructionsEl.querySelector('#start-btn')!.addEventListener('click', () => {
      document.body.requestPointerLock();
    });
  }

  showInteraction(label: string): void {
    this.interactionHint.innerHTML = `Premi <span class="key">E</span> ${label}`;
    this.interactionHint.classList.add('visible');
  }

  hideInteraction(): void {
    this.interactionHint.classList.remove('visible');
  }

  showMessage(text: string, duration = 2500): void {
    this.messageEl.textContent = text;
    this.messageEl.classList.add('visible');

    if (this.messageTimer !== null) {
      clearTimeout(this.messageTimer);
    }
    this.messageTimer = window.setTimeout(() => {
      this.messageEl.classList.remove('visible');
      this.messageTimer = null;
    }, duration);
  }

  showInstructions(): void {
    this.instructionsEl.classList.remove('hidden');
  }

  hideInstructions(): void {
    this.instructionsEl.classList.add('hidden');
  }
}

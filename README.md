# OpenTDS — Open Tactical Dynamic Stage Generator

Applicazione desktop cross-platform per la progettazione, generazione e simulazione di stage per il **Tiro Dinamico Sportivo (IPSC)**.

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![PySide6](https://img.shields.io/badge/PySide6-6.7%2B-green)
![License](https://img.shields.io/badge/license-MIT-yellow)

---

## Panoramica

OpenTDS consente a Range Officer, Match Director e tiratori di:

- **Disegnare stage IPSC** in un editor 2D con griglia metrica e snap
- **Generare automaticamente** layout random rispettando vincoli geometrici IPSC
- **Simulare in 3D** lo stage con camera orbitale e first-person
- **Animare bersagli mobili** (swinger, drop turner, mover) in tempo reale
- **Esportare** il progetto in JSON, PNG e PDF multi-pagina

---

## Stack Tecnologico

| Componente | Tecnologia |
|---|---|
| Linguaggio | Python 3.11+ |
| UI / Editor 2D | PySide6 Qt Widgets (`QGraphicsView`) |
| Viewer 3D | Qt Quick 3D via `QQuickWidget` |
| Validazione | `shapely` + motore custom IPSC |
| Packaging | PyInstaller |

---

## Installazione

### Requisiti

- Python 3.11 o superiore (gestito da `uv`)
- GPU con supporto OpenGL 3.3+ (per la vista 3D)

### Setup

### Prerequisiti

- [uv](https://docs.astral.sh/uv/getting-started/installation/) installato
- Python 3.11+ (uv lo scarica automaticamente se mancante)

### Setup

```bash
git clone https://github.com/your-org/opentds.git
cd opentds
uv sync              # crea venv e installa dipendenze
```

### Avvio

```bash
uv run python main.py
```

### Sviluppo / test

```bash
uv run pytest        # esegue i test
uv run ruff check .  # linting (opzionale)
```

---

## Funzionalità

### Editor 2D
- Griglia metrica con snap a 0.5 m
- Oggetti: **muri, barriere, porte, fault lines, no-shoots, bersagli carta/steel**
- Bersagli mobili: **swinger, drop turner, mover** con visualizzazione traiettoria
- Property dock laterale per editing live (coordinate, rotazione, dimensioni, parametri movimento)
- Undo/Redo (`Ctrl+Z` / `Ctrl+Shift+Z`)
- Zoom con rotella, pan, selezione multipla

### Generazione Procedurale IPSC
- Pannello di configurazione: dimensioni, numero bersagli, difficoltà, seed
- Constraint engine con distanze minime da bordi, muri, bersagli
- Punteggio automatico di qualità dello stage
- Esecuzione asincrona in thread separato

### Simulazione 3D
- Rendering hardware-accelerato Qt Quick 3D
- **Modalità Orbitale**: drag per ruotare, rotella zoom, Shift+drag pan
- **Modalità First-Person**: WASD movimento, Shift sprint, mouse look
- Animazioni live per bersagli mobili

### Esportazione
| Formato | Contenuto |
|---|---|
| **JSON** | Schema v1 completo, caricabile e modificabile |
| **PNG** | Piantina 2D ad alta risoluzione (150 DPI) |
| **PDF** | Piantina + lista bersagli + dettagli mobili |

---

## Architettura

```
opentds/
├── main.py                    # Entry point
├── requirements.txt
├── core/
│   ├── models.py              # StageItem, ItemType (10 tipi), Stage
│   ├── ipsc_rules.py          # IPSCRulesEngine (validatore vincoli)
│   └── generator.py           # StageGenerator + scoring
├── services/
│   ├── serializer.py          # JSON schema v1
│   └── exporter.py            # PNG + PDF multi-pagina
└── ui/
    ├── editor/
    │   ├── stage_scene.py     # QGraphicsScene + undo/redo
    │   ├── stage_view.py      # Zoom + pan
    │   ├── property_dock.py   # Editing proprietà
    │   └── generator_panel.py # Configurazione generazione
    ├── workers/
    │   └── generator_worker.py
    └── viewer3d/
        ├── quick_3d_widget.py # Bridge Python → QML 3D
        └── StageScene.qml     # Scena 3D + camera + animazioni
```

---

## Vincoli IPSC implementati

- Distanza minima bersaglio-bordo stage: **1.0 m**
- Distanza minima bersaglio-muro: **0.8 m**
- Distanza minima bersaglio-bersaglio: **0.8 m**
- Distanza minima bersaglio-barriera: **0.5 m**

---

## Tasti di scelta rapida

| Tasto | Azione |
|---|---|
| `Ctrl+Z` | Undo |
| `Ctrl+Shift+Z` | Redo |
| `Ctrl+S` | Salva JSON |
| `Ctrl+O` | Apri JSON |
| `Ctrl+G` | Genera stage |
| `Ctrl+Q` | Esci |
| `Del` | Elimina selezionati |
| Rotella mouse | Zoom 2D |

### 3D
| Modalità | Controlli |
|---|---|
| **Orbita** | Drag = ruota, rotella = zoom, Shift+drag = pan |
| **First-Person** | WASD = muovi, Shift = sprint, Mouse = look |

---

## Bersagli supportati

| Tipo | Codice colore | Animazione 3D |
|---|---|---|
| Paper Target | Rosso (#ef4444) | — |
| Steel Target | Blu (#3b82f6) | — |
| Swinger | Viola (#a855f7) | Oscillazione rotazione Y |
| Drop Turner | Verde (#14b8a6) | Caduta rotazione X |
| Mover | Arancione (#f97316) | Traslazione lineare |

---

## Roadmap

- [ ] `shapely` per collision detection avanzato
- [ ] Regole IPSC edizione 2025 complete
- [ ] Supporto IPSC Mini Rifle e Shotgun
- [ ] Texture 3D realistiche (legno, acciaio, terra)
- [ ] Modalità editor di percorsi di tiro
- [ ] Esportazione per tablet/table score
- [ ] Packaging PyInstaller (Windows, macOS, Linux AppImage)

---

## Licenza

MIT License — vedi file LICENSE.

---

## Contributori

Progetto sviluppato con l'AI Coding Agent **π (pi)**.

---

*OpenTDS — Stage design for practical shooters.*

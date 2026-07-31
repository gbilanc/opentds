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
- **Configurare l'aspetto dei bersagli** (colore centralizzato per tipo, rendering SVG vettoriale)
- **Esportare** il progetto in JSON, PNG, PDF e OpenSCAD (3D)
- **Validare** lo stage contro le regole IPSC (distanze, angoli, colpi per posizione, divisioni)

---

## Stack Tecnologico

| Componente | Tecnologia |
|---|---|
| Linguaggio | Python 3.11+ |
| UI / Editor 2D | PySide6 Qt Widgets (`QGraphicsView`) |
| Rendering bersagli | SVG vettoriale (`QSvgRenderer`) |
| Geometria / Collisioni | `shapely` |
| Export 3D | OpenSCAD (`.scad` / PNG / STL / 3MF) |
| Navigatore 3D | Three.js + TypeScript + Vite (first-person, WebGL) |
| Testing | `pytest` |

---

## Installazione

### Prerequisiti

- [uv](https://docs.astral.sh/uv/getting-started/installation/) installato
- Python 3.11+ (uv lo scarica automaticamente se mancante)
- OpenSCAD (opzionale, per rendering 3D e STL)

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

- Griglia metrica con snap a 0.5 m, parapalle di fondo con backstop indicatore
- **Area di tiro** evidenziata (poligono verde) delimitata da fault-line perimetrali
- Oggetti: **muri, barriere, porte, fault lines, hard/soft cover, bersagli**
- **Bersagli SVG vettoriali**: rendering nitido a qualsiasi zoom, sagome IPSC fedeli
- Bersagli mobili: **swinger, drop turner, mover** con visualizzazione traiettoria
- Property dock laterale per editing live (coordinate, rotazione, dimensioni, parametri movimento)
- Per i bersagli: colore e dimensioni **ereditati dal tipo**, non modificabili singolarmente
- Undo/Redo (`Ctrl+Z` / `Ctrl+Shift+Z`)
- Zoom con rotella, pan, selezione multipla, snap alla griglia

### Configurazione Aspetto Bersagli

- Menu `Configurazione → Aspetto Bersagli`
- Ogni tipo bersaglio ha un **colore predefinito** a livello applicativo
- I colori sono centralizzati in `TARGET_COLORS` (`core/constants.py`)
- Possibilità di modificare i colori a runtime e ripristinare i default IPSC
- I singoli bersagli ereditano automaticamente il colore del loro tipo

### Generazione Procedurale IPSC

- Pannello di configurazione: dimensioni stage, numero bersagli, difficoltà, seed
- **Forme alfabetiche** per l'area di tiro (L, T, U, C, H, O, Q, Z, S, X, Y, M, N, E, W, F)
- Constraint engine con distanze minime da bordi, muri, bersagli
- **Rotazione automatica** dei bersagli verso la shooting position più vicina
- **Lato più ampio** del bersaglio sempre rivolto verso il tiratore
- Relazioni attivatore-attivato tra metallici e bersagli mobili
- Punteggio automatico di qualità dello stage
- Esecuzione asincrona in thread separato

### Esportazione

| Formato | Contenuto |
|---|---|
| **JSON** | Schema v1 completo, caricabile e modificabile |
| **PNG** | Piantina 2D ad alta risoluzione (150 DPI) |
| **PDF** | Piantina + lista bersagli + dettagli mobili |
| **OpenSCAD (.scad)** | Modello 3D parametrico editabile |
| **PNG (OpenSCAD)** | Rendering 3D via `openscad` CLI |
| **STL / 3MF** | Stampa 3D dello stage |

---

## Architettura

```
opentds/
├── main.py                       # Entry point
├── pyproject.toml                # Dipendenze e build
├── navigator/                    # Visualizzatore 3D (Three.js + TypeScript)
├── core/
│   ├── models.py                 # StageItem, ItemType, Stage, ShootingPosition
│   ├── constants.py              # TARGET_COLORS, TARGET_DIMENSIONS, distanze IPSC
│   ├── geometry.py               # Utility geometriche (intersezioni, punto-in-poligono)
│   ├── collision.py              # OBB (Oriented Bounding Box) e overlap detection
│   ├── shapes.py                 # Forme alfabetiche area di tiro e poligoni perimetrali
│   ├── scoring.py                # Classificazione bersagli, scoring, metadati briefing
│   ├── ipsc_rules.py             # IPSCRulesEngine (validatore completo)
│   └── generator.py              # StageGenerator procedurale
├── services/
│   ├── serializer.py             # JSON schema v1 (salva/carica)
│   ├── exporter.py               # PNG + PDF multi-pagina
│   └── openscad_exporter.py      # OpenSCAD 3D export (.scad/PNG/STL/3MF)
├── ui/
│   ├── editor/
│   │   ├── stage_scene.py        # QGraphicsScene + undo/redo + factory grafica
│   │   ├── stage_view.py         # Zoom + pan
│   │   ├── stage_info.py         # Pannello riepilogo stage
│   │   ├── property_dock.py      # Dock editing proprietà oggetto
│   │   ├── generator_panel.py    # Pannello configurazione generazione
│   │   └── target_images.py      # TargetSvgManager (QSvgRenderer + cache)
│   ├── dialogs/
│   │   └── target_config_dialog.py  # Dialog configurazione aspetto bersagli
│   ├── workers/
│   │   └── generator_worker.py   # Thread worker per generazione asincrona
│   └── main_window.py            # Main window con menu, toolbar e dock
├── resources/
│   └── targets/
│       ├── ipsc_target.svg       # Sagoma IPSC classica (paper, mini, micro, mobili)
│       ├── ipsc_target_zones.svg # Sagoma con zone punteggio
│       ├── ipsc_popper.svg       # Popper calibrato (steel, popper)
│       ├── ipsc_metal_plate.svg  # Piatto metallico circolare
│       └── ipsc_no_shoot.svg     # Sagoma no-shoot
└── tests/
    ├── test_models.py
    ├── test_generator.py
    ├── test_scoring.py
    ├── test_ipsc_rules.py
    ├── test_shapes.py
    ├── test_serializer.py
    └── ...
```

---

## Vincoli IPSC implementati

- Distanza minima bersaglio-bordo stage: **1.0 m**
- Distanza minima bersaglio-muro: **0.8 m**
- Distanza minima bersaglio-bersaglio: **0.8 m**
- Distanza minima bersaglio-barriera: **0.5 m**
- Distanza minima tiratore-metallico: **7.0 m** (piazzamento a 8.0 m)
- Angolo di sicurezza default: **90°**
- Massimo **9 colpi** conteggiabili da singola posizione
- Validazione **Short/Medium/Long Course**
- Validazione **Divisione** (ottiche, compensatori, capacità caricatore)
- Rapporto **3:2:1** Short/Medium/Long per gare multi-stage

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

## Bersagli supportati

| Tipo | SVG | Colore default | Note |
|---|---|---|---|
| Paper Target | `ipsc_target.svg` | Marrone `#8B4513` | Sagoma IPSC classica (Reg. 4.1.2.1) |
| Steel Target | `ipsc_popper.svg` | Grigio `#d1d5db` | Metallico generico (Reg. 4.1.2.2) |
| Popper | `ipsc_popper.svg` | Grigio `#d1d5db` | Calibrato (App. C1-C2) |
| Piatto metallico | `ipsc_metal_plate.svg` | Grigio `#e5e7eb` | Non calibrato (App. C3) |
| Mini Target | `ipsc_target.svg` | Marrone `#A0522D` | Formato ridotto (App. B3) |
| Micro Target | `ipsc_target.svg` | Marrone `#8B4513` | Formato micro |
| Swinger | `ipsc_target.svg` | Marrone `#A0522D` | Bersaglio oscillante |
| Drop Turner | `ipsc_target.svg` | Marrone `#8B6914` | Bersaglio a caduta |
| Mover | `ipsc_target.svg` | Marrone `#CD853F` | Bersaglio su rotaia |
| No-Shoot | `ipsc_no_shoot.svg` | Giallo `#eab308` | Penalità (Reg. 4.1.3) |
| Hard Cover | Rettangolo | Grigio scuro `#1e293b` | Copertura impenetrabile (Reg. 4.1.4.1) |
| Soft Cover | Rettangolo | Grigio `#94a3b8` | Copertura visiva (Reg. 4.1.4.2) |

> **Nota**: I colori sono configurabili via `Configurazione → Aspetto Bersagli`.  
> I bersagli usano **SVG vettoriali** per un rendering nitido a qualsiasi zoom.

---

## Navigator — Visualizzatore 3D

Visualizzatore 3D first-person degli stage IPSC, realizzato con **Three.js + TypeScript + Vite**. Esplora gli stage creati in OpenTDS camminandoci letteralmente dentro.

```
navigator/
├── index.html                    # Entry point HTML
├── package.json                  # Dipendenze (three, vite, typescript)
├── tsconfig.json                 # TypeScript strict, target es2023
├── public/
│   ├── stage_short.json          # Stage Short Course di esempio
│   ├── stage_short_barriers.json # Short Course con barriere
│   ├── stage_medium.json         # Stage Medium Course di esempio
│   └── stage_long.json           # Stage Long Course di esempio
└── src/
    ├── main.ts                   # Bootstrap: carica JSON OpenTDS via URL param ?stage=
    ├── style.css                 # Reset, fullscreen, HUD styling
    ├── engine/
    │   ├── AssetFactory.ts       # Factory Three.js: mesh da WorldObject (box, cylinder, sphere, cone, plane)
    │   ├── PlayerController.ts   # Controller FPS: WASD, mouse look, salto, gravità, collisioni AABB
    │   └── SceneManager.ts       # Orchestratore: renderer WebGL, animation loop, wiring
    ├── world/
    │   ├── WorldDescription.ts   # DSL dichiarativo per mondi 3D (tipi Vec3, WorldObject, WorldLight, CompositeObject)
    │   ├── WorldBuilder.ts       # Costruisce la scena Three.js dal WorldDescription
    │   ├── OpenTDSLoader.ts      # Parser JSON OpenTDS → WorldDescription (mappa tutti i tipi di item)
    │   └── GardenWorld.ts        # Mondo demo: giardino con capanna, albero, panchina, staccionata
    ├── ui/
    │   ├── HUD.ts                # Mirino, hint interazione ("Premi E"), messaggi temporanei, overlay istruzioni
    │   └── InteractionSystem.ts  # Raycasting per rilevare oggetti interagibili (distanza max 3m)
    └── utils/
        └── ProceduralTextures.ts # Texture procedurali Canvas: erba, legno, pietra, terra, tetto
```

### Funzionalità

- **Navigazione first-person**: WASD per muoversi, mouse per guardarsi intorno, Spazio per saltare
- **Collisioni**: rilevamento contro muri, barriere, hard cover (AABB con push-back)
- **Interazione**: tasto E per interagire con oggetti (porte, bersagli, ecc.) entro 3 metri
- **Ombre dinamiche**: shadow mapping PCF soft per la luce direzionale
- **Texture procedurali**: generate a runtime via Canvas API, nessuna immagine esterna necessaria
- **HUD contestuale**: mirino centrale, hint di interazione, messaggi temporanei, overlay istruzioni
- **Stage multipli**: selezionabili via parametro URL `?stage=stage_medium.json`

### Conversione Item OpenTDS → 3D

| Tipo OpenTDS | Rappresentazione 3D | Collisione | Interazione |
|---|---|---|---|
| WALL | Box 2m altezza, texture solida | ✓ | — |
| BARRIER | Box 1m altezza, texture solida | ✓ | — |
| HARD_COVER | Box 2m altezza | ✓ | — |
| SOFT_COVER | Box 1.5m (senza collisione) | — | — |
| DOOR | Box 2m, texture legno | ✓ | ✓ "Porta" |
| FAULT_LINE (perimetrale) | Staccionata bassa 0.6m | ✓ | — |
| FAULT_LINE (interna) | Linea rossa a terra | — | — |
| PAPER/MINI/MICRO | Palo + pannello verticale | — | ✓ |
| NO_SHOOT | Palo + pannello giallo | — | ✓ "No-Shoot" |
| STEEL/POPPER | Palo + disco metallico | — | ✓ |
| METAL_PLATE | Palo basso + piatto sottile | — | ✓ |
| SWINGER/DROP_TURNER/MOVER | Come bersaglio paper (statico per ora) | — | ✓ |
| Composti (Doublet, ecc.) | Sotto-oggetti multipli con offset | — | ✓ |
| Shooting Position | Cerchio a terra + freccia direzionale (verde=start, blu=normale) | — | — |

### Comandi

| Tasto | Azione |
|---|---|
| `W A S D` / `Frecce` | Movimento |
| `Mouse` | Guardare intorno |
| `Spazio` | Saltare |
| `E` | Interagire con oggetti |
| `ESC` | Rilasciare il mouse |
| `Clic` | Bloccare il mouse / iniziare |

### Sviluppo

```bash
cd navigator
npm install       # installa three, vite, typescript
npm run dev       # avvia server di sviluppo (hot reload)
npm run build     # build di produzione in dist/
npm run preview   # preview della build
```

### Integrazione con OpenTDS

Il visualizzatore carica direttamente i file JSON esportati da OpenTDS (schema v1). Per usarlo con un nuovo stage:

1. Esporta lo stage da OpenTDS come JSON
2. Copia il file in `navigator/public/`
3. Avvia `npm run dev` e accedi via `?stage=nomefile.json`

---

## Roadmap

- [x] Rendering bersagli SVG vettoriale (`QSvgRenderer`)
- [x] Colori centralizzati per tipo bersaglio (`TARGET_COLORS`)
- [x] Configurazione aspetto bersagli da UI
- [x] Rotazione automatica verso shooting position più vicina
- [x] Lato più ampio del bersaglio sempre rivolto al tiratore
- [x] Validazione distanza metallici 7m, angoli sicurezza 90°, max colpi per posizione
- [x] Tipi Popper, Piatto metallico, Mini/Micro Target, Hard/Soft Cover
- [x] Validazione Short/Medium/Long Course
- [x] Validazione Divisione (ottiche, compensatori, canna, capacità)
- [x] Rapporto 3:2:1 per gare multi-stage
- [x] Generazione briefing in PDF
- [x] Navigatore 3D first-person con Three.js + TypeScript
- [ ] Regole IPSC edizione 2025 complete
- [ ] Supporto IPSC Mini Rifle e Shotgun
- [ ] Modalità editor di percorsi di tiro nel navigatore 3D
- [ ] Animazione bersagli mobili (swinger, drop turner, mover) nel navigatore
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

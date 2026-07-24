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
- [ ] Regole IPSC edizione 2025 complete
- [ ] Supporto IPSC Mini Rifle e Shotgun
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

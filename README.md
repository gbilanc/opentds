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
| Export 3D | OpenSCAD (`.scad` / PNG / STL / 3MF) |
| Validazione | `shapely` + motore custom IPSC |
| Packaging | PyInstaller |

---

## Installazione

### Requisiti

- Python 3.11 o superiore (gestito da `uv`)
- OpenSCAD (opzionale, per rendering 3D e STL)

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
├── main.py                    # Entry point
├── requirements.txt
├── core/
│   ├── models.py              # StageItem, ItemType (10 tipi), Stage
│   ├── ipsc_rules.py          # IPSCRulesEngine (validatore vincoli)
│   └── generator.py           # StageGenerator + scoring
├── services/
│   ├── serializer.py          # JSON schema v1
│   ├── exporter.py            # PNG + PDF multi-pagina
│   └── openscad_exporter.py   # OpenSCAD 3D export (.scad/PNG/STL)
└── ui/
    ├── editor/
    │   ├── stage_scene.py     # QGraphicsScene + undo/redo
    │   ├── stage_view.py      # Zoom + pan
    │   ├── property_dock.py   # Editing proprietà
    │   └── generator_panel.py # Configurazione generazione
    ├── workers/
    │   └── generator_worker.py
    └── main_window.py         # Main window con menu e toolbar
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

## Bersagli supportati

| Tipo | Codice colore IPSC | Note |
|---|---|---|
| Paper Target | Marrone (#8B4513) | Zona punti marrone (Reg. 4.1.2.1) |
| Steel Target | Grigio chiaro (#d1d5db) | Superficie bianca (Reg. 4.1.2.2) |
| Popper | Grigio chiaro (#d1d5db) | Metallico calibrato (App. C1-C2) |
| Piatto metallico | Grigio chiaro (#d1d5db) | Non calibrato (App. C3) |
| Mini Target | Marrone (#8B4513) | Formato ridotto (App. B3) |
| Micro Target | Marrone (#8B4513) | Formato micro |
| Swinger | Marrone scuro (#A0522D) | Bersaglio cartaceo mobile |
| Drop Turner | Marrone scuro (#8B6914) | Bersaglio cartaceo mobile |
| Mover | Marrone chiaro (#CD853F) | Bersaglio cartaceo mobile |
| No-Shoot | Giallo (#eab308) | Colore diverso dai bersagli punti (Reg. 4.1.3) |
| Hard Cover | Grigio scuro (#1e293b) | Copertura impenetrabile (Reg. 4.1.4.1) |
| Soft Cover | Grigio (#94a3b8) | Copertura visiva (Reg. 4.1.4.2) |

---

## Roadmap

- [x] Colori bersagli IPSC-conformi (marrone carta, bianco metallo, giallo no-shoot)
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

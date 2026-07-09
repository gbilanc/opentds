---
id: >-
  analysis-2026-07-09-analisi-conformita-opentds-al-regolamento-ipsc-handgun-2024
type: analysis
title: Analisi conformità OpenTDS al Regolamento IPSC Handgun 2024
aliases:
  - conformità regolamentare OpenTDS
  - gap analysis IPSC OpenTDS
tags:
  - OpenTDS
  - IPSC
  - conformità
  - analisi
  - regolamento
status: active
updated: '2026-07-09'
source_ids:
  - SRC-2026-07-09-001
summary: >-
  Analisi sistematica della conformità del codice OpenTDS (motore regole,
  generatore, modelli) al regolamento IPSC Handgun Edizione Gennaio 2024
---
# Analisi conformità OpenTDS al Regolamento IPSC Handgun 2024

## Question

Il generatore di stage e il motore di validazione IPSC di OpenTDS rispettano tutte le norme del Regolamento IPSC Handgun Edizione Gennaio 2024? In caso negativo, quali sono le lacune?

## Answer

La conformità è **parziale**. Il motore di validazione (`IPSCRulesEngine`) copre correttamente i vincoli geometrici di base (distanze, dimensioni, conteggi), ma mancano regole procedurali, di classificazione, di sicurezza avanzata e di scoring. Il generatore procedurale (`StageGenerator`) produce layout funzionali ma con alcune non-conformità cromatiche e tipologiche.

### Riepilogo per area

| Area | Stato | Dettaglio |
|---|---|---|
| Distanze geometriche | ✅ Buono | Bordo 1.0m, muro 0.8m, bersaglio 0.8m, barriera 0.5m, backstop 3.0m |
| Conteggio bersagli | ✅ Buono | Min 8, max 32, steel ≤40%, no-shoot consigliati 1:8 |
| Dimensioni stage | ✅ Buono | Min 10×8m, max 40×30m (pistola) |
| Posizioni di tiro | ✅ Buono | Validazione dentro stage, fuori muri, start position obbligatoria |
| Collision detection | ✅ Buono | OBB con Shapely per tutti i controlli spaziali |
| Tipi di esercizi | ❌ Assente | Nessuna classificazione Short/Medium/Long, nessun check max colpi da posizione |
| Rapporto 3:2:1 | ❌ Assente | Nessuna enforce del rapporto tra tipi di esercizio |
| Colori bersagli | ❌ Non conforme | Paper rosso (#ef4444) invece di marrone; Steel blu invece di bianco |
| Tipi bersagli specifici | ❌ Parziale | Manca Popper vs Piatto, Mini Target, Micro Target, Hard Cover, Soft Cover |
| Validazione per Divisione | ❌ Assente | Nessun check su box dimensionale, capacità caricatori, PF, ottiche |
| Angoli di sicurezza | ❌ Assente | Non verificati dal validator né dal generatore |
| Condizioni di pronto arma | ❌ Assente | Non modellate né validate |
| Freestyle compliance | ❌ Assente | Nessun check su ricaricamenti obbligatori, posizioni fisse |
| Briefing scritto | ❌ Assente | Il generatore non produce il briefing richiesto dalla Sez. 3.2 |
| Power Factor / Scoring | ❌ Fuori scope | OpenTDS è un generatore/editor, non un sistema di scoring |
| Shooting positions intermedie | ⚠️ Parziale | Il generatore non le crea, ma il modello le supporta |
| Bersagli mobili | ✅ Buono | Swinger, Drop Turner, Mover con proprietà di animazione |

### Dettaglio per componente

#### 1. `IPSCRulesEngine` (motore di validazione)

**✅ Vincoli implementati correttamente:**
- `MIN_TARGET_TO_EDGE = 1.0` — conforme a principi di sicurezza (Sez. 2.1)
- `MIN_TARGET_TO_WALL = 0.8` — desunto da vincoli di realizzazione
- `MIN_TARGET_TO_TARGET = 0.8` — ragionevole per accessibilità bersagli (Regola 4.2.4)
- `MIN_TARGET_TO_BARRIER = 0.5` — desunto da vincoli barriere (Regola 2.2.3)
- `MIN_BACKSTOP_DEPTH = 3.0` — conforme a requisiti di sicurezza parapalle
- `MIN_TARGETS = 8`, `MAX_TARGETS = 32` — coerente con max 32 colpi Long Course
- `MAX_STEEL_PCT = 0.4` — ratio ragionevole (non specificato nel regolamento ma buona pratica)
- Dimensioni stage: min 10×8m, max 40×30m per pistola
- `_validate_shooting_positions()`: posizioni dentro stage, non dentro muri, start position obbligatoria
- Validazione spaziale con Shapely OBB per calcoli precisi

**❌ Vincoli mancanti:**

1. **Max 9 colpi da singola posizione** (Regola 1.2.1.1-1.2.1.3)
   - Il validator non verifica che da qualsiasi posizione di tiro non siano visibili più di 9 bersagli conteggiabili.
   - *Impatto*: uno stage potrebbe violare il requisito fondamentale per Short/Medium/Long Course.

2. **Non tutti i bersagli visibili da una posizione** (Medium/Long Course, Regola 1.2.1.2-1.2.1.3)
   - Il validator non verifica che per Medium/Long Course non sia possibile ingaggiare tutti i bersagli da una singola posizione.

3. **Classificazione esercizio** (Short/Medium/Long)
   - Manca un attributo `course_type` nello `Stage` o nella configurazione.
   - Il validator non ha metodi per classificare o validare il tipo di esercizio.

4. **Rapporto 3:2:1** (Regola 1.2.1.4, Appendice A4)
   - Non implementato né nel generatore né nel validator.

5. **Condizioni di pronto arma** (Regola 1.2.1.5, 8.1)
   - Non modellate: nessuna proprietà per "arma scarica" / "camera vuota".
   - Il limite del 25% di esercizi con arma scarica non è verificabile.

6. **Angoli di sicurezza 90°** (Regola 2.1.2)
   - Non verificati. Il validator non calcola se un bersaglio costringerebbe il tiratore a superare gli angoli di sicurezza.

7. **Distanza metallici 7m/8m** (Regola 2.1.3)
   - Implementata solo nel `StageGenerator` (min_dist_from_edge=8.0 per STEEL_TARGET), ma **non** nel `IPSCRulesEngine._validate_spatial()`.
   - Il validator non verifica che i bersagli metallici siano ad almeno 7m dalle posizioni di tiro.

8. **Validazione per Divisione** (Appendici D1-D5)
   - Manca completamente: nessun check su box dimensionale 225×150×45mm, capacità caricatori, peso scatto, presenza ottiche/compensatori.

9. **No-Shoot obbligatori**
   - Attualmente sono solo "consigliati" (1 ogni 8 paper). Il regolamento richiede che i bersagli che assegnano penalità siano presenti e chiaramente contrassegnati (Regola 4.1.3).

#### 2. `StageGenerator` (generatore procedurale)

**✅ Comportamenti corretti:**
- Posiziona bersagli FUORI dall'area di tiro, tra area e parapalle.
- Steel a 8m dal perimetro (rispetta Regola 2.1.3).
- No-shoot attaccati davanti ai paper target (0.3-0.8m).
- Visibilità 100% garantita tramite rimozione ostacoli.
- Muri restrittivi per impedire visibilità da TUTTE le posizioni (principio Freestyle).
- Forma dell'area di tiro a lettera (diversità — Regola 1.1.4).
- Fault lines come delimitatore (colore rosso, ≥1.5m di default — Regola 2.2.1.4).
- Generazione ostacoli (muri, barriere) che bloccano la visuale.
- Bersagli mobili con proprietà di movimento documentate.

**❌ Non conformità cromatiche:**

| Elemento | Colore OpenTDS | Colore richiesto IPSC | Regola |
|---|---|---|---|
| Paper Target | Rosso #ef4444 | **Marrone** (zona punti) | 4.1.2.1 |
| Steel Target | Blu #3b82f6 | **Bianco** (superficie frontale) | 4.1.2.2 |
| Swinger | Viola #a855f7 | Dovrebbe essere marrone (carta) o bianco (metallo) | 4.1.2 |
| Drop Turner | Verde #14b8a6 | Idem | 4.1.2 |
| Mover | Arancione #f97316 | Idem | 4.1.2 |
| No-Shoot | Rosso #f87171 | **Colore uniforme DIVERSO** dai bersagli punti (es. giallo) o X ben visibile | 4.1.3 |
| Fault Line | Rosso #dc2626 | **Rosso** (raccomandato) ✅ | 2.2.1.4 |

*Impatto*: I colori usati da OpenTDS sono funzionali per l'editor ma non conformi al regolamento. I tiratori IPSC si aspettano bersagli carta marroni e bersagli metallo bianchi. I no-shoot dovrebbero essere di colore costante e diverso (es. giallo).

**❌ Tipi di bersagli mancanti:**
- **Popper** (calibrato PF 120-125): il modello ha solo STEEL_TARGET generico. Manca distinzione Popper vs Piatto.
- **Mini Target / Micro Target**: dimensioni fisse 0.45×0.45m per tutti i paper. Il regolamento prevede formati ridotti (Appendice B3).
- **Hard Cover**: non esiste come ItemType. Il regolamento richiede che l'Hard Cover sia realizzato con materiali impenetrabili (Regola 4.1.4.1).
- **Soft Cover**: non esiste come ItemType (Regola 4.1.4.2).
- **Cooper Tunnel**: non implementato (Regola 2.2.5).

#### 3. `models.py` (modelli dati)

**✅ Presente:** 10 ItemType (WALL, PAPER_TARGET, STEEL_TARGET, FAULT_LINE, NO_SHOOT, BARRIER, DOOR, SWINGER, DROP_TURNER, MOVER)

**❌ Mancante:**
- `POPPER` / `METAL_PLATE` — distinzione tra popper calibrati e piatti non calibrati
- `MINI_TARGET` / `MICRO_TARGET` — formati ridotti
- `HARD_COVER` / `SOFT_COVER` — tipi di copertura
- `COOPER_TUNNEL` — struttura tunnel
- `SHOOTING_POSITION` ha `is_start` ma mancano: `mandatory_reload` (Regola 1.1.5.2), `strong_hand_only` / `weak_hand_only` (Regola 1.1.5.3)
- `Stage` manca: `course_type` (short/medium/long), `division_requirements`, `match_level` (I-V)

### Regole non coperte (fuori scope di OpenTDS)

Queste sono regole che OpenTDS, in quanto generatore/editor di stage, non può o non deve implementare:

| Regola | Motivazione |
|---|---|
| Sez. 3: Briefing scritto | Potrebbe essere generato come output, ma non è implementato |
| Sez. 5: Equipaggiamento tiratori | Non pertinente (riguarda il tiratore, non lo stage) |
| Sez. 6: Struttura di gara | Gestione competizione, non progettazione |
| Sez. 7: Giudici di Gara | Personale, non progettuale |
| Sez. 8: Comandi di gara | Procedura esecuzione, non progettazione |
| Sez. 9: Punteggio Comstock | Potrebbe essere simulato, ma non è l'obiettivo primario |
| Sez. 11: Arbitraggio | Non pertinente |
| Sez. 12: Glossario | Documentazione, non codice |

Tuttavia, alcune di queste potrebbero diventare **feature future** (es. generazione automatica del briefing, simulazione hit factor, validazione division-compatibility).

### Priorità di remediation

### Stato correzioni applicate (2026-07-09)

**Bugfix UI:**
- Menu "Genera → Genera Stage IPSC" ora porta in primo piano il dock (`raise_()`)
- `_replace_stage` ora copia `course_type` e `division` dallo stage generato
- Aggiunte tutte le 6 classi grafiche mancanti per i nuovi ItemType (Popper, MetalPlate, MiniTarget, MicroTarget, HardCover, SoftCover) — 16/16 tipi renderizzabili

| Priorità | Cosa | Stato |
|---|---|---|
| **P0** | **Colori bersagli conformi** (marrone paper, bianco steel) | ✅ **FATTO** — #8B4513 e #d1d5db |
| **P0** | **No-Shoot colore giallo** (diverso da paper/steel) | ✅ **FATTO** — #eab308 |
| **P0** | **Colori bersagli mobili** come carta (marrone) | ✅ **FATTO** — tonalità marroni (#A0522D, #8B6914, #CD853F) |
| **P1** | **Max 9 colpi da singola posizione** nel validator | ✅ **FATTO** — `_validate_max_hits_per_position()` |
| **P1** | **Distanza metallici 7m** nel validator | ✅ **FATTO** — `_validate_steel_distance()` |
| **P1** | **Angoli di sicurezza 90°** — validazione geometrica | ✅ **FATTO** — `_validate_safety_angles()` |
| P2 | **Classificazione esercizio** (Short/Medium/Long) + validazione | ✅ **FATTO** — CourseType enum, `_validate_course_type()` |
| P2 | **Tipi Popper/Piatto, Mini/Micro Target** nei modelli | ✅ **FATTO** — 6 nuovi ItemType, factory UI, 3D, export |
| P2 | **Hard Cover / Soft Cover** come ItemType | ✅ **FATTO** — con proprietà impenetrabile/visiva |
| P3 | **Validazione per Divisione** (ottiche, compensatori, canna) | ✅ **FATTO** — `_validate_division()`, costanti Division |
| P3 | **Rapporto 3:2:1** nel generatore | ✅ **FATTO** — `MatchValidator` con validazione multi-stage |
| P3 | **Generazione briefing** in output PDF | ✅ **FATTO** — pagina briefing nell'esportazione PDF |

### Conclusione

OpenTDS ha un'architettura solida per la validazione geometrica (OBB con Shapely) e la generazione procedurale. Le lacune principali sono:

1. **Cromatiche** (facili da risolvere) — colori non conformi per paper, steel, no-shoot
2. **Tipologiche** (sforzo medio) — mancano tipi specifici (popper, mini target, hard cover)
3. **Regolamentari** (sforzo medio-alto) — max colpi per posizione, angoli sicurezza, distanza metallici nel validator
4. **Strutturali** (sforzo alto) — classificazione esercizi, validazione division, rapporto 3:2:1

Il motore regole (`IPSCRulesEngine`) è ben progettato e può essere esteso con relativa facilità per colmare le lacune identificate.

## Evidence used

- **Regolamento IPSC Handgun Ed. Gennaio 2024**: Sezioni 1, 2, 4, 8.1, 9, 10, Appendici A4, B, C, D ([[sources/SRC-2026-07-09-001|SRC-2026-07-09-001]])
- **Codice OpenTDS**:
  - `core/ipsc_rules.py` — motore di validazione ([[concepts/ipsc-stage-design]])
  - `core/generator.py` — generatore procedurale
  - `core/models.py` — modelli dati (ItemType, Stage, StageItem)
  - `core/collision.py` — collision detection Shapely
  - `core/geometry.py` — helper geometrici
  - `tests/test_ipsc_rules.py` — test validazione
  - `tests/test_generator.py` — test generatore
- **Wiki**: [[concepts/ipsc-stage-design]], [[concepts/ipsc-targets]], [[concepts/ipsc-scoring]], [[concepts/ipsc-divisions]], [[concepts/ipsc-safety-rules]], [[concepts/ipsc-penalties]], [[concepts/ipsc-range-commands]], [[entities/ipsc]], [[syntheses/opentds-ipsc-compliance]]

## Follow-up opportunities

1. Implementare le correzioni P0 (colori) e P1 (distanza metallici nel validator, max colpi per posizione, angoli sicurezza)
2. Estendere i modelli con i tipi mancanti (Popper, Mini Target, Hard Cover)
3. Aggiungere la classificazione Short/Medium/Long Course
4. Integrare la generazione del briefing scritto nell'esportazione PDF
5. Validare gli stage generati contro le regole di Divisione

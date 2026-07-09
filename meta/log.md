# OpenTDS Wiki Log

## [2026-07-09 13:18 UTC] capture | Captured Regolamento IPSC — Edizione corrente
- Sources: [[sources/SRC-2026-07-09-001|SRC-2026-07-09-001]]
- Pages: [[sources/SRC-2026-07-09-001]]
- Notes: inputType=file

## [2026-07-09 13:19 UTC] refactor | Created entity page IPSC
- Pages: [[entities/ipsc]]

## [2026-07-09 13:19 UTC] refactor | Created entity page FITDS
- Pages: [[entities/fitds]]

## [2026-07-09 13:19 UTC] refactor | Created entity page IROA
- Pages: [[entities/iroa]]

## [2026-07-09 13:19 UTC] refactor | Created concept page IPSC Targets
- Pages: [[concepts/ipsc-targets]]

## [2026-07-09 13:19 UTC] refactor | Created concept page IPSC Stage Design
- Pages: [[concepts/ipsc-stage-design]]

## [2026-07-09 13:19 UTC] refactor | Created concept page IPSC Scoring
- Pages: [[concepts/ipsc-scoring]]

## [2026-07-09 13:19 UTC] refactor | Created concept page IPSC Divisions
- Pages: [[concepts/ipsc-divisions]]

## [2026-07-09 13:19 UTC] refactor | Created concept page IPSC Penalties
- Pages: [[concepts/ipsc-penalties]]

## [2026-07-09 13:19 UTC] refactor | Created concept page IPSC Safety Rules
- Pages: [[concepts/ipsc-safety-rules]]

## [2026-07-09 13:19 UTC] refactor | Created concept page IPSC Range Commands
- Pages: [[concepts/ipsc-range-commands]]

## [2026-07-09 13:19 UTC] refactor | Created synthesis page OpenTDS IPSC Compliance
- Pages: [[syntheses/opentds-ipsc-compliance]]

## [2026-07-09 13:21 UTC] integrate | Integrato Regolamento IPSC Handgun Ed. 2024
- Summary: Catturato e integrato il Regolamento IPSC Handgun Edizione Gennaio 2024 (PDF). Creata pagina sorgente SRC-2026-07-09-001, 3 entità (IPSC, FITDS, IROA), 7 concetti (Stage Design, Targets, Scoring, Divisions, Safety Rules, Penalties, Range Commands), 1 sintesi (OpenTDS IPSC Compliance).
- Sources: [[sources/SRC-2026-07-09-001|SRC-2026-07-09-001]]
- Pages: [[sources/SRC-2026-07-09-001]], [[entities/ipsc]], [[entities/fitds]], [[entities/iroa]], [[concepts/ipsc-stage-design]], [[concepts/ipsc-targets]], [[concepts/ipsc-scoring]], [[concepts/ipsc-divisions]], [[concepts/ipsc-safety-rules]], [[concepts/ipsc-penalties]], [[concepts/ipsc-range-commands]], [[syntheses/opentds-ipsc-compliance]]

## [2026-07-09 13:22 UTC] refactor | Created analysis page Analisi conformità OpenTDS al Regolamento IPSC Handgun 2024
- Pages: [[analyses/2026-07-09-analisi-conformita-opentds-al-regolamento-ipsc-handgun-2024]]

## [2026-07-09 13:23 UTC] file-analysis | Analisi conformità OpenTDS vs Regolamento IPSC 2024
- Summary: Analisi completa del codice OpenTDS (ipsc_rules.py, generator.py, models.py, collision.py, geometry.py, test files) contro il Regolamento IPSC Handgun Ed. 2024. Identificate 3 aree prioritarie: colori bersagli non conformi (P0), vincoli mancanti nel validator (P1), estensione modelli (P2).
- Sources: [[sources/SRC-2026-07-09-001|SRC-2026-07-09-001]]
- Pages: [[analyses/2026-07-09-analisi-conformita-opentds-al-regolamento-ipsc-handgun-2024]], [[syntheses/opentds-ipsc-compliance]]

## [2026-07-09 13:28 UTC] refactor | Corrette non conformità P0 e P1 codice OpenTDS
- Summary: Implementate correzioni: (P0) colori bersagli IPSC-conformi — paper marrone #8B4513, steel grigio #d1d5db, no-shoot giallo #eab308, mobili in tonalità marroni. (P1) Aggiunte validazioni: distanza metallici 7m (Reg. 2.1.3), max 9 colpi per posizione (Reg. 1.2.1), angoli sicurezza 90° (Reg. 2.1.2) in IPSCRulesEngine. File: core/generator.py, core/ipsc_rules.py, ui/editor/stage_scene.py, services/exporter.py, README.md. 119 test passano.
- Sources: [[sources/SRC-2026-07-09-001|SRC-2026-07-09-001]]
- Pages: [[analyses/2026-07-09-analisi-conformita-opentds-al-regolamento-ipsc-handgun-2024]]

## [2026-07-09 13:38 UTC] refactor | Implementate correzioni P2 e P3 — tipi, validazioni, briefing
- Summary: P2: Aggiunti 6 nuovi ItemType (POPPER, METAL_PLATE, MINI_TARGET, MICRO_TARGET, HARD_COVER, SOFT_COVER), CourseType enum (Short/Medium/Long), Division enum. Validazione corso e divisione in IPSCRulesEngine. MatchValidator con rapporto 3:2:1. P3: Generazione briefing PDF conforme Sez. 3.2. UI: generator panel esteso con corso/divisione. 119 test passano.
- Sources: [[sources/SRC-2026-07-09-001|SRC-2026-07-09-001]]
- Pages: [[analyses/2026-07-09-analisi-conformita-opentds-al-regolamento-ipsc-handgun-2024]]

## [2026-07-09 13:48 UTC] refactor | Bugfix menu Genera e classi grafiche mancanti
- Summary: Fix: menu 'Genera Stage IPSC' ora chiama raise_() sul dock; _replace_stage copia course_type/division; aggiunte 6 classi grafiche mancanti per nuovi ItemType (PopperGraphicsItem, MetalPlateGraphicsItem, MiniTargetGraphicsItem, MicroTargetGraphicsItem, HardCoverGraphicsItem, SoftCoverGraphicsItem) — tutti i 16 tipi IPSC sono ora renderizzabili nell'editor 2D.
- Pages: [[analyses/2026-07-09-analisi-conformita-opentds-al-regolamento-ipsc-handgun-2024]], [[ui/main_window.py]], [[ui/editor/stage_scene.py]]

## [2026-07-09 14:27 UTC] refactor | Generatore produce stage senza violazioni IPSC
- Summary: Riscritto il core della generazione: _generate_once produce lo stage, generate() loop con riparazione mirata delle violazioni. _add_restrictive_walls usa le stesse posizioni del validatore. Aggiunte riparazioni per: backstop, max colpi/posizione, bersagli insufficienti, muri troppo vicini, ostacoli sovrapposti, angoli sicurezza. 9/9 configurazioni testate → zero violazioni.
- Pages: [[core/generator.py]], [[core/ipsc_rules.py]]

---
id: synthesis-opentds-ipsc-compliance
type: synthesis
title: OpenTDS IPSC Compliance
aliases:
  - conformità IPSC di OpenTDS
  - OpenTDS regole IPSC
tags:
  - OpenTDS
  - IPSC
  - conformità
  - implementazione
status: draft
updated: '2026-07-09'
source_ids:
  - SRC-2026-07-09-001
summary: Analisi di come OpenTDS implementa le regole IPSC Handgun Edition 2024
---
# OpenTDS IPSC Compliance

## Current thesis

OpenTDS implementa un motore di vincoli geometrici IPSC e un editor 2D per la progettazione di stage. La conformità al regolamento IPSC Handgun Ed. 2024 è parziale: copre i vincoli geometrici di base ma ha margini di miglioramento su regole procedurali, scoring completo e validazione avanzata.

## Why this seems true

### Vincoli geometrici implementati (da `core/generator.py`)
| Vincolo OpenTDS | Regola IPSC | Note |
|---|---|---|
| Distanza bersaglio-bordo stage ≥1.0m | Sez. 2.1 (implicito) | Desunto da principi di sicurezza |
| Distanza bersaglio-muro ≥0.8m | Sez. 2.1 (implicito) | — |
| Distanza bersaglio-bersaglio ≥0.8m | — | Non esplicitamente nel regolamento ma buona pratica |
| Distanza bersaglio-barriera ≥0.5m | — | — |
| Angoli di sicurezza 90° default | Regola 2.1.2 | Implementato? Da verificare |
| Fault lines (linee rosse, ≥2cm, ≥1.5m) | Regola 2.2.1.4 | Parziale |
| Barriere ≥1.8m | Regola 2.2.3.1 | — |
| Max 9 colpi da singola posizione | Regola 1.2.1.1-1.2.1.3 | Non implementato nel generatore? |

### Tipi di bersagli supportati
OpenTDS supporta: Paper Target, Steel Target, Swinger, Drop Turner, Mover — che coprono i principali tipi IPSC ma con denominazioni e codici colore propri (non necessariamente conformi ai colori ufficiali IPSC: marrone per carta, bianco per metallo).

### Classi di esercizi
- Short Course (≤12 colpi) — supportato
- Medium Course (≤24 colpi) — supportato
- Long Course (≤32 colpi) — supportato
- Rapporto 3:2:1 — non enforce dal generatore

### Scoring
- Sistema Comstock: non implementato (OpenTDS è un generatore/editor, non un sistema di scoring)
- Power Factor: non implementato

## Counterevidence / disagreement

- **Colori bersagli**: Il regolamento richiede zona punti marrone per carta (Regola 4.1.2.1) e bianco per metallo. OpenTDS usa: rosso per Paper, blu per Steel, viola per Swinger, verde per Drop Turner, arancione per Mover. **Non conforme**.
- **No-Shoot**: OpenTDS non ha un tipo esplicito "No-Shoot" nella lista ItemType.
- **Mini/Micro Targets**: non implementati.
- **Hard Cover / Soft Cover**: non implementati come tipi di copertura.
- **Popper con calibrazione**: non implementata logica di calibrazione PF.
- **Piatti metallici**: non implementati come tipo separato.
- **Vincoli procedurali**: il generatore non considera regole come "non più del 25% degli esercizi con arma scarica" o "condizioni di pronto per Divisione".

## Decision boundary

OpenTDS è **un tool di progettazione/generazione**, non un sistema di validazione o scoring. La conformità va valutata su:
- **Generazione**: i layout generati rispettano i vincoli geometrici IPSC? ✅ Parziale
- **Editor**: permette di progettare stage conformi? ✅ Sì, con limitazioni
- **Validazione**: avvisa l'utente se lo stage viola regole IPSC? ❌ Non implementato
- **Scoring**: calcola hit factor? ❌ Non in scope
- **Esportazione**: produce output conformi? ✅ JSON schema proprietario, PNG/PDF

## Unknowns

- Il codice del constraint engine (`core/ipsc_rules.py`) non è stato ancora esaminato nel dettaglio.
- La conformità esatta dei vincoli di distanza (1.0, 0.8, 0.5 m) con i valori impliciti del regolamento non è verificata.
- La generazione procedurale considera il rapporto 3:2:1 tra i tipi di esercizio? Da verificare.

## Related pages
- [[concepts/ipsc-stage-design]]
- [[concepts/ipsc-targets]]
- [[concepts/ipsc-scoring]]
- [[concepts/ipsc-divisions]]
- [[concepts/ipsc-safety-rules]]
- [[concepts/ipsc-penalties]]
- [[concepts/ipsc-range-commands]]
- [[entities/ipsc]]
- [[entities/fitds]]
- [[analyses/2026-07-09-analisi-conformita-opentds-al-regolamento-ipsc-handgun-2024]]
- [[sources/SRC-2026-07-09-001]]

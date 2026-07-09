---
id: concept-ipsc-scoring
type: concept
title: IPSC Scoring
aliases:
  - punteggio IPSC
  - Comstock scoring
  - Power Factor IPSC
  - hit factor
tags:
  - IPSC
  - punteggio
  - scoring
  - Power Factor
status: draft
updated: '2026-07-09'
source_ids:
  - SRC-2026-07-09-001
summary: >-
  Sistema di punteggio Comstock, Power Factor (Major/Minor) e regole di
  conteggio IPSC
---
# IPSC Scoring

## Current understanding

### Sistema Comstock (Regola 9.2.1)
Metodo di punteggio standard IPSC:
- Tempo illimitato (si arresta all'ultimo colpo)
- Numero illimitato di colpi sparabili
- Numero fissato di colpi a segno conteggiati per bersaglio
- **Hit Factor** = (Punti totali - Penalità) / Tempo (con 2 decimali)
- Il tiratore con hit factor più alto ottiene il punteggio massimo teorico dell'esercizio; gli altri in percentuale.

### Power Factor (Sezione 5.6)
**Formula**: PF = (peso palla in grains × velocità media in fps) / 1000

**Soglie**:
| Divisione | Minor PF | Major PF |
|---|---|---|
| Open | ≥125 | ≥160 |
| Standard | ≥125 | ≥170 |
| Classic | ≥125 | ≥170 |
| Production | ≥125 | — (solo Minor) |
| Production Optics | ≥125 | — (solo Minor) |
| Revolver | ≥125 | ≥170 (ma ≥7 colpi = solo Minor) |

**Test munizioni**: 8 cartucce prelevate, 1 pesata, 3 sparate; se insufficiente, ricalcolo con 3 più alte su 6; se ancora insufficiente, opzioni con 7a cartuccia (Regola 5.6.3).

### Valori punti (Appendici B, C)
**Bersagli cartacei** (Minor / Major PF):
| Zona | Minor | Major |
|---|---|---|
| A | 5 | 5 |
| C | 3 | 4 |
| D | 1 | 2 |

**Bersagli metallici**: 5 o 10 punti a seconda della zona colpita.

### Penalità (Section 9.4)
- **Miss**: -10 punti per colpo mancante (default: 2 per carta, 1 per metallico)
- **No-Shoot**: -10 punti per colpo, max 2 per bersaglio
- **Errore di procedura**: -10 punti ciascuno (Sezione 10.1)
- **Punteggio minimo esercizio**: zero (Regola 9.5.5)

### Default ingaggio (Regola 9.5.1)
- Bersagli carta: minimo 1 colpo, i 2 migliori contano
- Bersagli metallici: minimo 1 colpo, deve cadere

## Key distinctions

- **Comstock vs altri metodi**: Comstock è il metodo standard; esistono esercizi di classificazione con procedure specifiche.
- **Minor vs Major**: Major PF dà 4 punti in zona C (vs 3) e 2 in zona D (vs 1). Solo Open, Standard, Classic, Revolver possono usare Major.
- **Hit Factor**: formula che bilancia precisione, potenza e velocità (DVC).

## Supporting evidence

- Sezioni 5.6, 9 e Appendici B, C, D del Regolamento IPSC Handgun ([[sources/SRC-2026-07-09-001|SRC-2026-07-09-001]]).

## Tensions / caveats

- Il valore delle zone per Major PF su bersagli metallici (5 o 10) dipende dal tipo di bersaglio e dalla zona colpita.
- Il regolamento precisa: il risultato finale del PF ignora tutte le cifre decimali (124.9999 = 124, non 125).

## Open questions

- 

## Related pages
- [[concepts/ipsc-stage-design]]
- [[concepts/ipsc-targets]]
- [[concepts/ipsc-divisions]]
- [[concepts/ipsc-penalties]]
- [[syntheses/opentds-ipsc-compliance]]

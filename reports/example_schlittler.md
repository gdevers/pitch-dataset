# Pitch Arsenal Optimization Report

_Trained/scored on MLB 2026 pitches (2026-04-01 → 2026-05-15, n=175,759). Parquet data is local/gitignored; model artifact may be committed._

Recommendations compare **actual usage** to a constrained optimal mix that minimizes predicted pitch-level xwOBA (lower is better for the pitcher), holding location/count/TTO/context fixed and only reallocating pitch-type share.

## Schlittler, Cam (MLBAM 693645)

- Pitches modeled: **804**
- Arsenal: FF, FC, SI, CU
- Overall expected xwOBA: 0.269 → 0.267 (improvement **-0.002**)
- Overall expected RV/pitch: -0.0027 → -0.0034 (-0.0007)

### Platoon usage

#### vs LHH

Expected improvement: **-0.002 xwOBA** (0.272 → 0.270); n=522

- INCREASE **CU** usage from 9% → 24%
- REDUCE **FF** usage from 55% → 40%
- REDUCE **SI** usage from 11% → 3%
- INCREASE **FC** usage from 25% → 32%

#### vs RHH

Expected improvement: **-0.001 xwOBA** (0.262 → 0.261); n=282

- INCREASE **FC** usage from 31% → 46%
- REDUCE **SI** usage from 35% → 20%

### Count / situation detail

**vs RHH | ahead_pit** (97 pitches)

Expected improvement: **-0.001 xwOBA** (0.267 → 0.266); n=97

- INCREASE **FC** usage from 29% → 44%
- REDUCE **SI** usage from 32% → 17%

**vs LHH | ahead_pit** (175 pitches)

Expected improvement: **-0.001 xwOBA** (0.289 → 0.288); n=175

- REDUCE **FF** usage from 55% → 40%
- INCREASE **CU** usage from 17% → 32%
- INCREASE **FC** usage from 22% → 26%
- REDUCE **SI** usage from 6% → 3%

**vs LHH | even** (109 pitches)

Expected improvement: **-0.001 xwOBA** (0.256 → 0.255); n=109

- INCREASE **FC** usage from 29% → 44%
- REDUCE **SI** usage from 14% → 3%
- REDUCE **FF** usage from 53% → 49%

**vs LHH | ahead_hit** (77 pitches)

Expected improvement: **-0.001 xwOBA** (0.258 → 0.257); n=77

- INCREASE **FC** usage from 34% → 49%
- REDUCE **SI** usage from 16% → 3%
- REDUCE **FF** usage from 51% → 48%

**vs RHH | 0-0** (79 pitches)

Expected improvement: **-0.001 xwOBA** (0.246 → 0.245); n=79

- INCREASE **FC** usage from 22% → 37%
- REDUCE **SI** usage from 42% → 27%

**vs LHH | 0-0** (129 pitches)

Expected improvement: **-0.001 xwOBA** (0.272 → 0.271); n=129

- REDUCE **FF** usage from 64% → 49%
- INCREASE **CU** usage from 12% → 27%
- INCREASE **FC** usage from 16% → 22%
- REDUCE **SI** usage from 9% → 3%

### Arsenal pairing signals

- FC vs primary FF: velo sep 3.9 mph, move sep 1.1 in, release strong tunnel (0.11 ft)
- SI vs primary FF: velo sep 0.6 mph, move sep 0.9 in, release strong tunnel (0.04 ft)
- CU vs primary FF: velo sep 13.4 mph, move sep 2.5 in, release strong tunnel (0.09 ft)

# Pitch Arsenal Optimization Report

_Trained/scored on MLB 2026 pitches (2026-03-25 → 2026-08-13, n=491,230). Parquet data is local/gitignored; model artifact may be committed._

Recommendations compare **actual usage** to a constrained optimal mix that minimizes predicted pitch-level xwOBA (lower is better for the pitcher), holding location/count/TTO/context fixed and only reallocating pitch-type share.

## Schlittler, Cam (MLBAM 693645)

- Pitches modeled: **2,083**
- Arsenal: FF, FC, SI, CU
- Overall expected xwOBA: 0.275 → 0.273 (improvement **-0.002**)
- Overall expected RV/pitch: -0.0010 → -0.0012 (-0.0002)

### Platoon usage

#### vs LHH

Expected improvement: **-0.002 xwOBA** (0.278 → 0.276); n=1343

- REDUCE **FF** usage from 49% → 34%
- INCREASE **CU** usage from 11% → 26%
- INCREASE **FC** usage from 26% → 37%
- REDUCE **SI** usage from 14% → 3%

#### vs RHH

Expected improvement: **-0.001 xwOBA** (0.269 → 0.267); n=740

- REDUCE **SI** usage from 33% → 18%
- INCREASE **FC** usage from 26% → 41%

### Count / situation detail

**vs LHH | full** (76 pitches)

Expected improvement: **-0.004 xwOBA** (0.323 → 0.320); n=76

- REDUCE **FF** usage from 43% → 28%
- INCREASE **CU** usage from 9% → 24%
- INCREASE **FC** usage from 30% → 44%
- REDUCE **SI** usage from 17% → 3%

**vs LHH | even** (322 pitches)

Expected improvement: **-0.003 xwOBA** (0.275 → 0.272); n=322

- REDUCE **FF** usage from 42% → 27%
- INCREASE **CU** usage from 10% → 25%
- INCREASE **FC** usage from 31% → 45%
- REDUCE **SI** usage from 17% → 3%

**vs RHH | even** (171 pitches)

Expected improvement: **-0.002 xwOBA** (0.278 → 0.276); n=171

- REDUCE **SI** usage from 33% → 18%
- INCREASE **CU** usage from 6% → 21%
- REDUCE **FF** usage from 28% → 13%
- INCREASE **FC** usage from 33% → 48%

**vs LHH | 0-0** (332 pitches)

Expected improvement: **-0.002 xwOBA** (0.272 → 0.270); n=332

- INCREASE **CU** usage from 11% → 26%
- REDUCE **FF** usage from 56% → 41%
- REDUCE **SI** usage from 13% → 3%
- INCREASE **FC** usage from 20% → 30%

**vs LHH | ahead_pit** (423 pitches)

Expected improvement: **-0.002 xwOBA** (0.291 → 0.289); n=423

- INCREASE **CU** usage from 16% → 31%
- REDUCE **FF** usage from 53% → 38%
- INCREASE **FC** usage from 21% → 28%
- REDUCE **SI** usage from 10% → 3%

**vs RHH | ahead_pit** (229 pitches)

Expected improvement: **-0.002 xwOBA** (0.280 → 0.279); n=229

- REDUCE **SI** usage from 27% → 12%
- INCREASE **CU** usage from 5% → 20%
- INCREASE **FF** usage from 41% → 55%
- REDUCE **FC** usage from 27% → 13%

### Arsenal pairing signals

- FC vs primary FF: velo sep 3.3 mph, move sep 1.1 in, release strong tunnel (0.09 ft)
- SI vs primary FF: velo sep 0.2 mph, move sep 0.9 in, release strong tunnel (0.06 ft)
- CU vs primary FF: velo sep 11.8 mph, move sep 2.4 in, release strong tunnel (0.10 ft)

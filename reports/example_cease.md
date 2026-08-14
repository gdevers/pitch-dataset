# Pitch Arsenal Optimization Report

_Trained/scored on MLB 2026 pitches (2026-03-25 → 2026-08-13, n=491,230). Parquet data is local/gitignored; model artifact may be committed._

Recommendations compare **actual usage** to a constrained optimal mix that minimizes predicted pitch-level xwOBA (lower is better for the pitcher), holding location/count/TTO/context fixed and only reallocating pitch-type share.

## Cease, Dylan (MLBAM 656302)

- Pitches modeled: **2,069**
- Arsenal: FF, SL, CH, KC, SI, ST
- Overall expected xwOBA: 0.286 → 0.280 (improvement **-0.006**)
- Overall expected RV/pitch: +0.0057 → +0.0036 (-0.0021)

### Platoon usage

#### vs LHH

Expected improvement: **-0.005 xwOBA** (0.290 → 0.285); n=1198

- INCREASE **SL** usage from 24% → 39%
- INCREASE **KC** usage from 12% → 27%
- REDUCE **FF** usage from 39% → 24%
- REDUCE **CH** usage from 19% → 6%
- REDUCE **SI** usage from 6% → 3%

#### vs RHH

Expected improvement: **-0.008 xwOBA** (0.280 → 0.273); n=871

- INCREASE **ST** usage from 9% → 24%
- INCREASE **KC** usage from 6% → 21%
- REDUCE **FF** usage from 33% → 18%
- REDUCE **SI** usage from 13% → 3%
- REDUCE **SL** usage from 38% → 33%

### Count / situation detail

**vs RHH | 0-0** (216 pitches)

Expected improvement: **-0.008 xwOBA** (0.260 → 0.252); n=216

- REDUCE **FF** usage from 27% → 12%
- REDUCE **SI** usage from 19% → 4%
- INCREASE **ST** usage from 14% → 29%
- INCREASE **SL** usage from 28% → 43%

**vs RHH | even** (203 pitches)

Expected improvement: **-0.007 xwOBA** (0.286 → 0.279); n=203

- REDUCE **FF** usage from 37% → 22%
- INCREASE **ST** usage from 7% → 22%
- REDUCE **SI** usage from 12% → 3%
- INCREASE **SL** usage from 37% → 47%

**vs RHH | ahead_pit** (276 pitches)

Expected improvement: **-0.007 xwOBA** (0.294 → 0.287); n=276

- REDUCE **FF** usage from 31% → 16%
- INCREASE **ST** usage from 9% → 24%
- INCREASE **SL** usage from 44% → 51%
- REDUCE **SI** usage from 10% → 3%

**vs LHH | full** (94 pitches)

Expected improvement: **-0.007 xwOBA** (0.346 → 0.339); n=94

- REDUCE **FF** usage from 51% → 36%
- INCREASE **SL** usage from 35% → 50%

**vs LHH | ahead_pit** (352 pitches)

Expected improvement: **-0.006 xwOBA** (0.302 → 0.295); n=352

- INCREASE **SL** usage from 24% → 39%
- REDUCE **FF** usage from 36% → 21%
- INCREASE **KC** usage from 9% → 24%
- REDUCE **CH** usage from 23% → 13%
- REDUCE **SI** usage from 7% → 3%

**vs RHH | ahead_hit** (117 pitches)

Expected improvement: **-0.006 xwOBA** (0.272 → 0.266); n=117

- INCREASE **KC** usage from 9% → 24%
- REDUCE **FF** usage from 34% → 19%
- REDUCE **SI** usage from 13% → 3%
- INCREASE **SL** usage from 39% → 49%

### Arsenal pairing signals

- SL vs primary FF: velo sep 8.3 mph, move sep 1.3 in, release strong tunnel (0.15 ft)
- CH vs primary FF: velo sep 15.0 mph, move sep 0.5 in, release strong tunnel (0.10 ft)
- KC vs primary FF: velo sep 15.0 mph, move sep 2.7 in, release strong tunnel (0.06 ft)
- SI vs primary FF: velo sep 1.3 mph, move sep 0.8 in, release strong tunnel (0.16 ft)
- ST vs primary FF: velo sep 13.7 mph, move sep 2.6 in, release moderate tunnel (0.38 ft)

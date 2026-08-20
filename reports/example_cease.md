# Pitch Arsenal Optimization Report

_Trained/scored on MLB 2026 pitches (2026-03-25 → 2026-08-13, n=491,230). Parquet data is local/gitignored; model artifact may be committed._

Recommendations compare **actual usage** to a constrained optimal mix that minimizes predicted pitch-level xwOBA (lower is better for the pitcher), holding location/count/TTO/context fixed and only reallocating pitch-type share.

## Cease, Dylan (MLBAM 656302)

- Pitches modeled: **2,069**
- Arsenal: FF, SL, CH, KC, SI, ST
- Overall expected xwOBA: 0.283 → 0.279 (improvement **-0.004**)
- Overall expected RV/pitch: +0.0044 → +0.0017 (-0.0027)

### Platoon usage

#### vs LHH

Expected improvement: **-0.003 xwOBA** (0.289 → 0.286); n=1198

- REDUCE **FF** usage from 39% → 24%
- INCREASE **SL** usage from 24% → 39%
- INCREASE **KC** usage from 12% → 27%
- REDUCE **CH** usage from 19% → 6%
- REDUCE **SI** usage from 6% → 3%

#### vs RHH

Expected improvement: **-0.006 xwOBA** (0.276 → 0.270); n=871

- INCREASE **SL** usage from 38% → 53%
- REDUCE **FF** usage from 33% → 18%
- INCREASE **ST** usage from 9% → 22%
- REDUCE **SI** usage from 13% → 3%
- REDUCE **KC** usage from 6% → 3%

### Count / situation detail

**vs RHH | 0-0** (216 pitches)

Expected improvement: **-0.008 xwOBA** (0.261 → 0.253); n=216

- INCREASE **SL** usage from 28% → 43%
- INCREASE **ST** usage from 14% → 29%
- REDUCE **FF** usage from 27% → 12%
- REDUCE **SI** usage from 19% → 4%

**vs LHH | full** (94 pitches)

Expected improvement: **-0.005 xwOBA** (0.331 → 0.327); n=94

- INCREASE **SL** usage from 35% → 50%
- REDUCE **FF** usage from 51% → 43%
- REDUCE **SI** usage from 10% → 3%

**vs RHH | ahead_pit** (276 pitches)

Expected improvement: **-0.004 xwOBA** (0.287 → 0.282); n=276

- REDUCE **FF** usage from 31% → 16%
- INCREASE **ST** usage from 9% → 20%
- INCREASE **SL** usage from 44% → 55%
- REDUCE **SI** usage from 10% → 3%

**vs LHH | ahead_pit** (352 pitches)

Expected improvement: **-0.004 xwOBA** (0.304 → 0.300); n=352

- INCREASE **SL** usage from 24% → 39%
- INCREASE **KC** usage from 9% → 24%
- REDUCE **FF** usage from 36% → 21%
- REDUCE **CH** usage from 23% → 13%
- REDUCE **SI** usage from 7% → 3%

**vs LHH | ahead_hit** (188 pitches)

Expected improvement: **-0.004 xwOBA** (0.283 → 0.279); n=188

- REDUCE **FF** usage from 42% → 27%
- INCREASE **SL** usage from 27% → 42%
- INCREASE **KC** usage from 9% → 23%
- REDUCE **CH** usage from 18% → 3%

**vs RHH | ahead_hit** (117 pitches)

Expected improvement: **-0.003 xwOBA** (0.264 → 0.261); n=117

- REDUCE **FF** usage from 34% → 19%
- INCREASE **SL** usage from 39% → 54%
- INCREASE **KC** usage from 9% → 18%
- REDUCE **SI** usage from 13% → 3%

### Arsenal pairing signals

- SL vs primary FF: velo sep 8.3 mph, move sep 1.3 in, eff speed sep 8.1 mph, spin sep 243 rpm, spin axis sep 66°, arm angle sep 2.3°, extension sep 0.05 ft, API break sep 1.8 in, release strong tunnel (0.15 ft)
- CH vs primary FF: velo sep 15.0 mph, move sep 0.5 in, eff speed sep 14.6 mph, spin sep 706 rpm, spin axis sep 4°, arm angle sep 6.9°, extension sep 0.15 ft, API break sep 1.4 in, release strong tunnel (0.18 ft)
- KC vs primary FF: velo sep 15.0 mph, move sep 2.7 in, eff speed sep 15.1 mph, spin sep 225 rpm, spin axis sep 172°, arm angle sep 3.2°, extension sep 0.04 ft, API break sep 3.7 in, release strong tunnel (0.07 ft)
- SI vs primary FF: velo sep 1.3 mph, move sep 0.8 in, eff speed sep 1.2 mph, spin sep 72 rpm, spin axis sep 4°, arm angle sep 2.1°, extension sep 0.01 ft, API break sep 0.9 in, release strong tunnel (0.16 ft)
- ST vs primary FF: velo sep 13.7 mph, move sep 2.6 in, eff speed sep 14.1 mph, spin sep 374 rpm, spin axis sep 161°, arm angle sep 5.5°, extension sep 0.11 ft, API break sep 3.4 in, release moderate tunnel (0.40 ft)

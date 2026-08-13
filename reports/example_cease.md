# Pitch Arsenal Optimization Report

_Trained/scored on MLB 2026 pitches (2026-04-01 → 2026-05-15, n=175,759). Parquet data is local/gitignored; model artifact may be committed._

Recommendations compare **actual usage** to a constrained optimal mix that minimizes predicted pitch-level xwOBA (lower is better for the pitcher), holding location/count/TTO/context fixed and only reallocating pitch-type share.

## Cease, Dylan (MLBAM 656302)

- Pitches modeled: **814**
- Arsenal: FF, SL, CH, SI, KC, ST
- Overall expected xwOBA: 0.289 → 0.283 (improvement **-0.006**)
- Overall expected RV/pitch: +0.0052 → +0.0029 (-0.0023)

### Platoon usage

#### vs LHH

Expected improvement: **-0.004 xwOBA** (0.289 → 0.284); n=468

- INCREASE **CH** usage from 20% → 35%
- INCREASE **KC** usage from 12% → 27%
- REDUCE **FF** usage from 37% → 22%
- REDUCE **SL** usage from 23% → 11%
- REDUCE **SI** usage from 6% → 3%

#### vs RHH

Expected improvement: **-0.007 xwOBA** (0.289 → 0.282); n=346

- REDUCE **FF** usage from 34% → 19%
- INCREASE **ST** usage from 12% → 27%
- INCREASE **SL** usage from 36% → 47%
- REDUCE **SI** usage from 14% → 3%

### Count / situation detail

**vs RHH | ahead_pit** (88 pitches)

Expected improvement: **-0.009 xwOBA** (0.297 → 0.288); n=88

- INCREASE **ST** usage from 12% → 28%
- REDUCE **FF** usage from 30% → 15%
- REDUCE **SI** usage from 15% → 3%
- INCREASE **SL** usage from 42% → 54%

**vs RHH | 0-0** (87 pitches)

Expected improvement: **-0.007 xwOBA** (0.273 → 0.266); n=87

- INCREASE **SL** usage from 23% → 38%
- REDUCE **FF** usage from 30% → 15%
- REDUCE **SI** usage from 21% → 6%
- INCREASE **ST** usage from 20% → 35%

**vs RHH | ahead_hit** (58 pitches)

Expected improvement: **-0.007 xwOBA** (0.286 → 0.280); n=58

- REDUCE **FF** usage from 40% → 25%
- INCREASE **ST** usage from 7% → 22%
- INCREASE **KC** usage from 5% → 20%
- REDUCE **SI** usage from 17% → 3%

**vs RHH | even** (89 pitches)

Expected improvement: **-0.006 xwOBA** (0.289 → 0.283); n=89

- INCREASE **ST** usage from 9% → 24%
- REDUCE **FF** usage from 36% → 21%
- INCREASE **SL** usage from 44% → 49%
- REDUCE **SI** usage from 8% → 3%

**vs LHH | ahead_pit** (130 pitches)

Expected improvement: **-0.006 xwOBA** (0.302 → 0.297); n=130

- REDUCE **FF** usage from 35% → 20%
- INCREASE **CH** usage from 25% → 40%
- INCREASE **KC** usage from 8% → 23%
- REDUCE **SL** usage from 23% → 13%
- REDUCE **SI** usage from 8% → 3%

**vs LHH | even** (125 pitches)

Expected improvement: **-0.005 xwOBA** (0.280 → 0.275); n=125

- REDUCE **FF** usage from 31% → 16%
- INCREASE **CH** usage from 22% → 37%
- INCREASE **KC** usage from 8% → 23%
- REDUCE **SL** usage from 28% → 20%
- REDUCE **SI** usage from 10% → 3%

### Arsenal pairing signals

- SL vs primary FF: velo sep 8.5 mph, move sep 1.4 in, release strong tunnel (0.18 ft)
- CH vs primary FF: velo sep 13.2 mph, move sep 0.6 in, release strong tunnel (0.10 ft)
- SI vs primary FF: velo sep 1.6 mph, move sep 0.8 in, release strong tunnel (0.17 ft)
- KC vs primary FF: velo sep 15.2 mph, move sep 2.8 in, release strong tunnel (0.08 ft)
- ST vs primary FF: velo sep 13.7 mph, move sep 2.6 in, release moderate tunnel (0.41 ft)

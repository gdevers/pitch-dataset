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


## Baz, Shane (MLBAM 669358)

- Pitches modeled: **795**
- Arsenal: FF, KC, FC, CH, SI
- Overall expected xwOBA: 0.287 → 0.282 (improvement **-0.004**)
- Overall expected RV/pitch: +0.0054 → +0.0037 (-0.0017)

### Platoon usage

#### vs LHH

Expected improvement: **-0.003 xwOBA** (0.290 → 0.287); n=474

- REDUCE **FF** usage from 39% → 24%
- INCREASE **CH** usage from 13% → 28%
- INCREASE **KC** usage from 37% → 42%
- REDUCE **FC** usage from 8% → 3%

#### vs RHH

Expected improvement: **-0.005 xwOBA** (0.282 → 0.276); n=321

- INCREASE **KC** usage from 26% → 41%
- REDUCE **FF** usage from 27% → 12%
- REDUCE **SI** usage from 12% → 3%
- INCREASE **FC** usage from 35% → 44%

### Count / situation detail

**vs RHH | even** (75 pitches)

Expected improvement: **-0.006 xwOBA** (0.273 → 0.267); n=75

- INCREASE **KC** usage from 32% → 47%
- REDUCE **FF** usage from 25% → 10%
- REDUCE **SI** usage from 8% → 3%
- INCREASE **FC** usage from 35% → 40%

**vs LHH | ahead_hit** (95 pitches)

Expected improvement: **-0.005 xwOBA** (0.313 → 0.307); n=95

- REDUCE **FF** usage from 44% → 29%
- INCREASE **KC** usage from 28% → 43%
- INCREASE **CH** usage from 11% → 21%
- REDUCE **FC** usage from 9% → 3%
- REDUCE **SI** usage from 7% → 3%

**vs RHH | ahead_pit** (84 pitches)

Expected improvement: **-0.004 xwOBA** (0.295 → 0.291); n=84

- REDUCE **FF** usage from 29% → 14%
- INCREASE **FC** usage from 19% → 27%
- INCREASE **KC** usage from 48% → 55%

**vs RHH | 0-0** (84 pitches)

Expected improvement: **-0.004 xwOBA** (0.271 → 0.267); n=84

- REDUCE **FF** usage from 27% → 12%
- INCREASE **KC** usage from 10% → 25%
- INCREASE **FC** usage from 42% → 55%
- REDUCE **SI** usage from 20% → 7%

**vs RHH | ahead_hit** (61 pitches)

Expected improvement: **-0.004 xwOBA** (0.268 → 0.264); n=61

- INCREASE **KC** usage from 11% → 26%
- REDUCE **FF** usage from 25% → 10%
- REDUCE **SI** usage from 18% → 9%
- INCREASE **FC** usage from 46% → 55%

**vs LHH | ahead_pit** (111 pitches)

Expected improvement: **-0.004 xwOBA** (0.284 → 0.280); n=111

- INCREASE **CH** usage from 19% → 34%
- REDUCE **FF** usage from 32% → 17%
- REDUCE **FC** usage from 5% → 3%
- INCREASE **KC** usage from 44% → 47%

### Arsenal pairing signals

- KC vs primary FF: velo sep 11.1 mph, move sep 2.6 in, release strong tunnel (0.09 ft)
- FC vs primary FF: velo sep 6.9 mph, move sep 1.4 in, release strong tunnel (0.20 ft)
- CH vs primary FF: velo sep 7.3 mph, move sep 0.8 in, release strong tunnel (0.09 ft)
- SI vs primary FF: velo sep 0.7 mph, move sep 0.5 in, release strong tunnel (0.04 ft)

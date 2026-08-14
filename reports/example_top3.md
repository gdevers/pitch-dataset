# Pitch Arsenal Optimization Report

_Trained/scored on MLB 2026 pitches (2026-03-25 → 2026-08-13, n=491,230). Parquet data is local/gitignored; model artifact may be committed._

Recommendations compare **actual usage** to a constrained optimal mix that minimizes predicted pitch-level xwOBA (lower is better for the pitcher), holding location/count/TTO/context fixed and only reallocating pitch-type share.

## Alcantara, Sandy (MLBAM 645261)

- Pitches modeled: **2,385**
- Arsenal: SI, CH, FF, FC, ST, SL, CU
- Overall expected xwOBA: 0.272 → 0.264 (improvement **-0.007**)
- Overall expected RV/pitch: -0.0007 → -0.0026 (-0.0019)

### Platoon usage

#### vs LHH

Expected improvement: **-0.006 xwOBA** (0.277 → 0.271); n=1463

- REDUCE **SI** usage from 23% → 8%
- REDUCE **FF** usage from 21% → 6%
- INCREASE **ST** usage from 8% → 23%
- INCREASE **CH** usage from 25% → 40%

#### vs RHH

Expected improvement: **-0.009 xwOBA** (0.263 → 0.255); n=922

- INCREASE **ST** usage from 10% → 25%
- REDUCE **SI** usage from 31% → 16%
- INCREASE **SL** usage from 12% → 27%
- REDUCE **FF** usage from 17% → 3%
- REDUCE **FC** usage from 14% → 3%
- INCREASE **CH** usage from 14% → 24%

### Count / situation detail

**vs RHH | ahead_hit** (135 pitches)

Expected improvement: **-0.010 xwOBA** (0.271 → 0.261); n=135

- REDUCE **SI** usage from 39% → 24%
- INCREASE **SL** usage from 10% → 25%
- INCREASE **ST** usage from 7% → 22%
- REDUCE **FC** usage from 18% → 3%
- REDUCE **FF** usage from 17% → 3%
- INCREASE **CH** usage from 7% → 21%

**vs RHH | ahead_pit** (295 pitches)

Expected improvement: **-0.009 xwOBA** (0.273 → 0.264); n=295

- INCREASE **SL** usage from 16% → 31%
- REDUCE **SI** usage from 28% → 13%
- INCREASE **ST** usage from 13% → 28%
- REDUCE **FF** usage from 15% → 3%
- REDUCE **FC** usage from 12% → 3%
- INCREASE **CH** usage from 15% → 21%

**vs RHH | even** (195 pitches)

Expected improvement: **-0.008 xwOBA** (0.269 → 0.260); n=195

- INCREASE **ST** usage from 9% → 24%
- INCREASE **SL** usage from 10% → 25%
- REDUCE **SI** usage from 28% → 13%
- REDUCE **FF** usage from 15% → 3%
- REDUCE **FC** usage from 14% → 3%
- INCREASE **CH** usage from 21% → 29%

**vs LHH | ahead_pit** (436 pitches)

Expected improvement: **-0.007 xwOBA** (0.285 → 0.278); n=436

- INCREASE **CH** usage from 27% → 42%
- REDUCE **FF** usage from 20% → 5%
- INCREASE **ST** usage from 10% → 25%
- REDUCE **SI** usage from 21% → 6%

**vs RHH | 0-0** (265 pitches)

Expected improvement: **-0.007 xwOBA** (0.250 → 0.243); n=265

- REDUCE **FF** usage from 21% → 6%
- INCREASE **SL** usage from 9% → 24%
- REDUCE **SI** usage from 33% → 18%
- INCREASE **ST** usage from 11% → 26%
- INCREASE **CH** usage from 10% → 21%
- REDUCE **FC** usage from 14% → 3%

**vs LHH | full** (64 pitches)

Expected improvement: **-0.006 xwOBA** (0.336 → 0.329); n=64

- REDUCE **SI** usage from 33% → 18%
- REDUCE **FF** usage from 28% → 13%
- INCREASE **CH** usage from 14% → 29%
- INCREASE **ST** usage from 11% → 26%

### Arsenal pairing signals

- CH vs primary SI: velo sep 6.4 mph, move sep 0.5 in, release strong tunnel (0.03 ft)
- FF vs primary SI: velo sep 0.2 mph, move sep 0.6 in, release strong tunnel (0.07 ft)
- FC vs primary SI: velo sep 7.3 mph, move sep 1.5 in, release strong tunnel (0.03 ft)
- ST vs primary SI: velo sep 12.9 mph, move sep 2.5 in, release strong tunnel (0.03 ft)
- SL vs primary SI: velo sep 12.1 mph, move sep 1.9 in, release strong tunnel (0.02 ft)
- CU vs primary SI: velo sep 14.0 mph, move sep 2.0 in, release strong tunnel (0.08 ft)


## Sánchez, Cristopher (MLBAM 650911)

- Pitches modeled: **2,376**
- Arsenal: SI, CH, SL
- Overall expected xwOBA: 0.277 → 0.272 (improvement **-0.004**)
- Overall expected RV/pitch: -0.0021 → -0.0030 (-0.0009)

### Platoon usage

#### vs LHH

Expected improvement: **-0.004 xwOBA** (0.260 → 0.256); n=531

- INCREASE **SL** usage from 30% → 45%
- REDUCE **SI** usage from 58% → 43%

#### vs RHH

Expected improvement: **-0.004 xwOBA** (0.282 → 0.277); n=1845

- INCREASE **SL** usage from 16% → 31%
- REDUCE **SI** usage from 39% → 24%

### Count / situation detail

**vs RHH | full** (79 pitches)

Expected improvement: **-0.006 xwOBA** (0.326 → 0.319); n=79

- REDUCE **SI** usage from 37% → 22%
- INCREASE **SL** usage from 22% → 37%

**vs RHH | ahead_pit** (558 pitches)

Expected improvement: **-0.005 xwOBA** (0.286 → 0.281); n=558

- INCREASE **SL** usage from 13% → 28%
- REDUCE **SI** usage from 30% → 17%

**vs RHH | even** (406 pitches)

Expected improvement: **-0.005 xwOBA** (0.272 → 0.267); n=406

- REDUCE **SI** usage from 33% → 18%
- INCREASE **SL** usage from 14% → 27%

**vs LHH | ahead_pit** (202 pitches)

Expected improvement: **-0.005 xwOBA** (0.272 → 0.268); n=202

- REDUCE **SI** usage from 45% → 30%
- INCREASE **SL** usage from 35% → 50%

**vs LHH | even** (95 pitches)

Expected improvement: **-0.005 xwOBA** (0.272 → 0.267); n=95

- REDUCE **SI** usage from 49% → 34%
- INCREASE **SL** usage from 31% → 46%

**vs RHH | ahead_hit** (313 pitches)

Expected improvement: **-0.004 xwOBA** (0.282 → 0.278); n=313

- INCREASE **SL** usage from 18% → 33%
- REDUCE **SI** usage from 50% → 35%

### Arsenal pairing signals

- CH vs primary SI: velo sep 8.1 mph, move sep 0.4 in, release strong tunnel (0.09 ft)
- SL vs primary SI: velo sep 8.8 mph, move sep 1.7 in, release strong tunnel (0.08 ft)


## Gausman, Kevin (MLBAM 592332)

- Pitches modeled: **2,259**
- Arsenal: FF, FS, SL
- Overall expected xwOBA: 0.279 → 0.275 (improvement **-0.004**)
- Overall expected RV/pitch: +0.0005 → -0.0011 (-0.0016)

### Platoon usage

#### vs LHH

Expected improvement: **-0.003 xwOBA** (0.280 → 0.277); n=1289

- REDUCE **FF** usage from 53% → 42%
- INCREASE **FS** usage from 44% → 55%

#### vs RHH

Expected improvement: **-0.005 xwOBA** (0.278 → 0.273); n=970

- INCREASE **SL** usage from 19% → 34%
- REDUCE **FF** usage from 49% → 34%

### Count / situation detail

**vs RHH | full** (43 pitches)

Expected improvement: **-0.008 xwOBA** (0.323 → 0.315); n=43

- INCREASE **SL** usage from 7% → 22%
- REDUCE **FF** usage from 60% → 45%

**vs LHH | full** (74 pitches)

Expected improvement: **-0.008 xwOBA** (0.330 → 0.322); n=74

- INCREASE **FS** usage from 39% → 54%
- REDUCE **FF** usage from 61% → 46%

**vs RHH | ahead_pit** (337 pitches)

Expected improvement: **-0.006 xwOBA** (0.282 → 0.275); n=337

- REDUCE **FF** usage from 36% → 21%
- INCREASE **SL** usage from 22% → 37%

**vs RHH | even** (201 pitches)

Expected improvement: **-0.005 xwOBA** (0.277 → 0.272); n=201

- INCREASE **SL** usage from 9% → 24%
- REDUCE **FF** usage from 55% → 40%

**vs RHH | ahead_hit** (143 pitches)

Expected improvement: **-0.005 xwOBA** (0.276 → 0.271); n=143

- REDUCE **FF** usage from 62% → 47%
- INCREASE **SL** usage from 13% → 28%

**vs RHH | 0-0** (246 pitches)

Expected improvement: **-0.004 xwOBA** (0.264 → 0.260); n=246

- REDUCE **FF** usage from 54% → 39%
- INCREASE **SL** usage from 28% → 43%

### Arsenal pairing signals

- FS vs primary FF: velo sep 9.8 mph, move sep 1.1 in, release strong tunnel (0.23 ft)
- SL vs primary FF: velo sep 9.7 mph, move sep 1.5 in, release strong tunnel (0.19 ft)

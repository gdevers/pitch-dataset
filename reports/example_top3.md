# Pitch Arsenal Optimization Report

_Trained/scored on MLB 2026 pitches (2026-03-25 → 2026-08-13, n=491,230). Parquet data is local/gitignored; model artifact may be committed._

Recommendations compare **actual usage** to a constrained optimal mix that minimizes predicted pitch-level xwOBA (lower is better for the pitcher), holding location/count/TTO/context fixed and only reallocating pitch-type share.

## Alcantara, Sandy (MLBAM 645261)

- Pitches modeled: **2,385**
- Arsenal: SI, CH, FF, FC, ST, SL, CU
- Overall expected xwOBA: 0.276 → 0.271 (improvement **-0.006**)
- Overall expected RV/pitch: +0.0005 → -0.0002 (-0.0008)

### Platoon usage

#### vs LHH

Expected improvement: **-0.004 xwOBA** (0.281 → 0.277); n=1463

- REDUCE **FF** usage from 21% → 6%
- INCREASE **ST** usage from 8% → 23%
- REDUCE **SI** usage from 23% → 8%
- INCREASE **CH** usage from 25% → 40%

#### vs RHH

Expected improvement: **-0.008 xwOBA** (0.268 → 0.261); n=922

- INCREASE **ST** usage from 10% → 25%
- INCREASE **SL** usage from 12% → 27%
- REDUCE **SI** usage from 31% → 16%
- REDUCE **FF** usage from 17% → 3%
- REDUCE **FC** usage from 14% → 3%
- INCREASE **CH** usage from 14% → 24%

### Count / situation detail

**vs RHH | ahead_hit** (135 pitches)

Expected improvement: **-0.010 xwOBA** (0.275 → 0.265); n=135

- REDUCE **SI** usage from 39% → 24%
- INCREASE **ST** usage from 7% → 22%
- INCREASE **SL** usage from 10% → 25%
- REDUCE **FC** usage from 18% → 3%
- REDUCE **FF** usage from 17% → 3%
- INCREASE **CH** usage from 7% → 21%

**vs RHH | ahead_pit** (295 pitches)

Expected improvement: **-0.006 xwOBA** (0.278 → 0.272); n=295

- INCREASE **SL** usage from 16% → 31%
- REDUCE **SI** usage from 28% → 13%
- INCREASE **ST** usage from 13% → 28%
- REDUCE **FF** usage from 15% → 3%
- REDUCE **FC** usage from 12% → 3%
- INCREASE **CH** usage from 15% → 21%

**vs RHH | even** (195 pitches)

Expected improvement: **-0.005 xwOBA** (0.274 → 0.269); n=195

- INCREASE **SL** usage from 10% → 25%
- INCREASE **CH** usage from 21% → 36%
- REDUCE **SI** usage from 28% → 13%
- REDUCE **FF** usage from 15% → 3%
- REDUCE **FC** usage from 14% → 3%
- INCREASE **ST** usage from 9% → 17%

**vs LHH | 0-0** (387 pitches)

Expected improvement: **-0.005 xwOBA** (0.274 → 0.268); n=387

- INCREASE **CH** usage from 24% → 39%
- INCREASE **ST** usage from 7% → 22%
- REDUCE **FF** usage from 23% → 8%
- REDUCE **SI** usage from 21% → 6%
- REDUCE **CU** usage from 9% → 3%
- INCREASE **FC** usage from 15% → 21%

**vs RHH | 0-0** (265 pitches)

Expected improvement: **-0.005 xwOBA** (0.255 → 0.250); n=265

- INCREASE **CH** usage from 10% → 25%
- INCREASE **SL** usage from 9% → 24%
- REDUCE **FF** usage from 21% → 6%
- REDUCE **SI** usage from 33% → 18%
- REDUCE **ST** usage from 11% → 3%
- INCREASE **FC** usage from 14% → 22%

**vs LHH | ahead_hit** (253 pitches)

Expected improvement: **-0.003 xwOBA** (0.284 → 0.281); n=253

- REDUCE **SI** usage from 30% → 15%
- INCREASE **CH** usage from 25% → 40%
- INCREASE **FC** usage from 18% → 33%
- REDUCE **FF** usage from 17% → 3%

### Arsenal pairing signals

- CH vs primary SI:, velo sep 6.4 mph, move sep 0.5 in, eff speed sep 6.1 mph, spin sep 205 rpm, spin axis sep 10°, arm angle sep 0.5°, extension sep 0.10 ft, API break sep 1.0 in, release strong tunnel (0.10 ft)
- FF vs primary SI:, velo sep 0.2 mph, move sep 0.6 in, eff speed sep 0.1 mph, spin sep 44 rpm, spin axis sep 0°, arm angle sep 0.9°, extension sep 0.02 ft, API break sep 0.6 in, release strong tunnel (0.08 ft)
- FC vs primary SI:, velo sep 7.3 mph, move sep 1.5 in, eff speed sep 7.0 mph, spin sep 87 rpm, spin axis sep 31°, arm angle sep 1.0°, extension sep 0.03 ft, API break sep 1.6 in, release strong tunnel (0.04 ft)
- ST vs primary SI:, velo sep 12.9 mph, move sep 2.5 in, eff speed sep 13.0 mph, spin sep 80 rpm, spin axis sep 163°, arm angle sep 0.5°, extension sep 0.06 ft, API break sep 2.8 in, release strong tunnel (0.06 ft)
- SL vs primary SI:, velo sep 12.1 mph, move sep 1.9 in, eff speed sep 12.3 mph, spin sep 58 rpm, spin axis sep 157°, arm angle sep 1.2°, extension sep 0.00 ft, API break sep 2.2 in, release strong tunnel (0.02 ft)
- CU vs primary SI:, velo sep 14.0 mph, move sep 2.0 in, eff speed sep 13.7 mph, spin sep 126 rpm, spin axis sep 169°, arm angle sep 3.2°, extension sep 0.04 ft, API break sep 2.5 in, release strong tunnel (0.09 ft)


## Sánchez, Cristopher (MLBAM 650911)

- Pitches modeled: **2,376**
- Arsenal: SI, CH, SL
- Overall expected xwOBA: 0.277 → 0.275 (improvement **-0.002**)
- Overall expected RV/pitch: -0.0023 → -0.0026 (-0.0004)

### Platoon usage

#### vs LHH

Expected improvement: **-0.001 xwOBA** (0.256 → 0.255); n=531

- REDUCE **SI** usage from 58% → 43%
- INCREASE **CH** usage from 12% → 27%

#### vs RHH

Expected improvement: **-0.002 xwOBA** (0.283 → 0.281); n=1845

- REDUCE **SI** usage from 39% → 24%
- INCREASE **CH** usage from 45% → 55%
- INCREASE **SL** usage from 16% → 21%

### Count / situation detail

**vs RHH | full** (79 pitches)

Expected improvement: **-0.006 xwOBA** (0.325 → 0.320); n=79

- REDUCE **SI** usage from 37% → 22%
- INCREASE **CH** usage from 42% → 55%
- INCREASE **SL** usage from 22% → 23%

**vs RHH | 0-0** (489 pitches)

Expected improvement: **-0.004 xwOBA** (0.263 → 0.259); n=489

- INCREASE **CH** usage from 33% → 48%
- REDUCE **SI** usage from 46% → 31%

**vs LHH | even** (95 pitches)

Expected improvement: **-0.003 xwOBA** (0.270 → 0.267); n=95

- INCREASE **CH** usage from 20% → 35%
- REDUCE **SI** usage from 49% → 34%

**vs RHH | ahead_hit** (313 pitches)

Expected improvement: **-0.003 xwOBA** (0.281 → 0.278); n=313

- REDUCE **SI** usage from 50% → 35%
- INCREASE **CH** usage from 32% → 47%

**vs RHH | ahead_pit** (558 pitches)

Expected improvement: **-0.003 xwOBA** (0.288 → 0.285); n=558

- INCREASE **SL** usage from 13% → 28%
- REDUCE **SI** usage from 30% → 17%

**vs RHH | even** (406 pitches)

Expected improvement: **-0.003 xwOBA** (0.276 → 0.273); n=406

- REDUCE **SI** usage from 33% → 18%
- INCREASE **SL** usage from 14% → 27%

### Arsenal pairing signals

- CH vs primary SI:, velo sep 8.1 mph, move sep 0.4 in, eff speed sep 8.0 mph, spin sep 94 rpm, spin axis sep 15°, arm angle sep 1.7°, extension sep 0.11 ft, API break sep 1.1 in, release strong tunnel (0.15 ft)
- SL vs primary SI:, velo sep 8.8 mph, move sep 1.7 in, eff speed sep 9.0 mph, spin sep 58 rpm, spin axis sep 171°, arm angle sep 2.0°, extension sep 0.06 ft, API break sep 2.1 in, release strong tunnel (0.10 ft)


## Gausman, Kevin (MLBAM 592332)

- Pitches modeled: **2,259**
- Arsenal: FF, FS, SL
- Overall expected xwOBA: 0.282 → 0.279 (improvement **-0.004**)
- Overall expected RV/pitch: +0.0019 → +0.0003 (-0.0016)

### Platoon usage

#### vs LHH

Expected improvement: **-0.003 xwOBA** (0.283 → 0.280); n=1289

- INCREASE **FS** usage from 44% → 55%
- REDUCE **FF** usage from 53% → 42%

#### vs RHH

Expected improvement: **-0.005 xwOBA** (0.282 → 0.277); n=970

- REDUCE **FF** usage from 49% → 34%
- INCREASE **FS** usage from 32% → 47%

### Count / situation detail

**vs LHH | full** (74 pitches)

Expected improvement: **-0.008 xwOBA** (0.327 → 0.318); n=74

- REDUCE **FF** usage from 61% → 46%
- INCREASE **FS** usage from 39% → 54%

**vs RHH | full** (43 pitches)

Expected improvement: **-0.008 xwOBA** (0.322 → 0.314); n=43

- REDUCE **FF** usage from 60% → 45%
- INCREASE **FS** usage from 33% → 48%

**vs LHH | ahead_hit** (211 pitches)

Expected improvement: **-0.006 xwOBA** (0.283 → 0.277); n=211

- INCREASE **FS** usage from 40% → 55%
- REDUCE **FF** usage from 58% → 43%

**vs RHH | ahead_hit** (143 pitches)

Expected improvement: **-0.005 xwOBA** (0.279 → 0.274); n=143

- REDUCE **FF** usage from 62% → 47%
- INCREASE **FS** usage from 26% → 41%

**vs RHH | even** (201 pitches)

Expected improvement: **-0.005 xwOBA** (0.280 → 0.275); n=201

- REDUCE **FF** usage from 55% → 40%
- INCREASE **FS** usage from 36% → 51%

**vs LHH | even** (292 pitches)

Expected improvement: **-0.005 xwOBA** (0.282 → 0.277); n=292

- INCREASE **FS** usage from 41% → 55%
- REDUCE **FF** usage from 57% → 42%

### Arsenal pairing signals

- FS vs primary FF:, velo sep 9.8 mph, move sep 1.1 in, eff speed sep 9.7 mph, spin sep 706 rpm, spin axis sep 17°, arm angle sep 4.3°, extension sep 0.04 ft, API break sep 1.7 in, release strong tunnel (0.23 ft)
- SL vs primary FF:, velo sep 9.7 mph, move sep 1.5 in, eff speed sep 9.7 mph, spin sep 14 rpm, spin axis sep 27°, arm angle sep 2.8°, extension sep 0.03 ft, API break sep 2.0 in, release strong tunnel (0.19 ft)

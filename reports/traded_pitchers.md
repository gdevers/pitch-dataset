# 2026 Trade Deadline Pitcher Analysis

_MLB 2026 pitches (2026-03-25 → 2026-08-13, n=491,230). Team affiliation derived from `inning_topbot` + home/away. Post-trade samples are partial through data end date._

Pre/post splits use **trade date** cutoffs and **pitcher team** derived from `inning_topbot` + home/away. Shape metrics include arm angle, release point, Pairing/tunnel notes reuse extended separation logic from `arsenal.py` (velo/movement, effective speed, spin, arm angle, extension, API break, 3D release distance).

## Tarik Skubal (DET → LAD)

- MLBAM **669373** · trade date **2026-08-01**
- Pitches: **1,346** pre / **180** post (total 1,526)
- Pre-trade window: 2026-03-26 → 2026-07-29
- Post-trade window: 2026-08-04 → 2026-08-10

### Usage mix (%)

| Pitch | Pre | Post | Δ pp |
| --- | ---: | ---: | ---: |
| FF · 4-Seam | 36.7 | 25.0 | -11.7 |
| CH · Changeup | 25.6 | 28.9 | +3.3 |
| SI · Sinker | 19.5 | 31.1 | +11.6 |
| SL · Slider | 13.8 | 10.0 | -3.8 |
| CU · Curveball | 4.5 | 5.0 | +0.5 |

### Pairing / tunnel vs primary

Primary pitch shifted **FF → SI** post-trade.

**Pre-trade**
- CH vs primary FF:, velo sep 9.4 mph, move sep 1.3 in, eff speed sep 9.7 mph, spin sep 499 rpm, spin axis sep 21°, arm angle sep 8.8°, extension sep 0.09 ft, API break sep 1.9 in, release distinct release (0.50 ft)
- SI vs primary FF:, velo sep 0.0 mph, move sep 0.9 in, eff speed sep 0.1 mph, spin sep 133 rpm, spin axis sep 5°, arm angle sep 3.7°, extension sep 0.02 ft, API break sep 1.0 in, release strong tunnel (0.19 ft)
- SL vs primary FF:, velo sep 7.4 mph, move sep 1.2 in, eff speed sep 7.1 mph, spin sep 102 rpm, spin axis sep 39°, arm angle sep 5.5°, extension sep 0.01 ft, API break sep 1.7 in, release distinct release (0.50 ft)
- CU vs primary FF:, velo sep 16.5 mph, move sep 2.1 in, eff speed sep 16.4 mph, spin sep 208 rpm, spin axis sep 166°, arm angle sep 0.4°, extension sep 0.02 ft, API break sep 3.2 in, release strong tunnel (0.19 ft)

**Post-trade**
- CH vs primary SI:, velo sep 9.1 mph, move sep 0.6 in, eff speed sep 9.3 mph, spin sep 318 rpm, spin axis sep 21°, arm angle sep 6.3°, extension sep 0.06 ft, API break sep 1.2 in, release moderate tunnel (0.40 ft)
- FF vs primary SI:, velo sep 0.3 mph, move sep 0.9 in, eff speed sep 0.3 mph, spin sep 122 rpm, spin axis sep 2°, arm angle sep 3.5°, extension sep 0.04 ft, API break sep 0.9 in, release strong tunnel (0.20 ft)
- SL vs primary SI:, velo sep 6.4 mph, move sep 1.4 in, eff speed sep 6.1 mph, spin sep 30 rpm, spin axis sep 14°, arm angle sep 2.4°, extension sep 0.03 ft, API break sep 1.6 in, release moderate tunnel (0.32 ft)
- CU vs primary SI:, velo sep 16.4 mph, move sep 2.2 in, eff speed sep 16.4 mph, spin sep 335 rpm, spin axis sep 164°, arm angle sep 3.7°, extension sep 0.00 ft, API break sep 3.0 in, release strong tunnel (0.10 ft)

### Shape metrics by pitch type

#### CH · Changeup

| Metric | Pre | Post | Δ |
| --- | ---: | ---: | ---: |
| Arm angle (deg) | 42.01 | 41.69 | -0.32 |
| Release height Z (ft) | 6.01 | 6.06 | +0.05 |
| Extension (ft) | 6.28 | 6.34 | +0.06 |
| Spin rate (rpm) | 1824.63 | 1874.50 | +49.87 |
| Effective speed (mph) | 87.04 | 88.04 | +1.00 |
| Break Z w/ gravity (in) | 2.62 | 2.53 | -0.09 |
| Release speed (mph) | 87.22 | 87.90 | +0.68 |
| Spin axis (deg) | 133.41 | 131.37 | -2.04 |
| Release side X (ft) | 2.13 | 2.05 | -0.08 |
| Release depth Y (ft) | 54.22 | 54.15 | -0.07 |
| PFX horizontal (in) | 1.13 | 1.17 | +0.04 |
| PFX vertical (in) | 0.39 | 0.42 | +0.03 |
| Break X arm (in) | 1.13 | 1.17 | +0.04 |
| Break X batter-in (in) | -0.76 | -0.49 | +0.27 |

#### CU · Curveball

| Metric | Pre | Post | Δ |
| --- | ---: | ---: | ---: |
| Arm angle (deg) | 51.18 | 51.67 | +0.49 |
| Release height Z (ft) | 6.17 | 6.25 | +0.08 |
| Extension (ft) | 6.34 | 6.40 | +0.06 |
| Spin rate (rpm) | 2531.73 | 2527.67 | -4.06 |
| Effective speed (mph) | 80.30 | 80.93 | +0.63 |
| Break Z w/ gravity (in) | 3.98 | 3.91 | -0.07 |
| Release speed (mph) | 80.18 | 80.58 | +0.40 |
| Spin axis (deg) | 320.15 | 316.89 | -3.26 |
| Release side X (ft) | 1.87 | 1.77 | -0.10 |
| Release depth Y (ft) | 54.15 | 54.10 | -0.05 |
| PFX horizontal (in) | -0.72 | -0.69 | +0.03 |
| PFX vertical (in) | -0.43 | -0.41 | +0.02 |
| Break X arm (in) | -0.72 | -0.69 | +0.03 |
| Break X batter-in (in) | 0.23 | -0.19 | -0.42 |

#### FF · 4-Seam

| Metric | Pre | Post | Δ |
| --- | ---: | ---: | ---: |
| Arm angle (deg) | 50.79 | 51.45 | +0.66 |
| Release height Z (ft) | 6.25 | 6.35 | +0.10 |
| Extension (ft) | 6.37 | 6.37 | +0.00 |
| Spin rate (rpm) | 2323.67 | 2314.16 | -9.51 |
| Effective speed (mph) | 96.75 | 97.60 | +0.85 |
| Break Z w/ gravity (in) | 1.02 | 1.03 | +0.01 |
| Release speed (mph) | 96.66 | 97.31 | +0.65 |
| Spin axis (deg) | 154.45 | 154.36 | -0.09 |
| Release side X (ft) | 1.70 | 1.56 | -0.14 |
| Release depth Y (ft) | 54.13 | 54.13 | +0.00 |
| PFX horizontal (in) | 0.30 | 0.21 | -0.09 |
| PFX vertical (in) | 1.42 | 1.37 | -0.05 |
| Break X arm (in) | 0.30 | 0.21 | -0.09 |
| Break X batter-in (in) | -0.23 | -0.06 | +0.17 |

#### SI · Sinker

| Metric | Pre | Post | Δ |
| --- | ---: | ---: | ---: |
| Arm angle (deg) | 47.14 | 47.98 | +0.84 |
| Release height Z (ft) | 6.13 | 6.20 | +0.07 |
| Extension (ft) | 6.39 | 6.40 | +0.01 |
| Spin rate (rpm) | 2190.45 | 2192.45 | +2.00 |
| Effective speed (mph) | 96.69 | 97.31 | +0.62 |
| Break Z w/ gravity (in) | 1.44 | 1.41 | -0.03 |
| Release speed (mph) | 96.64 | 96.98 | +0.34 |
| Spin axis (deg) | 149.71 | 152.71 | +3.00 |
| Release side X (ft) | 1.85 | 1.68 | -0.17 |
| Release depth Y (ft) | 54.11 | 54.09 | -0.02 |
| PFX horizontal (in) | 1.14 | 1.05 | -0.09 |
| PFX vertical (in) | 1.00 | 1.01 | +0.01 |
| Break X arm (in) | 1.14 | 1.05 | -0.09 |
| Break X batter-in (in) | 0.01 | -0.19 | -0.20 |

#### SL · Slider

| Metric | Pre | Post | Δ |
| --- | ---: | ---: | ---: |
| Arm angle (deg) | 45.26 | 45.59 | +0.33 |
| Release height Z (ft) | 6.03 | 6.09 | +0.06 |
| Extension (ft) | 6.38 | 6.38 | +0.00 |
| Spin rate (rpm) | 2221.49 | 2162.22 | -59.27 |
| Effective speed (mph) | 89.63 | 91.17 | +1.54 |
| Break Z w/ gravity (in) | 2.53 | 2.32 | -0.21 |
| Release speed (mph) | 89.29 | 90.61 | +1.32 |
| Spin axis (deg) | 193.46 | 166.72 | -26.74 |
| Release side X (ft) | 2.15 | 1.98 | -0.17 |
| Release depth Y (ft) | 54.12 | 54.11 | -0.01 |
| PFX horizontal (in) | -0.26 | -0.28 | -0.02 |
| PFX vertical (in) | 0.32 | 0.43 | +0.11 |
| Break X arm (in) | -0.26 | -0.28 | -0.02 |
| Break X batter-in (in) | 0.21 | 0.10 | -0.11 |


## Kevin Gausman (TOR → CHC)

- MLBAM **592332** · trade date **2026-08-02**
- Pitches: **2,104** pre / **155** post (total 2,259)
- Pre-trade window: 2026-03-27 → 2026-08-01
- Post-trade window: 2026-08-07 → 2026-08-13

### Usage mix (%)

| Pitch | Pre | Post | Δ pp |
| --- | ---: | ---: | ---: |
| FF · 4-Seam | 51.9 | 44.5 | -7.4 |
| FS · Splitter | 37.9 | 51.6 | +13.7 |
| SL · Slider | 10.2 | 3.9 | -6.3 |

### Pairing / tunnel vs primary

Primary pitch shifted **FF → FS** post-trade.

**Pre-trade**
- FS vs primary FF:, velo sep 9.9 mph, move sep 1.1 in, eff speed sep 9.8 mph, spin sep 704 rpm, spin axis sep 17°, arm angle sep 4.3°, extension sep 0.03 ft, API break sep 1.7 in, release strong tunnel (0.23 ft)
- SL vs primary FF:, velo sep 9.7 mph, move sep 1.5 in, eff speed sep 9.6 mph, spin sep 7 rpm, spin axis sep 28°, arm angle sep 2.8°, extension sep 0.02 ft, API break sep 2.0 in, release strong tunnel (0.19 ft)

**Post-trade**
- FF vs primary FS:, velo sep 9.2 mph, move sep 1.0 in, eff speed sep 9.2 mph, spin sep 748 rpm, spin axis sep 18°, arm angle sep 5.8°, extension sep 0.01 ft, API break sep 1.5 in, release moderate tunnel (0.25 ft)
- SL vs primary FS:, velo sep 0.4 mph, move sep 1.1 in, eff speed sep 0.6 mph, spin sep 574 rpm, spin axis sep 26°, arm angle sep nan°, extension sep 0.07 ft, API break sep 1.1 in, release strong tunnel (0.17 ft)

### Shape metrics by pitch type

#### FF · 4-Seam

| Metric | Pre | Post | Δ |
| --- | ---: | ---: | ---: |
| Arm angle (deg) | 39.19 | 40.63 | +1.44 |
| Release height Z (ft) | 5.83 | 5.82 | -0.01 |
| Extension (ft) | 6.70 | 6.88 | +0.18 |
| Spin rate (rpm) | 2275.75 | 2329.72 | +53.97 |
| Effective speed (mph) | 94.51 | 95.70 | +1.19 |
| Break Z w/ gravity (in) | 1.18 | 1.17 | -0.01 |
| Release speed (mph) | 93.95 | 94.56 | +0.61 |
| Spin axis (deg) | 217.54 | 217.06 | -0.48 |
| Release side X (ft) | -2.36 | -2.40 | -0.04 |
| Release depth Y (ft) | 53.80 | 53.62 | -0.18 |
| PFX horizontal (in) | -0.91 | -0.88 | +0.03 |
| PFX vertical (in) | 1.41 | 1.37 | -0.04 |
| Break X arm (in) | 0.91 | 0.88 | -0.03 |
| Break X batter-in (in) | -0.16 | -0.14 | +0.02 |

#### FS · Splitter

| Metric | Pre | Post | Δ |
| --- | ---: | ---: | ---: |
| Arm angle (deg) | 34.87 | 34.83 | -0.04 |
| Release height Z (ft) | 5.69 | 5.65 | -0.04 |
| Extension (ft) | 6.74 | 6.87 | +0.13 |
| Spin rate (rpm) | 1572.18 | 1582.12 | +9.94 |
| Effective speed (mph) | 84.66 | 86.50 | +1.84 |
| Break Z w/ gravity (in) | 2.87 | 2.67 | -0.20 |
| Release speed (mph) | 84.05 | 85.36 | +1.31 |
| Spin axis (deg) | 234.32 | 234.72 | +0.40 |
| Release side X (ft) | -2.54 | -2.58 | -0.04 |
| Release depth Y (ft) | 53.76 | 53.63 | -0.13 |
| PFX horizontal (in) | -1.14 | -1.15 | -0.01 |
| PFX vertical (in) | 0.37 | 0.45 | +0.08 |
| Break X arm (in) | 1.14 | 1.15 | +0.01 |
| Break X batter-in (in) | -0.35 | -0.09 | +0.26 |

#### SL · Slider

| Metric | Pre | Post | Δ |
| --- | ---: | ---: | ---: |
| Arm angle (deg) | 36.40 | — | — |
| Release height Z (ft) | 5.69 | 5.73 | +0.04 |
| Extension (ft) | 6.68 | 6.80 | +0.12 |
| Spin rate (rpm) | 2268.43 | 2156.50 | -111.93 |
| Effective speed (mph) | 84.88 | 85.87 | +0.99 |
| Break Z w/ gravity (in) | 2.91 | 2.88 | -0.03 |
| Release speed (mph) | 84.22 | 84.95 | +0.73 |
| Spin axis (deg) | 189.50 | 209.17 | +19.67 |
| Release side X (ft) | -2.49 | -2.46 | +0.03 |
| Release depth Y (ft) | 53.82 | 53.72 | -0.10 |
| PFX horizontal (in) | 0.08 | -0.05 | -0.13 |
| PFX vertical (in) | 0.30 | 0.27 | -0.03 |
| Break X arm (in) | -0.08 | 0.05 | +0.13 |
| Break X batter-in (in) | -0.05 | 0.05 | +0.10 |


## José Soriano (LAA → TOR)

- MLBAM **667755** · trade date **2026-08-03**
- Pitches: **1,965** pre / **150** post (total 2,115)
- Pre-trade window: 2026-03-26 → 2026-07-26
- Post-trade window: 2026-08-07 → 2026-08-12

### Usage mix (%)

| Pitch | Pre | Post | Δ pp |
| --- | ---: | ---: | ---: |
| SI · Sinker | 26.1 | 39.3 | +13.2 |
| KC · Knuckle Curve | 25.8 | 24.0 | -1.8 |
| FF · 4-Seam | 23.9 | 18.0 | -5.9 |
| FS · Splitter | 19.4 | 17.3 | -2.1 |
| SL · Slider | 4.8 | 0.0 | -4.8 |

### Pairing / tunnel vs primary



**Pre-trade**
- KC vs primary SI:, velo sep 11.1 mph, move sep 2.4 in, eff speed sep 11.3 mph, spin sep 430 rpm, spin axis sep 159°, arm angle sep 7.2°, extension sep 0.01 ft, API break sep 2.7 in, release moderate tunnel (0.31 ft)
- FF vs primary SI:, velo sep 0.8 mph, move sep 0.9 in, eff speed sep 0.6 mph, spin sep 258 rpm, spin axis sep 2°, arm angle sep 0.0°, extension sep 0.02 ft, API break sep 1.0 in, release strong tunnel (0.03 ft)
- FS vs primary SI:, velo sep 4.0 mph, move sep 0.2 in, eff speed sep 3.9 mph, spin sep 314 rpm, spin axis sep 8°, arm angle sep 0.9°, extension sep 0.04 ft, API break sep 0.8 in, release strong tunnel (0.05 ft)
- SL vs primary SI:, velo sep 6.2 mph, move sep 1.3 in, eff speed sep 6.3 mph, spin sep 412 rpm, spin axis sep 53°, arm angle sep 3.3°, extension sep 0.03 ft, API break sep 1.4 in, release strong tunnel (0.15 ft)

**Post-trade**
- KC vs primary SI:, velo sep 10.2 mph, move sep 2.5 in, eff speed sep 10.4 mph, spin sep 418 rpm, spin axis sep 156°, arm angle sep 2.5°, extension sep 0.05 ft, API break sep 2.8 in, release moderate tunnel (0.36 ft)
- FF vs primary SI:, velo sep 0.6 mph, move sep 0.9 in, eff speed sep 0.4 mph, spin sep 248 rpm, spin axis sep 0°, arm angle sep 1.1°, extension sep 0.05 ft, API break sep 1.0 in, release strong tunnel (0.05 ft)
- FS vs primary SI:, velo sep 3.8 mph, move sep 0.1 in, eff speed sep 3.8 mph, spin sep 222 rpm, spin axis sep 10°, arm angle sep 2.7°, extension sep 0.04 ft, API break sep 1.1 in, release strong tunnel (0.08 ft)

### Shape metrics by pitch type

#### FF · 4-Seam

| Metric | Pre | Post | Δ |
| --- | ---: | ---: | ---: |
| Arm angle (deg) | 32.06 | 37.90 | +5.84 |
| Release height Z (ft) | 5.72 | 5.80 | +0.08 |
| Extension (ft) | 6.75 | 6.70 | -0.05 |
| Spin rate (rpm) | 2184.82 | 2176.85 | -7.97 |
| Effective speed (mph) | 97.73 | 97.38 | -0.35 |
| Break Z w/ gravity (in) | 1.31 | 1.30 | -0.01 |
| Release speed (mph) | 97.14 | 96.94 | -0.20 |
| Spin axis (deg) | 231.08 | 230.81 | -0.27 |
| Release side X (ft) | -2.42 | -2.15 | +0.27 |
| Release depth Y (ft) | 53.75 | 53.80 | +0.05 |
| PFX horizontal (in) | -0.81 | -0.80 | +0.01 |
| PFX vertical (in) | 1.12 | 1.14 | +0.02 |
| Break X arm (in) | 0.81 | 0.80 | -0.01 |
| Break X batter-in (in) | -0.13 | 0.26 | +0.39 |

#### FS · Splitter

| Metric | Pre | Post | Δ |
| --- | ---: | ---: | ---: |
| Arm angle (deg) | 32.99 | 36.30 | +3.31 |
| Release height Z (ft) | 5.68 | 5.76 | +0.08 |
| Extension (ft) | 6.81 | 6.79 | -0.02 |
| Spin rate (rpm) | 1611.97 | 1707.73 | +95.76 |
| Effective speed (mph) | 93.20 | 93.21 | +0.01 |
| Break Z w/ gravity (in) | 2.61 | 2.42 | -0.19 |
| Release speed (mph) | 92.31 | 92.47 | +0.16 |
| Spin axis (deg) | 241.04 | 240.69 | -0.35 |
| Release side X (ft) | -2.41 | -2.18 | +0.23 |
| Release depth Y (ft) | 53.69 | 53.71 | +0.02 |
| PFX horizontal (in) | -1.14 | -1.22 | -0.08 |
| PFX vertical (in) | 0.06 | 0.25 | +0.19 |
| Break X arm (in) | 1.14 | 1.22 | +0.08 |
| Break X batter-in (in) | -0.71 | -1.22 | -0.51 |

#### KC · Knuckle Curve

| Metric | Pre | Post | Δ |
| --- | ---: | ---: | ---: |
| Arm angle (deg) | 39.29 | 41.52 | +2.23 |
| Release height Z (ft) | 5.88 | 6.01 | +0.13 |
| Extension (ft) | 6.76 | 6.80 | +0.04 |
| Spin rate (rpm) | 2356.63 | 2347.28 | -9.35 |
| Effective speed (mph) | 85.86 | 86.59 | +0.73 |
| Break Z w/ gravity (in) | 3.69 | 3.62 | -0.07 |
| Release speed (mph) | 85.28 | 86.05 | +0.77 |
| Spin axis (deg) | 32.15 | 26.78 | -5.37 |
| Release side X (ft) | -2.15 | -1.84 | +0.31 |
| Release depth Y (ft) | 53.74 | 53.71 | -0.03 |
| PFX horizontal (in) | 1.01 | 1.03 | +0.02 |
| PFX vertical (in) | -0.54 | -0.52 | +0.02 |
| Break X arm (in) | -1.01 | -1.03 | -0.02 |
| Break X batter-in (in) | -0.07 | -0.07 | +0.00 |

#### SI · Sinker

| Metric | Pre | Post | Δ |
| --- | ---: | ---: | ---: |
| Arm angle (deg) | 32.07 | 39.03 | +6.96 |
| Release height Z (ft) | 5.71 | 5.82 | +0.11 |
| Extension (ft) | 6.77 | 6.75 | -0.02 |
| Spin rate (rpm) | 1926.40 | 1929.24 | +2.84 |
| Effective speed (mph) | 97.14 | 97.01 | -0.13 |
| Break Z w/ gravity (in) | 2.18 | 2.08 | -0.10 |
| Release speed (mph) | 96.34 | 96.29 | -0.05 |
| Spin axis (deg) | 232.83 | 231.00 | -1.83 |
| Release side X (ft) | -2.40 | -2.15 | +0.25 |
| Release depth Y (ft) | 53.73 | 53.76 | +0.03 |
| PFX horizontal (in) | -1.25 | -1.28 | -0.03 |
| PFX vertical (in) | 0.28 | 0.38 | +0.10 |
| Break X arm (in) | 1.25 | 1.28 | +0.03 |
| Break X batter-in (in) | -0.01 | -0.16 | -0.15 |

#### SL · Slider

| Metric | Pre | Post | Δ |
| --- | ---: | ---: | ---: |
| Arm angle (deg) | 35.37 | — | — |
| Release height Z (ft) | 5.78 | — | — |
| Extension (ft) | 6.80 | — | — |
| Spin rate (rpm) | 2338.80 | — | — |
| Effective speed (mph) | 90.89 | — | — |
| Break Z w/ gravity (in) | 2.55 | — | — |
| Release speed (mph) | 90.15 | — | — |
| Spin axis (deg) | 179.34 | — | — |
| Release side X (ft) | -2.28 | — | — |
| Release depth Y (ft) | 53.70 | — | — |
| PFX horizontal (in) | 0.09 | — | — |
| PFX vertical (in) | 0.26 | — | — |
| Break X arm (in) | -0.09 | — | — |
| Break X batter-in (in) | -0.07 | — | — |


## Casey Mize (DET → SD)

- MLBAM **663554** · trade date **2026-08-03**
- Pitches: **1,264** pre / **160** post (total 1,424)
- Pre-trade window: 2026-03-31 → 2026-07-25
- Post-trade window: 2026-08-05 → 2026-08-10

### Usage mix (%)

| Pitch | Pre | Post | Δ pp |
| --- | ---: | ---: | ---: |
| FF · 4-Seam | 34.1 | 32.5 | -1.6 |
| SL · Slider | 26.7 | 30.0 | +3.3 |
| FS · Splitter | 23.4 | 21.9 | -1.5 |
| SI · Sinker | 10.8 | 11.2 | +0.4 |
| SV · Slurve | 5.0 | 4.4 | -0.6 |

### Pairing / tunnel vs primary



**Pre-trade**
- SL vs primary FF:, velo sep 5.8 mph, move sep 1.5 in, eff speed sep 5.5 mph, spin sep 29 rpm, spin axis sep 42°, arm angle sep 5.3°, extension sep 0.03 ft, API break sep 1.8 in, release moderate tunnel (0.41 ft)
- FS vs primary FF:, velo sep 5.6 mph, move sep 1.1 in, eff speed sep 5.5 mph, spin sep 736 rpm, spin axis sep 20°, arm angle sep 3.4°, extension sep 0.00 ft, API break sep 1.4 in, release strong tunnel (0.21 ft)
- SI vs primary FF:, velo sep 0.1 mph, move sep 0.4 in, eff speed sep 0.2 mph, spin sep 36 rpm, spin axis sep 4°, arm angle sep 2.1°, extension sep 0.00 ft, API break sep 1.5 in, release strong tunnel (0.07 ft)
- SV vs primary FF:, velo sep 12.0 mph, move sep 2.8 in, eff speed sep 12.4 mph, spin sep 287 rpm, spin axis sep 175°, arm angle sep 5.3°, extension sep 0.06 ft, API break sep 3.5 in, release distinct release (0.51 ft)

**Post-trade**
- SL vs primary FF:, velo sep 5.7 mph, move sep 1.6 in, eff speed sep 5.4 mph, spin sep 19 rpm, spin axis sep 55°, arm angle sep 5.3°, extension sep 0.01 ft, API break sep 1.9 in, release moderate tunnel (0.38 ft)
- FS vs primary FF:, velo sep 5.0 mph, move sep 1.1 in, eff speed sep 4.8 mph, spin sep 767 rpm, spin axis sep 17°, arm angle sep 3.2°, extension sep 0.00 ft, API break sep 1.4 in, release strong tunnel (0.19 ft)
- SI vs primary FF:, velo sep 0.5 mph, move sep 0.4 in, eff speed sep 0.8 mph, spin sep 60 rpm, spin axis sep 0°, arm angle sep 1.9°, extension sep 0.01 ft, API break sep 1.4 in, release strong tunnel (0.07 ft)
- SV vs primary FF:, velo sep 11.8 mph, move sep 2.7 in, eff speed sep 12.1 mph, spin sep 284 rpm, spin axis sep 170°, arm angle sep 5.5°, extension sep 0.07 ft, API break sep 3.4 in, release distinct release (0.47 ft)

### Shape metrics by pitch type

#### FF · 4-Seam

| Metric | Pre | Post | Δ |
| --- | ---: | ---: | ---: |
| Arm angle (deg) | 46.52 | 47.61 | +1.09 |
| Release height Z (ft) | 5.90 | 5.95 | +0.05 |
| Extension (ft) | 6.82 | 6.81 | -0.01 |
| Spin rate (rpm) | 2269.17 | 2250.88 | -18.29 |
| Effective speed (mph) | 94.28 | 93.61 | -0.67 |
| Break Z w/ gravity (in) | 1.12 | 1.12 | +0.00 |
| Release speed (mph) | 93.49 | 93.05 | -0.44 |
| Spin axis (deg) | 213.42 | 211.54 | -1.88 |
| Release side X (ft) | -2.08 | -2.12 | -0.04 |
| Release depth Y (ft) | 53.68 | 53.69 | +0.01 |
| PFX horizontal (in) | -0.82 | -0.76 | +0.06 |
| PFX vertical (in) | 1.49 | 1.53 | +0.04 |
| Break X arm (in) | 0.82 | 0.76 | -0.06 |
| Break X batter-in (in) | -0.35 | -0.25 | +0.10 |

#### FS · Splitter

| Metric | Pre | Post | Δ |
| --- | ---: | ---: | ---: |
| Arm angle (deg) | 43.10 | 44.38 | +1.28 |
| Release height Z (ft) | 5.78 | 5.85 | +0.07 |
| Extension (ft) | 6.82 | 6.81 | -0.01 |
| Spin rate (rpm) | 1532.82 | 1484.29 | -48.53 |
| Effective speed (mph) | 88.80 | 88.79 | -0.01 |
| Break Z w/ gravity (in) | 2.47 | 2.39 | -0.08 |
| Release speed (mph) | 87.90 | 88.06 | +0.16 |
| Spin axis (deg) | 233.76 | 228.97 | -4.79 |
| Release side X (ft) | -2.25 | -2.28 | -0.03 |
| Release depth Y (ft) | 53.68 | 53.69 | +0.01 |
| PFX horizontal (in) | -1.25 | -1.19 | +0.06 |
| PFX vertical (in) | 0.48 | 0.56 | +0.08 |
| Break X arm (in) | 1.25 | 1.19 | -0.06 |
| Break X batter-in (in) | -0.57 | -0.65 | -0.08 |

#### SI · Sinker

| Metric | Pre | Post | Δ |
| --- | ---: | ---: | ---: |
| Arm angle (deg) | 44.37 | 45.68 | +1.31 |
| Release height Z (ft) | 5.85 | 5.90 | +0.05 |
| Extension (ft) | 6.82 | 6.82 | +0.00 |
| Spin rate (rpm) | 2305.64 | 2310.44 | +4.80 |
| Effective speed (mph) | 94.43 | 94.38 | -0.05 |
| Break Z w/ gravity (in) | 1.36 | 1.33 | -0.03 |
| Release speed (mph) | 93.58 | 93.53 | -0.05 |
| Spin axis (deg) | 216.93 | 211.61 | -5.32 |
| Release side X (ft) | -2.12 | -2.16 | -0.04 |
| Release depth Y (ft) | 53.68 | 53.67 | -0.01 |
| PFX horizontal (in) | -1.16 | -1.07 | +0.09 |
| PFX vertical (in) | 1.25 | 1.28 | +0.03 |
| Break X arm (in) | 1.16 | 1.07 | -0.09 |
| Break X batter-in (in) | 1.13 | 1.07 | -0.06 |

#### SL · Slider

| Metric | Pre | Post | Δ |
| --- | ---: | ---: | ---: |
| Arm angle (deg) | 41.25 | 42.36 | +1.11 |
| Release height Z (ft) | 5.69 | 5.74 | +0.05 |
| Extension (ft) | 6.80 | 6.83 | +0.03 |
| Spin rate (rpm) | 2240.53 | 2232.23 | -8.30 |
| Effective speed (mph) | 88.76 | 88.20 | -0.56 |
| Break Z w/ gravity (in) | 2.51 | 2.64 | +0.13 |
| Release speed (mph) | 87.72 | 87.30 | -0.42 |
| Spin axis (deg) | 170.99 | 156.65 | -14.34 |
| Release side X (ft) | -2.43 | -2.44 | -0.01 |
| Release depth Y (ft) | 53.71 | 53.67 | -0.04 |
| PFX horizontal (in) | 0.29 | 0.32 | +0.03 |
| PFX vertical (in) | 0.44 | 0.35 | -0.09 |
| Break X arm (in) | -0.29 | -0.32 | -0.03 |
| Break X batter-in (in) | 0.06 | -0.04 | -0.10 |

#### SV · Slurve

| Metric | Pre | Post | Δ |
| --- | ---: | ---: | ---: |
| Arm angle (deg) | 41.20 | 42.16 | +0.96 |
| Release height Z (ft) | 5.66 | 5.75 | +0.09 |
| Extension (ft) | 6.76 | 6.74 | -0.02 |
| Spin rate (rpm) | 2556.17 | 2535.00 | -21.17 |
| Effective speed (mph) | 81.91 | 81.56 | -0.35 |
| Break Z w/ gravity (in) | 4.05 | 3.98 | -0.07 |
| Release speed (mph) | 81.44 | 81.24 | -0.20 |
| Spin axis (deg) | 38.83 | 41.43 | +2.60 |
| Release side X (ft) | -2.52 | -2.54 | -0.02 |
| Release depth Y (ft) | 53.74 | 53.74 | +0.00 |
| PFX horizontal (in) | 1.11 | 1.09 | -0.02 |
| PFX vertical (in) | -0.59 | -0.49 | +0.10 |
| Break X arm (in) | -1.11 | -1.09 | +0.02 |
| Break X batter-in (in) | -0.52 | -0.45 | +0.07 |


## Freddy Peralta (NYM → TB)

- MLBAM **642547** · trade date **2026-08-02**
- Pitches: **2,042** pre / **169** post (total 2,211)
- Pre-trade window: 2026-03-26 → 2026-07-26
- Post-trade window: 2026-08-04 → 2026-08-10

### Usage mix (%)

| Pitch | Pre | Post | Δ pp |
| --- | ---: | ---: | ---: |
| FF · 4-Seam | 52.9 | 48.5 | -4.4 |
| CH · Changeup | 20.9 | 34.3 | +13.4 |
| CU · Curveball | 13.4 | 10.7 | -2.7 |
| ST · Sweeper | 5.7 | 5.9 | +0.2 |
| SL · Slider | 5.6 | 0.0 | -5.6 |
| CS · Slow Curve | 1.4 | 0.0 | -1.4 |

### Pairing / tunnel vs primary



**Pre-trade**
- CH vs primary FF:, velo sep 6.9 mph, move sep 1.4 in, eff speed sep 7.2 mph, spin sep 484 rpm, spin axis sep 39°, arm angle sep 10.0°, extension sep 0.11 ft, API break sep 1.9 in, release distinct release (0.45 ft)
- CU vs primary FF:, velo sep 14.9 mph, move sep 1.9 in, eff speed sep 14.8 mph, spin sep 135 rpm, spin axis sep 144°, arm angle sep 0.7°, extension sep 0.08 ft, API break sep 2.9 in, release strong tunnel (0.11 ft)
- ST vs primary FF:, velo sep 12.4 mph, move sep 1.8 in, eff speed sep 12.5 mph, spin sep 76 rpm, spin axis sep 130°, arm angle sep 5.6°, extension sep 0.13 ft, API break sep 2.4 in, release strong tunnel (0.25 ft)
- SL vs primary FF:, velo sep 11.0 mph, move sep 1.4 in, eff speed sep 10.9 mph, spin sep 78 rpm, spin axis sep 101°, arm angle sep 6.8°, extension sep 0.07 ft, API break sep 2.0 in, release moderate tunnel (0.36 ft)
- CS vs primary FF:, velo sep 19.2 mph, move sep 2.5 in, eff speed sep 19.5 mph, spin sep 52 rpm, spin axis sep 158°, arm angle sep 0.4°, extension sep 0.17 ft, API break sep 3.8 in, release strong tunnel (0.18 ft)

**Post-trade**
- CH vs primary FF:, velo sep 6.8 mph, move sep 1.2 in, eff speed sep 6.9 mph, spin sep 370 rpm, spin axis sep 35°, arm angle sep 7.3°, extension sep 0.01 ft, API break sep 1.6 in, release moderate tunnel (0.32 ft)
- CU vs primary FF:, velo sep 14.3 mph, move sep 1.8 in, eff speed sep 14.2 mph, spin sep 148 rpm, spin axis sep 146°, arm angle sep 1.4°, extension sep 0.02 ft, API break sep 2.7 in, release strong tunnel (0.12 ft)
- ST vs primary FF:, velo sep 11.5 mph, move sep 1.6 in, eff speed sep 11.8 mph, spin sep 89 rpm, spin axis sep 122°, arm angle sep 3.0°, extension sep 0.15 ft, API break sep 2.2 in, release strong tunnel (0.25 ft)

### Shape metrics by pitch type

#### CH · Changeup

| Metric | Pre | Post | Δ |
| --- | ---: | ---: | ---: |
| Arm angle (deg) | 25.85 | 29.70 | +3.85 |
| Release height Z (ft) | 4.98 | 5.02 | +0.04 |
| Extension (ft) | 6.40 | 6.58 | +0.18 |
| Spin rate (rpm) | 1938.92 | 2037.05 | +98.13 |
| Effective speed (mph) | 87.18 | 87.55 | +0.37 |
| Break Z w/ gravity (in) | 2.78 | 2.64 | -0.14 |
| Release speed (mph) | 87.25 | 87.06 | -0.19 |
| Spin axis (deg) | 252.40 | 249.81 | -2.59 |
| Release side X (ft) | -3.58 | -3.80 | -0.22 |
| Release depth Y (ft) | 54.10 | 53.94 | -0.16 |
| PFX horizontal (in) | -1.47 | -1.30 | +0.17 |
| PFX vertical (in) | 0.23 | 0.37 | +0.14 |
| Break X arm (in) | 1.47 | 1.30 | -0.17 |
| Break X batter-in (in) | -0.68 | -0.59 | +0.09 |

#### CS · Slow Curve

| Metric | Pre | Post | Δ |
| --- | ---: | ---: | ---: |
| Arm angle (deg) | 35.48 | — | — |
| Release height Z (ft) | 5.34 | — | — |
| Extension (ft) | 6.34 | — | — |
| Spin rate (rpm) | 2371.62 | — | — |
| Effective speed (mph) | 74.84 | — | — |
| Break Z w/ gravity (in) | 4.81 | — | — |
| Release speed (mph) | 74.96 | — | — |
| Spin axis (deg) | 55.79 | — | — |
| Release side X (ft) | -3.26 | — | — |
| Release depth Y (ft) | 54.17 | — | — |
| PFX horizontal (in) | 0.64 | — | — |
| PFX vertical (in) | -0.73 | — | — |
| Break X arm (in) | -0.64 | — | — |
| Break X batter-in (in) | 0.23 | — | — |

#### CU · Curveball

| Metric | Pre | Post | Δ |
| --- | ---: | ---: | ---: |
| Arm angle (deg) | 35.15 | 38.44 | +3.29 |
| Release height Z (ft) | 5.33 | 5.33 | +0.00 |
| Extension (ft) | 6.43 | 6.57 | +0.14 |
| Spin rate (rpm) | 2288.03 | 2259.11 | -28.92 |
| Effective speed (mph) | 79.50 | 80.34 | +0.84 |
| Break Z w/ gravity (in) | 3.91 | 3.85 | -0.06 |
| Release speed (mph) | 79.24 | 79.50 | +0.26 |
| Spin axis (deg) | 69.73 | 68.61 | -1.12 |
| Release side X (ft) | -3.33 | -3.49 | -0.16 |
| Release depth Y (ft) | 54.07 | 53.93 | -0.14 |
| PFX horizontal (in) | 0.40 | 0.38 | -0.02 |
| PFX vertical (in) | -0.28 | -0.28 | +0.00 |
| Break X arm (in) | -0.40 | -0.38 | +0.02 |
| Break X batter-in (in) | 0.23 | 0.24 | +0.01 |

#### FF · 4-Seam

| Metric | Pre | Post | Δ |
| --- | ---: | ---: | ---: |
| Arm angle (deg) | 35.83 | 37.04 | +1.21 |
| Release height Z (ft) | 5.29 | 5.24 | -0.05 |
| Extension (ft) | 6.51 | 6.59 | +0.08 |
| Spin rate (rpm) | 2423.30 | 2407.10 | -16.20 |
| Effective speed (mph) | 94.35 | 94.49 | +0.14 |
| Break Z w/ gravity (in) | 1.20 | 1.32 | +0.12 |
| Release speed (mph) | 94.18 | 93.85 | -0.33 |
| Spin axis (deg) | 213.74 | 214.90 | +1.16 |
| Release side X (ft) | -3.27 | -3.57 | -0.30 |
| Release depth Y (ft) | 53.99 | 53.92 | -0.07 |
| PFX horizontal (in) | -0.59 | -0.53 | +0.06 |
| PFX vertical (in) | 1.39 | 1.26 | -0.13 |
| Break X arm (in) | 0.59 | 0.53 | -0.06 |
| Break X batter-in (in) | -0.17 | -0.12 | +0.05 |

#### SL · Slider

| Metric | Pre | Post | Δ |
| --- | ---: | ---: | ---: |
| Arm angle (deg) | 28.99 | — | — |
| Release height Z (ft) | 5.05 | — | — |
| Extension (ft) | 6.44 | — | — |
| Spin rate (rpm) | 2345.58 | — | — |
| Effective speed (mph) | 83.41 | — | — |
| Break Z w/ gravity (in) | 3.00 | — | — |
| Release speed (mph) | 83.17 | — | — |
| Spin axis (deg) | 112.59 | — | — |
| Release side X (ft) | -3.52 | — | — |
| Release depth Y (ft) | 54.06 | — | — |
| PFX horizontal (in) | 0.23 | — | — |
| PFX vertical (in) | 0.30 | — | — |
| Break X arm (in) | -0.23 | — | — |
| Break X batter-in (in) | -0.10 | — | — |

#### ST · Sweeper

| Metric | Pre | Post | Δ |
| --- | ---: | ---: | ---: |
| Arm angle (deg) | 30.22 | 34.03 | +3.81 |
| Release height Z (ft) | 5.13 | 5.15 | +0.02 |
| Extension (ft) | 6.38 | 6.44 | +0.06 |
| Spin rate (rpm) | 2499.00 | 2495.60 | -3.40 |
| Effective speed (mph) | 81.89 | 82.70 | +0.81 |
| Break Z w/ gravity (in) | 2.98 | 2.93 | -0.05 |
| Release speed (mph) | 81.76 | 82.38 | +0.62 |
| Spin axis (deg) | 83.26 | 93.00 | +9.74 |
| Release side X (ft) | -3.41 | -3.75 | -0.34 |
| Release depth Y (ft) | 54.12 | 54.06 | -0.06 |
| PFX horizontal (in) | 0.94 | 0.82 | -0.12 |
| PFX vertical (in) | 0.44 | 0.43 | -0.01 |
| Break X arm (in) | -0.94 | -0.82 | +0.12 |
| Break X batter-in (in) | -0.36 | -0.82 | -0.46 |

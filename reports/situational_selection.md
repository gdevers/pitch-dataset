# Situational Pitch Selection Report

_Situational model scored on MLB 2026 pitches (2026-03-25 → 2026-09-06, n=635,803). Micro pitch-choice (not season usage optimization)._

Micro pitch-choice recommendations: which pitch **minimizes predicted xwOBA** for this batter, count, and game state — not season-long usage optimization.

## Cease vs Devers

- Count: **1-2** | LHH vs RHP | high leverage (proxy 0.65)
- Outs: 2 | Runners on: 1 | Score diff (fld-bat): 0
- Previous pitch: **FF**
- Recommended: **FF** (default in situation: SL)
- Expected improvement vs default: **-0.029 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| FF | 0.251 | -0.0091 | pick |
| SL | 0.280 | +0.0103 | default |
| SI | 0.289 | +0.0118 |  |
| ST | 0.293 | +0.0129 |  |
| KC | 0.300 | +0.0138 |  |
| CH | 0.302 | +0.0128 |  |

## Cease vs Abreu

- Count: **0-2** | LHH vs RHP | medium leverage (proxy 0.40)
- Outs: 1 | Runners on: 0 | Score diff (fld-bat): 0
- Recommended: **FF** (default in situation: FF)
- Expected improvement vs default: **-0.000 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| FF | 0.262 | -0.0087 | pick |
| SL | 0.290 | +0.0077 |  |
| SI | 0.293 | +0.0068 |  |
| ST | 0.300 | +0.0112 |  |
| CH | 0.304 | +0.0077 |  |
| KC | 0.316 | +0.0139 |  |

## Skubal vs Judge

- Count: **2-2** | RHH vs LHP | high leverage (proxy 0.65)
- Outs: 2 | Runners on: 2 | Score diff (fld-bat): -1
- Recommended: **FF** (default in situation: CH)
- Expected improvement vs default: **-0.025 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| FF | 0.288 | +0.0062 | pick |
| CU | 0.294 | +0.0160 |  |
| SI | 0.300 | +0.0154 |  |
| SL | 0.302 | +0.0151 |  |
| CH | 0.314 | +0.0204 | default |

## Skenes vs Ohtani

- Count: **1-1** | LHH vs RHP | medium leverage (proxy 0.40)
- Outs: 0 | Runners on: 0 | Score diff (fld-bat): 0
- Recommended: **ST** (default in situation: FF)
- Expected improvement vs default: **-0.008 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| ST | 0.298 | +0.0172 | pick |
| SL | 0.301 | +0.0174 |  |
| SI | 0.303 | +0.0169 |  |
| FF | 0.305 | +0.0201 | default |
| FS | 0.311 | +0.0193 |  |
| CH | 0.315 | +0.0200 |  |

## Gausman vs Guerrero

- Count: **3-2** | RHH vs RHP | high leverage (proxy 0.65)
- Outs: 2 | Runners on: 1 | Score diff (fld-bat): 1
- Recommended: **SL** (default in situation: FF)
- Expected improvement vs default: **-0.002 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| SL | 0.334 | -0.0024 | pick |
| FF | 0.336 | +0.0037 | default |
| FS | 0.337 | -0.0046 |  |
| CH | 0.340 | +0.0190 |  |

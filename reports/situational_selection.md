# Situational Pitch Selection Report

_Situational model scored on MLB 2026 pitches (2026-03-25 → 2026-08-30, n=606,903). Micro pitch-choice (not season usage optimization)._

Micro pitch-choice recommendations: which pitch **minimizes predicted xwOBA** for this batter, count, and game state — not season-long usage optimization.

## Cease vs Devers

- Count: **1-2** | LHH vs RHP | high leverage (proxy 0.65)
- Outs: 2 | Runners on: 1 | Score diff (fld-bat): 0
- Previous pitch: **FF**
- Recommended: **FF** (default in situation: SL)
- Expected improvement vs default: **-0.029 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| FF | 0.256 | -0.0031 | pick |
| SI | 0.282 | +0.0072 |  |
| ST | 0.285 | +0.0097 |  |
| SL | 0.285 | +0.0084 | default |
| CH | 0.288 | +0.0081 |  |
| KC | 0.292 | +0.0097 |  |

## Cease vs Abreu

- Count: **0-2** | LHH vs RHP | medium leverage (proxy 0.40)
- Outs: 1 | Runners on: 0 | Score diff (fld-bat): 0
- Recommended: **FF** (default in situation: FF)
- Expected improvement vs default: **-0.000 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| FF | 0.263 | -0.0043 | pick |
| CH | 0.287 | +0.0074 |  |
| SL | 0.289 | +0.0073 |  |
| ST | 0.289 | +0.0086 |  |
| KC | 0.310 | +0.0076 |  |
| SI | 0.319 | +0.0065 |  |

## Skubal vs Judge

- Count: **2-2** | RHH vs LHP | high leverage (proxy 0.65)
- Outs: 2 | Runners on: 2 | Score diff (fld-bat): -1
- Recommended: **CU** (default in situation: CH)
- Expected improvement vs default: **-0.016 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| CU | 0.289 | +0.0104 | pick |
| FF | 0.293 | +0.0117 |  |
| SL | 0.295 | +0.0135 |  |
| SI | 0.298 | +0.0171 |  |
| CH | 0.304 | +0.0117 | default |

## Skenes vs Ohtani

- Count: **1-1** | LHH vs RHP | medium leverage (proxy 0.40)
- Outs: 0 | Runners on: 0 | Score diff (fld-bat): 0
- Recommended: **FS** (default in situation: FF)
- Expected improvement vs default: **-0.024 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| FS | 0.282 | +0.0084 | pick |
| SL | 0.283 | +0.0095 |  |
| SI | 0.296 | +0.0106 |  |
| ST | 0.296 | +0.0095 |  |
| FF | 0.306 | +0.0149 | default |
| CH | 0.309 | +0.0092 |  |

## Gausman vs Guerrero

- Count: **3-2** | RHH vs RHP | high leverage (proxy 0.65)
- Outs: 2 | Runners on: 1 | Score diff (fld-bat): 1
- Recommended: **FS** (default in situation: FF)
- Expected improvement vs default: **-0.018 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| FS | 0.317 | -0.0051 | pick |
| SL | 0.332 | -0.0045 |  |
| FF | 0.335 | -0.0002 | default |
| CH | 0.373 | -0.0046 |  |

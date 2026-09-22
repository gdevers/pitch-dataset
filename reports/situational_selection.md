# Situational Pitch Selection Report

_Situational model scored on MLB 2026 pitches (2026-03-25 → 2026-09-20, n=690,489). Micro pitch-choice (not season usage optimization)._

Micro pitch-choice recommendations: which pitch **minimizes predicted xwOBA** for this batter, count, and game state — not season-long usage optimization.

## Cease vs Devers

- Count: **1-2** | LHH vs RHP | high leverage (proxy 0.65)
- Outs: 2 | Runners on: 1 | Score diff (fld-bat): 0
- Previous pitch: **FF**
- Recommended: **FF** (default in situation: SL)
- Expected improvement vs default: **-0.031 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| FF | 0.254 | +0.0009 | pick |
| SL | 0.285 | +0.0107 | default |
| CH | 0.297 | +0.0119 |  |
| ST | 0.297 | +0.0126 |  |
| SI | 0.301 | +0.0116 |  |
| KC | 0.304 | +0.0120 |  |

## Cease vs Abreu

- Count: **0-2** | LHH vs RHP | medium leverage (proxy 0.40)
- Outs: 1 | Runners on: 0 | Score diff (fld-bat): 0
- Recommended: **FF** (default in situation: FF)
- Expected improvement vs default: **-0.000 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| FF | 0.269 | -0.0034 | pick |
| SL | 0.294 | +0.0067 |  |
| CH | 0.296 | +0.0045 |  |
| SI | 0.302 | +0.0070 |  |
| ST | 0.305 | +0.0080 |  |
| KC | 0.315 | +0.0080 |  |

## Skubal vs Judge

- Count: **2-2** | RHH vs LHP | high leverage (proxy 0.65)
- Outs: 2 | Runners on: 2 | Score diff (fld-bat): -1
- Recommended: **FF** (default in situation: FF)
- Expected improvement vs default: **-0.000 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| FF | 0.268 | +0.0111 | pick |
| SL | 0.288 | +0.0207 |  |
| CU | 0.297 | +0.0148 |  |
| SI | 0.297 | +0.0112 |  |
| CH | 0.302 | +0.0184 |  |

## Skenes vs Ohtani

- Count: **1-1** | LHH vs RHP | medium leverage (proxy 0.40)
- Outs: 0 | Runners on: 0 | Score diff (fld-bat): 0
- Recommended: **ST** (default in situation: FF)
- Expected improvement vs default: **-0.013 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| ST | 0.276 | +0.0126 | pick |
| SI | 0.280 | +0.0097 |  |
| SL | 0.281 | +0.0123 |  |
| FF | 0.290 | +0.0139 | default |
| FS | 0.291 | +0.0115 |  |
| CH | 0.294 | +0.0117 |  |

## Gausman vs Guerrero

- Count: **3-2** | RHH vs RHP | high leverage (proxy 0.65)
- Outs: 2 | Runners on: 1 | Score diff (fld-bat): 1
- Recommended: **FS** (default in situation: FF)
- Expected improvement vs default: **-0.013 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| FS | 0.312 | -0.0016 | pick |
| SL | 0.325 | +0.0002 |  |
| FF | 0.325 | +0.0031 | default |
| CH | 0.344 | +0.0033 |  |

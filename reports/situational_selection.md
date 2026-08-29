# Situational Pitch Selection Report

_Situational model scored on MLB 2026 pitches (2026-03-25 → 2026-08-27, n=593,334). Micro pitch-choice (not season usage optimization)._

Micro pitch-choice recommendations: which pitch **minimizes predicted xwOBA** for this batter, count, and game state — not season-long usage optimization.

## Cease vs Devers

- Count: **1-2** | LHH vs RHP | high leverage (proxy 0.65)
- Outs: 2 | Runners on: 1 | Score diff (fld-bat): 0
- Previous pitch: **FF**
- Recommended: **FF** (default in situation: SL)
- Expected improvement vs default: **-0.028 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| FF | 0.253 | -0.0002 | pick |
| SL | 0.281 | +0.0073 | default |
| SI | 0.285 | +0.0057 |  |
| CH | 0.288 | +0.0069 |  |
| ST | 0.294 | +0.0106 |  |
| KC | 0.296 | +0.0092 |  |

## Cease vs Abreu

- Count: **0-2** | LHH vs RHP | medium leverage (proxy 0.40)
- Outs: 1 | Runners on: 0 | Score diff (fld-bat): 0
- Recommended: **FF** (default in situation: FF)
- Expected improvement vs default: **-0.000 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| FF | 0.263 | +0.0008 | pick |
| SL | 0.283 | +0.0038 |  |
| CH | 0.287 | +0.0030 |  |
| ST | 0.297 | +0.0067 |  |
| SI | 0.300 | +0.0067 |  |
| KC | 0.302 | +0.0061 |  |

## Skubal vs Judge

- Count: **2-2** | RHH vs LHP | high leverage (proxy 0.65)
- Outs: 2 | Runners on: 2 | Score diff (fld-bat): -1
- Recommended: **FF** (default in situation: CH)
- Expected improvement vs default: **-0.037 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| FF | 0.288 | +0.0137 | pick |
| SI | 0.297 | +0.0195 |  |
| CU | 0.298 | +0.0142 |  |
| SL | 0.319 | +0.0158 |  |
| CH | 0.326 | +0.0299 | default |

## Skenes vs Ohtani

- Count: **1-1** | LHH vs RHP | medium leverage (proxy 0.40)
- Outs: 0 | Runners on: 0 | Score diff (fld-bat): 0
- Recommended: **SL** (default in situation: FF)
- Expected improvement vs default: **-0.000 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| SL | 0.292 | +0.0242 | pick |
| FF | 0.292 | +0.0235 | default |
| ST | 0.294 | +0.0209 |  |
| SI | 0.297 | +0.0242 |  |
| FS | 0.301 | +0.0270 |  |
| CH | 0.308 | +0.0271 |  |

## Gausman vs Guerrero

- Count: **3-2** | RHH vs RHP | high leverage (proxy 0.65)
- Outs: 2 | Runners on: 1 | Score diff (fld-bat): 1
- Recommended: **FF** (default in situation: FF)
- Expected improvement vs default: **-0.000 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| FF | 0.311 | -0.0047 | pick |
| FS | 0.320 | -0.0067 |  |
| SL | 0.326 | -0.0085 |  |
| CH | 0.328 | +0.0003 |  |

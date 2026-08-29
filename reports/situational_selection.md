# Situational Pitch Selection Report

_Situational model scored on MLB 2026 pitches (2026-03-25 → 2026-08-27, n=593,334). Micro pitch-choice (not season usage optimization)._

Micro pitch-choice recommendations: which pitch **minimizes predicted xwOBA** for this batter, count, and game state — not season-long usage optimization.

## Cease vs Devers

- Count: **1-2** | LHH vs RHP | high leverage (proxy 0.65)
- Outs: 2 | Runners on: 1 | Score diff (fld-bat): 0
- Previous pitch: **FF**
- Recommended: **FF** (default in situation: SL)
- Expected improvement vs default: **-0.039 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| FF | 0.254 | +0.0004 | pick |
| CH | 0.288 | +0.0054 |  |
| SI | 0.289 | +0.0057 |  |
| SL | 0.292 | +0.0064 | default |
| KC | 0.296 | +0.0113 |  |
| ST | 0.296 | +0.0107 |  |

## Cease vs Abreu

- Count: **0-2** | LHH vs RHP | medium leverage (proxy 0.40)
- Outs: 1 | Runners on: 0 | Score diff (fld-bat): 0
- Recommended: **FF** (default in situation: FF)
- Expected improvement vs default: **-0.000 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| FF | 0.263 | +0.0036 | pick |
| SL | 0.289 | +0.0024 |  |
| CH | 0.295 | +0.0021 |  |
| ST | 0.298 | +0.0062 |  |
| SI | 0.299 | +0.0074 |  |
| KC | 0.309 | +0.0067 |  |

## Skubal vs Judge

- Count: **2-2** | RHH vs LHP | high leverage (proxy 0.65)
- Outs: 2 | Runners on: 2 | Score diff (fld-bat): -1
- Recommended: **CU** (default in situation: CH)
- Expected improvement vs default: **-0.028 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| CU | 0.286 | +0.0156 | pick |
| FF | 0.287 | +0.0087 |  |
| SL | 0.301 | +0.0184 |  |
| SI | 0.303 | +0.0185 |  |
| CH | 0.314 | +0.0229 | default |

## Skenes vs Ohtani

- Count: **1-1** | LHH vs RHP | medium leverage (proxy 0.40)
- Outs: 0 | Runners on: 0 | Score diff (fld-bat): 0
- Recommended: **FF** (default in situation: FF)
- Expected improvement vs default: **-0.000 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| FF | 0.288 | +0.0187 | pick |
| SL | 0.291 | +0.0156 |  |
| ST | 0.293 | +0.0145 |  |
| SI | 0.296 | +0.0166 |  |
| FS | 0.301 | +0.0178 |  |
| CH | 0.307 | +0.0212 |  |

## Gausman vs Guerrero

- Count: **3-2** | RHH vs RHP | high leverage (proxy 0.65)
- Outs: 2 | Runners on: 1 | Score diff (fld-bat): 1
- Recommended: **FF** (default in situation: FF)
- Expected improvement vs default: **-0.000 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| FF | 0.315 | -0.0007 | pick |
| FS | 0.320 | -0.0061 |  |
| SL | 0.324 | -0.0047 |  |
| CH | 0.339 | -0.0005 |  |

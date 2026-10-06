# Situational Pitch Selection Report

_Situational model scored on MLB 2026 pitches (2026-03-25 → 2026-10-05, n=721,682). Micro pitch-choice (not season usage optimization)._

Micro pitch-choice recommendations: which pitch **minimizes predicted xwOBA** for this batter, count, and game state — not season-long usage optimization.

## Cease vs Devers

- Count: **1-2** | LHH vs RHP | high leverage (proxy 0.65)
- Outs: 2 | Runners on: 1 | Score diff (fld-bat): 0
- Previous pitch: **FF**
- Recommended: **FF** (default in situation: SL)
- Expected improvement vs default: **-0.031 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| FF | 0.255 | -0.0004 | pick |
| SL | 0.286 | +0.0085 | default |
| ST | 0.291 | +0.0142 |  |
| SI | 0.292 | +0.0174 |  |
| KC | 0.293 | +0.0210 |  |
| CH | 0.305 | +0.0111 |  |

Top locations for **FF** (batter-relative; glove side = in):

| Rank | Location | Runs saved /100 | Pred xwOBA | Whiff |
| ---: | --- | ---: | ---: | ---: |
| 1 | Up & away | +2.73 | 0.162 | 30.4% |
| 2 | Down & away | +2.47 | 0.143 | 5.3% |
| 3 | Down & in | +1.85 | 0.158 | 5.7% |

## Cease vs Abreu

- Count: **0-2** | LHH vs RHP | medium leverage (proxy 0.40)
- Outs: 1 | Runners on: 0 | Score diff (fld-bat): 0
- Recommended: **FF** (default in situation: FF)
- Expected improvement vs default: **-0.000 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| FF | 0.264 | -0.0025 | pick |
| SL | 0.292 | +0.0041 |  |
| SI | 0.294 | +0.0083 |  |
| ST | 0.294 | +0.0099 |  |
| CH | 0.297 | +0.0040 |  |
| KC | 0.303 | +0.0106 |  |

Top locations for **FF** (batter-relative; glove side = in):

| Rank | Location | Runs saved /100 | Pred xwOBA | Whiff |
| ---: | --- | ---: | ---: | ---: |
| 1 | Down & away | +2.97 | 0.143 | 6.0% |
| 2 | Down, middle | +2.59 | 0.168 | 6.6% |
| 3 | Chase up & in | +2.28 | 0.232 | 20.0% |

## Skubal vs Judge

- Count: **2-2** | RHH vs LHP | high leverage (proxy 0.65)
- Outs: 2 | Runners on: 2 | Score diff (fld-bat): -1
- Recommended: **FF** (default in situation: FF)
- Expected improvement vs default: **-0.000 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| FF | 0.281 | +0.0086 | pick |
| SL | 0.285 | +0.0147 |  |
| CU | 0.285 | +0.0087 |  |
| CH | 0.294 | +0.0198 |  |
| SI | 0.303 | +0.0200 |  |

Top locations for **FF** (batter-relative; glove side = in):

| Rank | Location | Runs saved /100 | Pred xwOBA | Whiff |
| ---: | --- | ---: | ---: | ---: |
| 1 | Down & in | +2.74 | 0.174 | 5.3% |
| 2 | Down & away | +1.86 | 0.180 | 8.9% |
| 3 | Up & away | +1.50 | 0.205 | 23.2% |

## Skenes vs Ohtani

- Count: **1-1** | LHH vs RHP | medium leverage (proxy 0.40)
- Outs: 0 | Runners on: 0 | Score diff (fld-bat): 0
- Recommended: **ST** (default in situation: FF)
- Expected improvement vs default: **-0.005 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| ST | 0.292 | +0.0383 | pick |
| FS | 0.295 | +0.0188 |  |
| FF | 0.296 | +0.0206 | default |
| SL | 0.299 | +0.0381 |  |
| SI | 0.300 | +0.0179 |  |
| CH | 0.308 | +0.0162 |  |

Top locations for **ST** (batter-relative; glove side = in):

| Rank | Location | Runs saved /100 | Pred xwOBA | Whiff |
| ---: | --- | ---: | ---: | ---: |
| 1 | Down & away | +0.53 | 0.184 | 8.6% |
| 2 | Up & away | +0.33 | 0.181 | 10.6% |
| 3 | Middle away | +0.28 | 0.209 | 8.1% |

## Gausman vs Guerrero

- Count: **3-2** | RHH vs RHP | high leverage (proxy 0.65)
- Outs: 2 | Runners on: 1 | Score diff (fld-bat): 1
- Recommended: **FS** (default in situation: FF)
- Expected improvement vs default: **-0.021 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| FS | 0.317 | -0.0161 | pick |
| SL | 0.325 | -0.0045 |  |
| FF | 0.338 | +0.0014 | default |
| CH | 0.370 | +0.0152 |  |

Top locations for **FS** (batter-relative; glove side = away):

| Rank | Location | Runs saved /100 | Pred xwOBA | Whiff |
| ---: | --- | ---: | ---: | ---: |
| 1 | Down, middle | +4.42 | 0.221 | 17.3% |
| 2 | Down & away | +4.11 | 0.191 | 16.9% |
| 3 | Up & in | +3.76 | 0.198 | 3.1% |

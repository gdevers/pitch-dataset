# Situational Pitch Selection Report

_Situational model scored on MLB 2026 pitches (2026-03-25 → 2026-10-28, n=728,343). Micro pitch-choice (not season usage optimization)._

Micro pitch-choice recommendations: which pitch **minimizes predicted xwOBA** for this batter, count, and game state — not season-long usage optimization.

## Cease vs Devers

- Count: **1-2** | LHH vs RHP | high leverage (proxy 0.65)
- Outs: 2 | Runners on: 1 | Score diff (fld-bat): 0
- Previous pitch: **FF**
- Recommended: **FF** (default in situation: SL)
- Expected improvement vs default: **-0.039 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| FF | 0.255 | +0.0045 | pick |
| SL | 0.294 | +0.0098 | default |
| ST | 0.296 | +0.0123 |  |
| KC | 0.296 | +0.0129 |  |
| SI | 0.303 | +0.0101 |  |
| CH | 0.306 | +0.0122 |  |

Top locations for **FF** (batter-relative; glove side = in):

| Rank | Location | Runs saved /100 | Pred xwOBA | Whiff |
| ---: | --- | ---: | ---: | ---: |
| 1 | Down & away | +4.13 | 0.159 | 4.9% |
| 2 | Down & in | +2.03 | 0.177 | 3.9% |
| 3 | Middle away | +1.85 | 0.175 | 15.5% |

## Cease vs Abreu

- Count: **0-2** | LHH vs RHP | medium leverage (proxy 0.40)
- Outs: 1 | Runners on: 0 | Score diff (fld-bat): 0
- Recommended: **FF** (default in situation: FF)
- Expected improvement vs default: **-0.000 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| FF | 0.258 | -0.0079 | pick |
| SL | 0.290 | +0.0015 |  |
| CH | 0.296 | +0.0047 |  |
| SI | 0.297 | +0.0020 |  |
| ST | 0.300 | +0.0048 |  |
| KC | 0.305 | +0.0048 |  |

Top locations for **FF** (batter-relative; glove side = in):

| Rank | Location | Runs saved /100 | Pred xwOBA | Whiff |
| ---: | --- | ---: | ---: | ---: |
| 1 | Down & away | +3.09 | 0.146 | 7.3% |
| 2 | Up & in | +2.90 | 0.170 | 13.5% |
| 3 | Chase up & in | +2.56 | 0.241 | 17.5% |

## Skubal vs Judge

- Count: **2-2** | RHH vs LHP | high leverage (proxy 0.65)
- Outs: 2 | Runners on: 2 | Score diff (fld-bat): -1
- Recommended: **FF** (default in situation: FF)
- Expected improvement vs default: **-0.000 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| FF | 0.269 | +0.0064 | pick |
| CU | 0.284 | +0.0092 |  |
| SL | 0.285 | +0.0128 |  |
| SI | 0.295 | +0.0114 |  |
| CH | 0.310 | +0.0131 |  |

Top locations for **FF** (batter-relative; glove side = in):

| Rank | Location | Runs saved /100 | Pred xwOBA | Whiff |
| ---: | --- | ---: | ---: | ---: |
| 1 | Down & in | +4.63 | 0.173 | 5.3% |
| 2 | Down & away | +4.62 | 0.156 | 8.8% |
| 3 | Up & in | +2.56 | 0.217 | 12.7% |

## Skenes vs Ohtani

- Count: **1-1** | LHH vs RHP | medium leverage (proxy 0.40)
- Outs: 0 | Runners on: 0 | Score diff (fld-bat): 0
- Recommended: **ST** (default in situation: FF)
- Expected improvement vs default: **-0.009 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| ST | 0.285 | +0.0173 | pick |
| SL | 0.286 | +0.0117 |  |
| SI | 0.290 | +0.0068 |  |
| FF | 0.294 | +0.0154 | default |
| CH | 0.304 | +0.0138 |  |
| FS | 0.308 | +0.0124 |  |

Top locations for **ST** (batter-relative; glove side = in):

| Rank | Location | Runs saved /100 | Pred xwOBA | Whiff |
| ---: | --- | ---: | ---: | ---: |
| 1 | Down & away | +1.87 | 0.186 | 8.4% |
| 2 | Middle away | +1.33 | 0.204 | 7.1% |
| 3 | Up & away | +1.16 | 0.175 | 7.1% |

## Gausman vs Guerrero

- Count: **3-2** | RHH vs RHP | high leverage (proxy 0.65)
- Outs: 2 | Runners on: 1 | Score diff (fld-bat): 1
- Recommended: **FS** (default in situation: FF)
- Expected improvement vs default: **-0.029 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| FS | 0.310 | -0.0054 | pick |
| ST | 0.319 | -0.0002 |  |
| SL | 0.326 | -0.0008 |  |
| CH | 0.333 | -0.0054 |  |
| FF | 0.339 | +0.0027 | default |

Top locations for **FS** (batter-relative; glove side = away):

| Rank | Location | Runs saved /100 | Pred xwOBA | Whiff |
| ---: | --- | ---: | ---: | ---: |
| 1 | Down, middle | +4.85 | 0.188 | 19.4% |
| 2 | Down & away | +4.30 | 0.186 | 17.9% |
| 3 | Down & in | +3.78 | 0.219 | 16.3% |

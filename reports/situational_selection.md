# Situational Pitch Selection Report

_Situational model scored on MLB 2026 pitches (2026-03-25 → 2026-10-11, n=724,326). Micro pitch-choice (not season usage optimization)._

Micro pitch-choice recommendations: which pitch **minimizes predicted xwOBA** for this batter, count, and game state — not season-long usage optimization.

## Cease vs Devers

- Count: **1-2** | LHH vs RHP | high leverage (proxy 0.65)
- Outs: 2 | Runners on: 1 | Score diff (fld-bat): 0
- Previous pitch: **FF**
- Recommended: **FF** (default in situation: SL)
- Expected improvement vs default: **-0.044 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| FF | 0.253 | +0.0071 | pick |
| KC | 0.296 | +0.0147 |  |
| SL | 0.297 | +0.0135 | default |
| SI | 0.299 | +0.0123 |  |
| ST | 0.300 | +0.0166 |  |
| CH | 0.309 | +0.0164 |  |

Top locations for **FF** (batter-relative; glove side = in):

| Rank | Location | Runs saved /100 | Pred xwOBA | Whiff |
| ---: | --- | ---: | ---: | ---: |
| 1 | Down & away | +2.99 | 0.175 | 6.6% |
| 2 | Up & away | +2.45 | 0.190 | 27.4% |
| 3 | Chase up & in | +1.99 | 0.240 | 19.7% |

## Cease vs Abreu

- Count: **0-2** | LHH vs RHP | medium leverage (proxy 0.40)
- Outs: 1 | Runners on: 0 | Score diff (fld-bat): 0
- Recommended: **FF** (default in situation: FF)
- Expected improvement vs default: **-0.000 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| FF | 0.251 | -0.0093 | pick |
| SL | 0.292 | +0.0053 |  |
| SI | 0.294 | +0.0024 |  |
| CH | 0.302 | +0.0041 |  |
| KC | 0.303 | +0.0082 |  |
| ST | 0.310 | +0.0067 |  |

Top locations for **FF** (batter-relative; glove side = in):

| Rank | Location | Runs saved /100 | Pred xwOBA | Whiff |
| ---: | --- | ---: | ---: | ---: |
| 1 | Down & away | +4.27 | 0.146 | 5.6% |
| 2 | Up & in | +2.82 | 0.170 | 11.6% |
| 3 | Down, middle | +2.76 | 0.145 | 5.3% |

## Skubal vs Judge

- Count: **2-2** | RHH vs LHP | high leverage (proxy 0.65)
- Outs: 2 | Runners on: 2 | Score diff (fld-bat): -1
- Recommended: **FF** (default in situation: FF)
- Expected improvement vs default: **-0.000 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| FF | 0.282 | +0.0154 | pick |
| SL | 0.282 | +0.0126 |  |
| CU | 0.288 | +0.0158 |  |
| SI | 0.292 | +0.0096 |  |
| CH | 0.302 | +0.0097 |  |

Top locations for **FF** (batter-relative; glove side = in):

| Rank | Location | Runs saved /100 | Pred xwOBA | Whiff |
| ---: | --- | ---: | ---: | ---: |
| 1 | Down & in | +2.94 | 0.185 | 3.6% |
| 2 | Down & away | +2.41 | 0.183 | 7.4% |
| 3 | Middle in | +1.27 | 0.231 | 8.2% |

## Skenes vs Ohtani

- Count: **1-1** | LHH vs RHP | medium leverage (proxy 0.40)
- Outs: 0 | Runners on: 0 | Score diff (fld-bat): 0
- Recommended: **SL** (default in situation: FF)
- Expected improvement vs default: **-0.010 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| SL | 0.284 | +0.0149 | pick |
| ST | 0.290 | +0.0167 |  |
| FF | 0.294 | +0.0188 | default |
| SI | 0.295 | +0.0088 |  |
| FS | 0.300 | +0.0156 |  |
| CH | 0.306 | +0.0182 |  |

Top locations for **SL** (batter-relative; glove side = in):

| Rank | Location | Runs saved /100 | Pred xwOBA | Whiff |
| ---: | --- | ---: | ---: | ---: |
| 1 | Down & away | +1.31 | 0.210 | 12.9% |
| 2 | Up & away | +1.31 | 0.200 | 13.6% |
| 3 | Middle away | +1.10 | 0.222 | 10.7% |

## Gausman vs Guerrero

- Count: **3-2** | RHH vs RHP | high leverage (proxy 0.65)
- Outs: 2 | Runners on: 1 | Score diff (fld-bat): 1
- Recommended: **FS** (default in situation: FF)
- Expected improvement vs default: **-0.016 xwOBA**

| Pitch | Pred xwOBA | Pred RV | |
| --- | ---: | ---: | --- |
| FS | 0.315 | -0.0101 | pick |
| ST | 0.328 | -0.0012 |  |
| FF | 0.331 | -0.0001 | default |
| SL | 0.335 | -0.0032 |  |
| CH | 0.350 | -0.0027 |  |

Top locations for **FS** (batter-relative; glove side = away):

| Rank | Location | Runs saved /100 | Pred xwOBA | Whiff |
| ---: | --- | ---: | ---: | ---: |
| 1 | Down, middle | +3.65 | 0.216 | 18.6% |
| 2 | Down & away | +3.35 | 0.179 | 15.6% |
| 3 | Up & in | +3.01 | 0.195 | 4.2% |

# LinkedIn posts — pitch-dataset portfolio

Copy-paste captions for LinkedIn. Audience: MLB hiring, sports analytics, front office.
Demos are free on GitHub Pages (no install). Source: https://github.com/gdevers/pitch-dataset

---

## Overall portfolio (hub)

Most pitching tools either stay in a notebook or collapse into a single dashboard. I built a suite of **separate, shareable decision-support pieces** — each with its own link — so a scout, analyst, or coach can open one problem at a time.

**pitch-dataset** is an MLB pitching portfolio on top of Statcast:

- **Situational pitch selection** — rank type + location by expected xwOBA given count, leverage, and platoon  
- **Pitch-to-field** — spray, danger, and defense for hitter × pitch × zone  
- **3D strike zone** — true flight paths, tunneling, and back-of-zone calls  
- **Automated player reports** — two-page HTML/PDF evaluations with 20–80 grades and data-cited bottom lines  
- **Arsenal optimization & trade-deadline labs** — usage vs recommended mix; pre/post movers  

Every piece pairs a model with a readable visual. The interactive demos run in the browser on GitHub Pages — no install required. Full-roster live inference is available locally from the same repo.

Portfolio hub (each project linked separately):  
https://gdevers.github.io/pitch-dataset/

Happy to walk through methodology, validation choices, or how any of these would plug into a team’s stack.

#BaseballAnalytics #SportsAnalytics #MLB

---

## Situational pitch selection

Hook: What should this pitcher throw *right now* — and where?

I built an interactive **situational pitch selection** demo that ranks pitch type and location by expected xwOBA given pitcher, batter, count, leverage, and platoon. The UI is game-card style: pick a matchup, see the model’s ordering, and compare alternatives without digging through a spreadsheet.

Under the hood it’s a pitch-choice model plus a location step (batter-relative zones → run value / xwOBA / whiff). The public Pages demo ships a precomputed grid so anyone can click through immediately; the same codebase serves a full MLB roster with live inference locally.

For a team, this is the decision layer between “stuff grades” and “what do we call in 2–1 with a runner on.” Transparent enough to challenge; visual enough to share in a meeting.

Try it (free, no install):  
https://gdevers.github.io/pitch-dataset/pitch-selection.html

Happy to walk through features, holdout checks, or how recommendations are framed as direction rather than prescription.

#BaseballAnalytics #MLB

---

## Pitch-to-field

Hook: If I throw this pitch to this spot against this hitter — where does the ball go, and how should we play him?

**Pitch-to-field** answers that on a to-scale field. Pick hitter, pitch type, and a batter-relative zone; see spray colored by danger (xwOBA / hit probability), contact mix, exit velo, whiff context, and how much of the estimate is hitter-specific vs league.

Modes include count / pitcher-hand filters, brushing a field region to reverse-map zones and pitches, draggable fielders with a reach model and shift-rule-aware optimizer, pitcher matchup spray, hitter-vs-league / hitter-vs-hitter compare, and a date-ordered replay.

That combination — hierarchical spray model + defense UI — is aimed at advance work and in-game positioning conversations, not just a static heat map.

Interactive demo (GitHub Pages, no install):  
https://gdevers.github.io/pitch-dataset/pitch-to-field.html

Happy to walk through the shrinkage approach or the defense optimizer assumptions.

#BaseballAnalytics #SportsAnalytics

---

## 3D strike zone

Hook: A strike zone isn’t a rectangle on TV — pitches fly through a volume.

The **3D strike zone** demo reconstructs pitch trajectories through a real zone geometry (home plate’s 17″ pentagon extruded knees-to-letters). You can inspect tunneling, compare front-plane vs back-of-zone calls, and filter by pitcher with interactive orbit controls.

It’s built for conversations where 2D plots flatten the story: late break, decision-point separation, and whether a pitch that “looked like a strike” actually crossed the volume. Stats on tunneling and 3D calls sit next to the visual so the geometry stays tied to numbers.

For R&D, umpiring research, or pitcher development, this is a shareable artifact you can open in a browser — no local setup required for the demo set.

Open the demo:  
https://gdevers.github.io/pitch-dataset/zone-3d.html

Happy to dig into trajectory reconstruction or how 3D calls differ from the front plane.

#BaseballAnalytics #MLB

---

## Player evaluation reports

Hook: What if a player eval packet wrote itself — with every claim citing a number?

I automated **two-page pitcher and hitter evaluation reports** in the style of an MLB R&D / advance packet: season line, 20–80 grades from league percentiles, arsenal or swing-decision maps, count strategy, trends with IL overlays, comps, and a bottom line generated from a rules library so each sentence is a template filled with the computed number it cites.

Reports export as HTML and PDF. The gallery includes a set of headline pitchers and hitters; any player can be generated from the same CLI.

The point for a front office isn’t replacing the analyst — it’s compressing the first draft so humans spend time on judgment, not formatting. Effects from the situational / arsenal models are presented as direction, not prescription.

Browse the gallery:  
https://gdevers.github.io/pitch-dataset/reports/

Happy to walk through the Stuff model, grade mapping, or narrative rules.

#BaseballAnalytics #SportsAnalytics #MLB

---

## Pitch arsenal optimization

Hook: Is this pitcher actually using his pitches optimally?

**Arsenal optimization** compares current usage to a recommended mix and surfaces expected ΔxwOBA — so “throw the slider more” becomes a quantified opportunity, not a vibe. The published piece is a polished Dylan Cease case study with clear current-vs-recommended bars and top opportunities.

This sits upstream of situational calling: if the arsenal mix is off, count-level advice is fighting the wrong baseline. It’s also a clean interview artifact — one page that shows data → model → recommendation → visual.

Read the report:  
https://gdevers.github.io/pitch-dataset/arsenal.html

Happy to walk through the outcome model and how recommendations are constrained to a pitcher’s existing repertoire.

#BaseballAnalytics #MLB

---

## Trade-deadline pitcher analysis

Hook: After the deadline, what actually changed — usage, results, or both?

I published a **trade-deadline pitcher analysis** for recent movers (Skubal, Gausman, Soriano, Mize, Peralta): pre/post usage, outcomes, and pairing context, with sample-size honesty called out where post-trade windows are thin.

Teams need a fast, comparable view when a pitcher changes environments — not a week of ad-hoc queries. This report is that first pass: structured enough to brief a room, transparent enough to challenge.

Open the analysis:  
https://gdevers.github.io/pitch-dataset/traded-pitchers.html

Companion shape & pairing lab (arm angle, spin, extension, break, tunnels):  
https://gdevers.github.io/pitch-dataset/traded-shape.html

Happy to walk through how pre/post affiliation is derived from pitch data and where I’d extend it for a live ops workflow.

#BaseballAnalytics #MLB

---

## Trade-deadline shape & pairing lab (optional follow-up)

Hook: Usage tells you *what* changed after a trade. Shape and pairing tell you *how the stuff feels*.

The **shape & pairing lab** lets you switch among deadline movers and inspect arm angle, spin, extension, effective speed, break, and tunnel pairs — the physical story next to the usage/results report.

Same portfolio, separate link so you can share the visual lab without forcing someone through the full write-up.

https://gdevers.github.io/pitch-dataset/traded-shape.html

#BaseballAnalytics

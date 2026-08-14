# Example reports

Generated with:

```bash
uv run pitch-dataset train-model --league mlb --season 2026
uv run pitch-dataset optimize --pitcher Cease --report reports/example_cease.md
uv run pitch-dataset optimize --top 3 --report reports/example_top3.md
```

Training window: MLB 2026-03-25 → 2026-08-13 (season-to-date; n=491,230).

| File | Contents |
| --- | --- |
| `example_cease.md` | Dylan Cease recommendation write-up |
| `example_schlittler.md` | Cam Schlittler recommendation write-up |
| `example_top3.md` | Top-3 by pitch volume |
| `arsenal_optimization.html` | Static visual summary (Cease headline + top-3 ΔxwOBA) — open in a browser |

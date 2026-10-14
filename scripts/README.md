# Local automation (macOS)

Weekly refresh for situational pitch data plus the `train-select` (pitch type) and `train-location` (zone) models (MLB 2026 by default). It then regenerates `docs/pitch-to-field.html` (`pitch-dataset field --demo`) and `docs/zone-3d.html` (`pitch-dataset zone3d --demo`); those steps are non-fatal and do not commit or push.

`scripts/zone3d_shots.py` is a headless-Chrome smoke test for the 3D page: it saves screenshots to `logs/shots/` and exits non-zero on any console error (`--live http://127.0.0.1:8765/zone3d` to test the running server).

If a pull returns far fewer rows than the existing parquet (e.g. network outage), it refuses to overwrite the file and the script stops before retraining.

## Run manually

From the repo root:

```bash
./scripts/update-situational.sh
```

Logs append to `logs/update-situational.log`. Override league/season:

```bash
LEAGUE=mlb SEASON=2026 ./scripts/update-situational.sh
```

## Skip if already updated today

When launched by launchd (`XPC_SERVICE_NAME=com.grantdevers.pitch-dataset-update`), the script exits early if the log already has a `SUCCESS:` line dated today, logging `already updated today, skipping scheduled run`. Manual runs never skip. To force a scheduled-style run anyway, pass `--force` or set `FORCE=1`.

## Install launchd (Monday 4:00 PM local)

Copy the plist into your user LaunchAgents folder and load it:

```bash
cp scripts/com.grantdevers.pitch-dataset-update.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.grantdevers.pitch-dataset-update.plist
```

After editing the plist or script path, reload:

```bash
launchctl unload ~/Library/LaunchAgents/com.grantdevers.pitch-dataset-update.plist
launchctl load ~/Library/LaunchAgents/com.grantdevers.pitch-dataset-update.plist
```

Unload to disable:

```bash
launchctl unload ~/Library/LaunchAgents/com.grantdevers.pitch-dataset-update.plist
```

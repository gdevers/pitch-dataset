# Local automation (macOS)

Weekly refresh for situational pitch data and `train-select` model (MLB 2026 by default).

## Run manually

From the repo root:

```bash
./scripts/update-situational.sh
```

Logs append to `logs/update-situational.log`. Override league/season:

```bash
LEAGUE=mlb SEASON=2026 ./scripts/update-situational.sh
```

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

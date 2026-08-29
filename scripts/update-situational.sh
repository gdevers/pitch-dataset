#!/usr/bin/env bash
# Refresh MLB situational pitch data and retrain the selection model.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -x "${HOME}/.local/bin/uv" ]]; then
  UV="${HOME}/.local/bin/uv"
elif command -v uv >/dev/null 2>&1; then
  UV="$(command -v uv)"
else
  echo "error: uv not found (install uv or add ~/.local/bin to PATH)" >&2
  exit 1
fi

LEAGUE="${LEAGUE:-mlb}"
SEASON="${SEASON:-2026}"

mkdir -p logs
LOG="${ROOT}/logs/update-situational.log"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')" "$*" | tee -a "$LOG"
}

run_step() {
  local label=$1
  shift
  log "--- ${label} ---"
  if "$@" 2>&1 | tee -a "$LOG"; then
    return 0
  fi
  log "ERROR: ${label} failed (exit $?)"
  return 1
}

log "=== update-situational start (league=${LEAGUE} season=${SEASON}) ==="
log "project: ${ROOT}"
log "uv: ${UV}"

if ! run_step "pull-all" "$UV" run pitch-dataset pull-all --league "$LEAGUE" --season "$SEASON"; then
  log "Stopping: pull-all failed; train-select not run"
  exit 1
fi

if ! run_step "train-select" "$UV" run pitch-dataset train-select --league "$LEAGUE" --season "$SEASON"; then
  exit 1
fi

PITCH_FILE="${ROOT}/data/pitches_${LEAGUE}_${SEASON}.parquet"
if [[ -f "$PITCH_FILE" ]]; then
  if DATE_RANGE=$("$UV" run python -c "
import pandas as pd
from pathlib import Path
p = Path('${PITCH_FILE}')
df = pd.read_parquet(p, columns=['game_date'])
d = pd.to_datetime(df['game_date'])
print(f\"{d.min().date()} → {d.max().date()} ({len(df):,} pitches)\")
" 2>>"$LOG"); then
    log "SUCCESS: pitch data ${DATE_RANGE}"
  else
    log "SUCCESS: update complete (could not read date range)"
  fi
else
  log "SUCCESS: update complete (missing ${PITCH_FILE})"
fi

log "=== update-situational finished ==="

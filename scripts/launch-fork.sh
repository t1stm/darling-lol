#!/usr/bin/env bash
# ==============================================================================
# League of Legends (Darling) - Fork Launcher
# Boots up League of Legends using the user's custom fork (feat/pr41-followups)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
FORK_BRANCH="${FORK_BRANCH:-feat/pr41-followups}"
LOG_FILE="${LEAGUE_LOG:-/tmp/darling-lol-launch-fork.log}"
export DISPLAY="${DISPLAY:-:0}"
export RCLOL_FILTER_HOST_ENV="${RCLOL_FILTER_HOST_ENV:-1}"
export DARLING_METAL_GPU_NAME="${DARLING_METAL_GPU_NAME:-AMD Radeon Pro 5500M}"
export DARLING_METAL_MAC_GPU_NAME="${DARLING_METAL_MAC_GPU_NAME:-1}"
export DARLING_METAL_VRAM_MB="${DARLING_METAL_VRAM_MB:-4096}"

log() {
  local msg="$1"
  echo "== $(date '+%Y-%m-%d %H:%M:%S') $msg" >> "$LOG_FILE"
  if [[ -t 1 ]]; then
    echo "[$FORK_BRANCH] $msg"
  fi
}

show_help() {
  cat <<EOF
League of Legends - Darling Fork Launcher

Usage: $(basename "$0") [options] [-- run_args...]

Options:
  --gamescope     Launch the client inside an isolated gamescope session
  --dry-run       Validate configuration, branch, and runtime without starting the game
  -h, --help      Display this help message
EOF
  exit 0
}

# 1. Parse CLI arguments
USE_GAMESCOPE=0
DRY_RUN=0
PASSTHROUGH_ARGS=()

for arg in "$@"; do
  case "$arg" in
    --gamescope)
      USE_GAMESCOPE=1
      ;;
    --dry-run)
      DRY_RUN=1
      ;;
    -h|--help)
      show_help
      ;;
    *)
      PASSTHROUGH_ARGS+=("$arg")
      ;;
  esac
done

if [[ "${RCLOL_USE_GAMESCOPE:-0}" == "1" ]]; then
  USE_GAMESCOPE=1
fi

echo "========================================================" >> "$LOG_FILE"
echo "== $(date '+%Y-%m-%d %H:%M:%S') Starting League of Legends (Fork: $FORK_BRANCH)" >> "$LOG_FILE"
echo "========================================================" >> "$LOG_FILE"

cd "$REPO_DIR"

# 2. Verify and ensure fork branch
current_branch="$(git branch --show-current 2>/dev/null || true)"
if [[ "$DRY_RUN" != "1" && -n "$current_branch" && "$current_branch" != "$FORK_BRANCH" ]]; then
  # Allow other user-developed fork branches (e.g. fix/macos-identity-and-vanguard-telemetry)
  if [[ "$current_branch" == fix/macos-identity* || "$current_branch" == feat/* ]]; then
    log "Running on fork topic branch '$current_branch'"
  else
    log "Current branch is '$current_branch', attempting checkout of '$FORK_BRANCH'..."
    if git diff --quiet 2>/dev/null && git diff --cached --quiet 2>/dev/null; then
      git checkout "$FORK_BRANCH" >> "$LOG_FILE" 2>&1 || {
        log "Warning: Could not checkout $FORK_BRANCH; proceeding on '$current_branch'"
      }
    else
      log "Notice: Repository has uncommitted changes; staying on branch '$current_branch'"
    fi
  fi
fi

# Ensure runtime tools are generated for fork repo
python3 "$REPO_DIR/scripts/configure.py" >> "$LOG_FILE" 2>&1 || true

# 3. Dry-run handler
if [[ "$DRY_RUN" == "1" ]]; then
  mode="desktop"
  [[ "$USE_GAMESCOPE" == "1" ]] && mode="gamescope"
  echo "[DRY-RUN] Fork Launcher Validation"
  echo "[DRY-RUN] Repository: $REPO_DIR"
  echo "[DRY-RUN] Current Branch: $(git branch --show-current 2>/dev/null || echo 'detached')"
  echo "[DRY-RUN] Target Script: $REPO_DIR/scripts/run.sh"
  echo "[DRY-RUN] Execution Mode: $mode"
  echo "[DRY-RUN] Passthrough Args: ${PASSTHROUGH_ARGS[*]:-none}"
  exit 0
fi

# 4. Prevent disrupting an active match
LEAGUE_GAME_PATTERN='LeagueofLegends\.app/Contents/MacOS/LeagueofLegends( |$)'
if pgrep -i -f "$LEAGUE_GAME_PATTERN" >/dev/null 2>&1; then
  log "Active League match already running; focusing window."
  if command -v xdotool >/dev/null 2>&1; then
    win="$(xdotool search --onlyvisible --class 'LeagueofLegends' 2>/dev/null | head -n 1 || true)"
    [[ -n "$win" ]] && xdotool windowactivate "$win" 2>/dev/null || true
  fi
  exit 0
fi

# 5. Handle existing RiotClient / Darling state
if pgrep -f 'RiotClientServices' >/dev/null 2>&1; then
  if command -v xdotool >/dev/null 2>&1; then
    win="$(xdotool search --onlyvisible --class 'LeagueClientUx|Riot Client|RiotClientServices' 2>/dev/null | head -n 1 || true)"
    if [[ -n "$win" ]]; then
      log "Riot Client window already open ($win); activating."
      xdotool windowactivate "$win" 2>/dev/null || true
      exit 0
    fi
  fi
  log "RiotClientServices running without visible window; stopping Darling cleanly..."
  darling shutdown >> "$LOG_FILE" 2>&1 || true
  sleep 2
fi

# Clean up stale gamescopereaper if any
pkill -9 -x gamescopereaper 2>/dev/null || true

# 6. Launch in Gamescope or Desktop
if [[ "$USE_GAMESCOPE" == "1" ]] && command -v gamescope >/dev/null 2>&1; then
  GAMESCOPE_WIDTH="${GAMESCOPE_WIDTH:-3440}"
  GAMESCOPE_HEIGHT="${GAMESCOPE_HEIGHT:-1440}"
  GAMESCOPE_REFRESH="${GAMESCOPE_REFRESH:-180}"
  log "Launching via gamescope (${GAMESCOPE_WIDTH}x${GAMESCOPE_HEIGHT}@${GAMESCOPE_REFRESH}Hz)..."

  # Clean Darling server and stale launchd before gamescope launch
  if pgrep -f 'darlingserver|RiotClientServices' >/dev/null 2>&1; then
    darling shutdown >> "$LOG_FILE" 2>&1 || true
    sleep 2
  fi
  pkill -9 -x gamescopereaper 2>/dev/null || true
  if ! pgrep -x darlingserver >/dev/null 2>&1; then
    pkill -9 -f '^/sbin/launchd$' 2>/dev/null || true
  fi

  gamescope -W "$GAMESCOPE_WIDTH" -H "$GAMESCOPE_HEIGHT" \
    -w "$GAMESCOPE_WIDTH" -h "$GAMESCOPE_HEIGHT" -r "$GAMESCOPE_REFRESH" -f --adaptive-sync -g -- \
    "$REPO_DIR/scripts/run.sh" "${PASSTHROUGH_ARGS[@]}" >> "$LOG_FILE" 2>&1 &
  gs=$!

  # Watchdog: terminate gamescope and reaper once Riot Client / League exits
  (
    seen=0
    gone=0
    while kill -0 "$gs" 2>/dev/null; do
      if pgrep -f '/Riot Client\.app/|/League of Legends\.app/|RiotClientServices' >/dev/null 2>&1; then
        seen=1
        gone=0
      elif [[ "$seen" -eq 1 ]]; then
        gone=$((gone + 1))
        if [[ "$gone" -ge 10 ]]; then
          echo "== $(date '+%Y-%m-%d %H:%M:%S') Riot/League client exited; terminating gamescope..." >> "$LOG_FILE"
          pkill -9 -x gamescopereaper 2>/dev/null || true
          sleep 2
          kill -9 "$gs" 2>/dev/null || true
          break
        fi
      fi
      sleep 1
    done
  ) &
  wait "$gs" 2>/dev/null || true

  # Clean teardown of Darling after gamescope exit
  log "Gamescope session ended; shutting down Darling..."
  darling shutdown >> "$LOG_FILE" 2>&1 || true
  pkill -9 -x gamescopereaper 2>/dev/null || true
  exit 0
else
  # Background focus watcher on desktop mode
  if [[ -z "${GAMESCOPE_WAYLAND_DISPLAY:-}" ]] && command -v xdotool >/dev/null 2>&1; then
    (
      main_pid=$$
      i=0
      while [ $i -lt 60 ] && kill -0 "$main_pid" 2>/dev/null && ! pgrep -f '/Riot Client\.app/|/League of Legends\.app/|RiotClientServices' >/dev/null 2>&1; do
        sleep 1
        i=$((i+1))
      done
      last_win=""
      while kill -0 "$main_pid" 2>/dev/null && pgrep -f '/Riot Client\.app/|/League of Legends\.app/|RiotClientServices' >/dev/null 2>&1; do
        win="$(xdotool search --onlyvisible --class '^LeagueofLegends$' 2>/dev/null | head -n 1 || true)"
        # X reuses window IDs across game matches; forget window ID once it is gone
        [[ -z "$win" ]] && last_win=""
        if [[ -n "$win" && "$win" != "$last_win" ]]; then
          sleep 1
          xdotool windowactivate "$win" 2>/dev/null || true
          sleep 4
          xdotool windowactivate "$win" 2>/dev/null || true
          echo "== $(date '+%Y-%m-%d %H:%M:%S') activated game window $win" >> "$LOG_FILE"
          last_win="$win"
        fi
        sleep 2
      done
    ) &
  fi

  log "Executing fork run.sh..."
  exec "$REPO_DIR/scripts/run.sh" "${PASSTHROUGH_ARGS[@]}" >> "$LOG_FILE" 2>&1
fi

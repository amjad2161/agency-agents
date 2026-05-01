#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# JARVIS Watchdog — keeps the local stack alive 24/7
# ═══════════════════════════════════════════════════════════════════════════
# Install as a cron job (runs every 5 minutes):
#   crontab -e
#   */5 * * * * /path/to/agency-agents/scripts/watchdog.sh >> /var/log/jarvis-watchdog.log 2>&1
#
# Environment variables:
#   JARVIS_URL              Base URL of the local JARVIS instance (default: http://localhost:8765)
#   JARVIS_HEALTH_PATH      Health endpoint path (default: /api/health)
#                           Set to /api/version if AGENCY_DISABLE_HEALTH=1 on the server.
#                           When set to anything other than /api/health, any 2xx response
#                           is treated as healthy (no JSON status check).
#   JARVIS_WATCHDOG_PROFILES  Comma-separated Docker Compose profiles to activate on restart
#                             e.g. "sync,monitor"  (default: empty — base services only)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="${REPO_ROOT}/docker-compose.yml"
JARVIS_URL="${JARVIS_URL:-http://localhost:8765}"
JARVIS_HEALTH_PATH="${JARVIS_HEALTH_PATH:-/api/health}"
JARVIS_WATCHDOG_PROFILES="${JARVIS_WATCHDOG_PROFILES:-}"

log() {
  local ts
  ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo "[${ts}] JARVIS-WATCHDOG $*"
}

# Build --profile flags for compose commands
_profile_flags() {
  local flags=""
  if [ -n "$JARVIS_WATCHDOG_PROFILES" ]; then
    IFS=',' read -ra PROFS <<< "$JARVIS_WATCHDOG_PROFILES"
    for p in "${PROFS[@]}"; do
      flags="$flags --profile $p"
    done
  fi
  echo "$flags"
}

check_health() {
  local url="${JARVIS_URL}${JARVIS_HEALTH_PATH}"
  if [ "$JARVIS_HEALTH_PATH" = "/api/health" ]; then
    # Parse JSON and check status field
    local status
    status=$(curl -sf --max-time 5 "$url" \
      | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('status','down'))" 2>/dev/null \
      || echo "down")
    echo "$status"
  else
    # For other endpoints (e.g. /api/version), any 2xx is healthy
    if curl -sf --max-time 5 "$url" > /dev/null 2>&1; then
      echo "ok"
    else
      echo "down"
    fi
  fi
}

restart_stack() {
  local profile_flags
  profile_flags="$(_profile_flags)"
  log "Stopping JARVIS containers..."
  cd "$REPO_ROOT"
  # stop first so wedged/unhealthy containers are actually killed
  # shellcheck disable=SC2086
  docker compose -f "$COMPOSE_FILE" $profile_flags stop || true
  log "Starting JARVIS stack..."
  # shellcheck disable=SC2086
  docker compose -f "$COMPOSE_FILE" $profile_flags up -d
  log "Restart complete."
}

pull_latest() {
  local profile_flags
  profile_flags="$(_profile_flags)"
  log "Pulling latest images..."
  cd "$REPO_ROOT"
  # shellcheck disable=SC2086
  docker compose -f "$COMPOSE_FILE" $profile_flags pull --quiet
}

# ── Main ────────────────────────────────────────────────────────────────────
log "Health check → ${JARVIS_URL}${JARVIS_HEALTH_PATH}"
STATUS=$(check_health)
log "Status: ${STATUS}"

if [ "$STATUS" != "ok" ]; then
  log "JARVIS is DOWN (status=${STATUS}) — attempting recovery"

  pull_latest || log "Pull failed (continuing anyway)"
  restart_stack

  # Wait up to 60s for JARVIS to come back
  for i in $(seq 1 12); do
    sleep 5
    STATUS=$(check_health)
    log "Post-restart check ${i}/12 — status=${STATUS}"
    if [ "$STATUS" = "ok" ]; then
      log "✅ JARVIS recovered successfully"
      exit 0
    fi
  done

  log "❌ JARVIS failed to recover after 60s"
  exit 1
else
  log "✅ JARVIS is healthy"
fi

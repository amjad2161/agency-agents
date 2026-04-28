#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# JARVIS Watchdog — keeps the local stack alive 24/7
# ═══════════════════════════════════════════════════════════════════════════
# Install as a cron job (runs every 5 minutes):
#   crontab -e
#   */5 * * * * /path/to/agency-agents/scripts/watchdog.sh >> /var/log/jarvis-watchdog.log 2>&1
#
# Or as a systemd service — see docs/CLOUD_SETUP.md

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="${REPO_ROOT}/docker-compose.yml"
JARVIS_URL="${JARVIS_URL:-http://localhost:8765}"
LOG_PREFIX="[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] JARVIS-WATCHDOG"

log() { echo "${LOG_PREFIX} $*"; }

check_health() {
  local status
  status=$(curl -sf --max-time 5 "${JARVIS_URL}/healthz" \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','down'))" 2>/dev/null || echo "down")
  echo "$status"
}

restart_stack() {
  log "Restarting JARVIS stack..."
  cd "$REPO_ROOT"
  docker compose -f "$COMPOSE_FILE" up -d --remove-orphans
  log "Restart triggered."
}

pull_latest() {
  log "Pulling latest images..."
  cd "$REPO_ROOT"
  docker compose -f "$COMPOSE_FILE" pull --quiet
}

# ── Main ────────────────────────────────────────────────────────────────────
log "Health check → ${JARVIS_URL}/healthz"
STATUS=$(check_health)
log "Status: ${STATUS}"

if [ "$STATUS" != "ok" ]; then
  log "JARVIS is DOWN (status=${STATUS}) — attempting recovery"

  # Try pulling latest first (maybe a fresh image fixes it)
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

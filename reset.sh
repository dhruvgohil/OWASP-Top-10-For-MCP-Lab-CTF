#!/usr/bin/env bash
# Orchestrate BOTH stacks in this directory:
#   - combined-chain-lab   (the vulnerable HelixChain kill-chain lab)   -> http://localhost:3100
#   - scoreboard-dashboard (the hardened CTF scoreboard companion)      -> http://localhost:3200
#
# Usage:
#   ./reset.sh up      # build (if needed) + start both stacks           [default]
#   ./reset.sh reset   # wipe containers + volumes, rebuild, start fresh
#   ./reset.sh down    # stop + remove containers (KEEPS data volumes)
#   ./reset.sh logs    # tail logs from both stacks
#   ./reset.sh status  # show container status for both stacks
#
# `reset` gives a fully clean slate: it removes the lab's per-player tenant data AND the
# scoreboard's registered users / scores. Use `up` for day-to-day start with data intact.
set -euo pipefail

cd "$(dirname "$0")"
ROOT="$(pwd)"

LAB_DIR="$ROOT/combined-chain-lab"
SB_DIR="$ROOT/scoreboard-dashboard"

# Endpoints used for health checks.
LAB_HEALTH="http://localhost:8100/api/health"   # lab backend
LAB_URL="http://localhost:3100"
SB_HEALTH="http://localhost:3200/api/health"     # scoreboard, via nginx proxy
SB_URL="http://localhost:3200"

# Pretty output ------------------------------------------------------------
c_reset=$'\033[0m'; c_ok=$'\033[32m'; c_info=$'\033[36m'; c_warn=$'\033[33m'; c_err=$'\033[31m'
info() { echo "${c_info}[*]${c_reset} $*"; }
ok()   { echo "${c_ok}[+]${c_reset} $*"; }
warn() { echo "${c_warn}[!]${c_reset} $*" >&2; }
die()  { echo "${c_err}[x]${c_reset} $*" >&2; exit 1; }

# Pre-flight ---------------------------------------------------------------
command -v docker >/dev/null 2>&1 || die "docker is not installed / not on PATH."
docker compose version >/dev/null 2>&1 || die "'docker compose' (v2) is required."
docker info >/dev/null 2>&1 || die "Docker daemon is not running. Start Docker and retry."
[ -f "$LAB_DIR/docker-compose.yml" ] || die "Missing $LAB_DIR/docker-compose.yml"
[ -f "$SB_DIR/docker-compose.yml" ]  || die "Missing $SB_DIR/docker-compose.yml"

# Run `docker compose` inside a stack directory (so its .env / relative paths resolve).
dc() { local dir="$1"; shift; (cd "$dir" && docker compose "$@"); }

# Wait until a URL answers, up to ~60s.
wait_for() {
  local name="$1" url="$2"
  info "Waiting for $name at $url …"
  for _ in $(seq 1 30); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      ok "$name is up."
      return 0
    fi
    sleep 2
  done
  warn "$name did not become healthy in time (check: ./reset.sh logs)."
  return 1
}

# Actions ------------------------------------------------------------------
do_up() {
  info "Building + starting combined-chain-lab …"
  dc "$LAB_DIR" up --build -d
  info "Building + starting scoreboard-dashboard …"
  dc "$SB_DIR" up --build -d

  echo
  local rc=0
  wait_for "combined-chain-lab backend" "$LAB_HEALTH" || rc=1
  wait_for "scoreboard-dashboard"        "$SB_HEALTH"  || rc=1

  echo
  ok "Lab:        $LAB_URL"
  ok "Scoreboard: $SB_URL"
  return $rc
}

do_down() {
  info "Stopping scoreboard-dashboard (keeping volumes) …"
  dc "$SB_DIR" down --remove-orphans
  info "Stopping combined-chain-lab (keeping volumes) …"
  dc "$LAB_DIR" down --remove-orphans
  ok "Both stacks stopped. Data volumes preserved."
}

do_reset() {
  warn "FULL RESET: this wipes lab tenant data AND all scoreboard users/scores."
  info "Tearing down scoreboard-dashboard (containers + volumes) …"
  dc "$SB_DIR" down -v --remove-orphans
  info "Tearing down combined-chain-lab (containers + volumes) …"
  dc "$LAB_DIR" down -v --remove-orphans
  echo
  do_up
}

do_logs() {
  info "Tailing logs (Ctrl-C to stop). Lab first, then scoreboard…"
  # Separate invocations so both directories' compose projects are covered.
  ( cd "$LAB_DIR" && docker compose logs -f --tail=20 ) &
  local lab_pid=$!
  ( cd "$SB_DIR"  && docker compose logs -f --tail=20 ) &
  local sb_pid=$!
  trap 'kill "$lab_pid" "$sb_pid" 2>/dev/null || true' INT TERM
  wait
}

do_status() {
  echo "== combined-chain-lab =="
  dc "$LAB_DIR" ps
  echo
  echo "== scoreboard-dashboard =="
  dc "$SB_DIR" ps
}

# Dispatch -----------------------------------------------------------------
case "${1:-up}" in
  up|start)   do_up ;;
  reset)      do_reset ;;
  down|stop)  do_down ;;
  logs)       do_logs ;;
  status|ps)  do_status ;;
  -h|--help|help)
    grep -E '^#( |$)' "$0" | sed -E 's/^# ?//'
    ;;
  *) die "Unknown command '$1'. Try: up | reset | down | logs | status | help" ;;
esac

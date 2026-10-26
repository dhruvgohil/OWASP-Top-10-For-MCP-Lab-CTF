#!/usr/bin/env bash
# Thin wrapper around `python -m app.manage` inside the backend container.
#
# The scoreboard DB lives on the named volume `scoreboard-data`, which survives
# `docker compose down` and any rebuild. Use this to remove specific rows
# instead of `docker compose down -v`, which nukes every player at once.
#
#   ./scoreboard-admin.sh list
#   ./scoreboard-admin.sh delete marcus
#   ./scoreboard-admin.sh delete 3 alice@example.com --yes
#   ./scoreboard-admin.sh reset-captures marcus
#   ./scoreboard-admin.sh logout marcus
#   ./scoreboard-admin.sh backup ./scoreboard-$(date +%F).db
#   ./scoreboard-admin.sh restore ./scoreboard-2026-08-01.db
set -euo pipefail

cd "$(dirname "$0")"

run_in_backend() {
  if docker compose ps --status running --services 2>/dev/null | grep -qx backend; then
    docker compose exec -T backend python -m app.manage "$@"
  else
    docker compose run --rm --no-deps -T backend python -m app.manage "$@"
  fi
}

# backup/restore name a file on the HOST, but the CLI runs in the container, so
# stage through a path inside the container and copy across.
case "${1:-}" in
  backup)
    [ $# -eq 2 ] || { echo "usage: $0 backup <host-file>" >&2; exit 2; }
    run_in_backend backup /tmp/scoreboard-snapshot.db
    docker compose cp backend:/tmp/scoreboard-snapshot.db "$2"
    docker compose exec -T backend rm -f /tmp/scoreboard-snapshot.db
    echo "Saved to $2"
    exit 0
    ;;
  restore)
    [ $# -ge 2 ] || { echo "usage: $0 restore <host-file> [--yes]" >&2; exit 2; }
    [ -f "$2" ] || { echo "no such file: $2" >&2; exit 1; }
    docker compose cp "$2" backend:/tmp/scoreboard-restore.db
    shift 2
    run_in_backend restore /tmp/scoreboard-restore.db "$@"
    docker compose exec -T backend rm -f /tmp/scoreboard-restore.db
    exit 0
    ;;
esac

if docker compose ps --status running --services 2>/dev/null | grep -qx backend; then
  # Container is up: exec into it so the running app sees the change at once.
  exec docker compose exec backend python -m app.manage "$@"
else
  # Stack is down: a throwaway container mounts the same volume.
  echo "backend not running — using a temporary container on the same volume" >&2
  exec docker compose run --rm --no-deps backend python -m app.manage "$@"
fi

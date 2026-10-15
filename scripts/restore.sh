#!/usr/bin/env bash
# Restore a backup made by scripts/backup.sh. DESTRUCTIVE: replaces the database contents and
# the stored files of the target environment.
#
#   scripts/restore.sh [--compose] BACKUP_DIR [--yes]
#
# Verifies MANIFEST.sha256 first and refuses to continue if any file is missing or altered.
# The database roles (bdna_owner, bdna_app, bdna_system) must already exist — a fresh Compose
# stack creates them; elsewhere run deploy/postgres/init-roles.sh once.
set -euo pipefail
cd "$(dirname "$0")/.."

MODE=native
if [ "${1:-}" = "--compose" ]; then MODE=compose; shift; fi
SRC="${1:?usage: scripts/restore.sh [--compose] BACKUP_DIR [--yes]}"
SRC="$(cd "$SRC" && pwd)"
YES="${2:-}"
[ -f "$SRC/database.dump" ] || { echo "no database.dump in $SRC" >&2; exit 1; }

echo "verifying checksums…"
( cd "$SRC" && sha256sum --quiet -c MANIFEST.sha256 ) || { echo "checksum verification FAILED — not restoring" >&2; exit 1; }

if [ "$YES" != "--yes" ]; then
  read -r -p "This replaces ALL platform data in the target environment ($MODE). Type 'restore' to continue: " ok
  [ "$ok" = "restore" ] || { echo "aborted"; exit 1; }
fi

if [ "$MODE" = compose ]; then
  set -a; [ -f .env ] && . ./.env; set +a
  DB="${BDNA_DB_NAME:-bdna}"
  docker compose stop api worker mcp web >/dev/null 2>&1 || true
  docker compose exec -T postgres pg_restore -U postgres -d "$DB" --clean --if-exists --single-transaction --exit-on-error < "$SRC/database.dump"
  if [ -d "$SRC/storage" ]; then
    if [ "${BDNA_STORAGE_BACKEND:-s3}" = "local" ]; then
      docker compose run --rm -T -v "$SRC:/backup:ro" --entrypoint sh api -c "rm -rf /app/var/storage/* && cp -a /backup/storage/. /app/var/storage/"
    else
      BUCKET="${BDNA_S3_BUCKET:-bdna-assets}"
      docker compose run --rm -T -v "$SRC:/backup:ro" --entrypoint sh minio-init -c \
        "mc alias set local http://minio:9000 \"\$MINIO_ROOT_USER\" \"\$MINIO_ROOT_PASSWORD\" >/dev/null && mc mirror --overwrite --remove --quiet /backup/storage local/$BUCKET"
    fi
  fi
  docker compose run --rm migrate
  docker compose up -d api worker mcp web
else
  : "${BDNA_DATABASE_OWNER_URL:?set BDNA_DATABASE_OWNER_URL (or run with --compose)}"
  PGURL="${BDNA_DATABASE_OWNER_URL/postgresql+psycopg:/postgresql:}"
  # Extensions (vector, pg_trgm) belong to the superuser and already exist (init-roles.sh); the
  # owner role restores everything else.
  TOC="$(mktemp)"; trap 'rm -f "$TOC"' EXIT
  pg_restore -l "$SRC/database.dump" | grep -v -E ' (EXTENSION|COMMENT - EXTENSION) ' > "$TOC"
  pg_restore -d "$PGURL" -L "$TOC" --clean --if-exists --single-transaction --exit-on-error "$SRC/database.dump"
  if [ -d "$SRC/storage" ] && [ "${BDNA_STORAGE_BACKEND:-local}" = "local" ]; then
    ROOT="${BDNA_STORAGE_LOCAL_ROOT:-backend/var/storage}"
    [ -d "$(dirname "$ROOT")" ] || ROOT="backend/${ROOT#./}"
    rm -rf "$ROOT" && mkdir -p "$ROOT" && cp -a "$SRC/storage/." "$ROOT/"
  elif [ -d "$SRC/storage" ] && command -v aws >/dev/null 2>&1; then
    aws s3 sync "$SRC/storage" "s3://${BDNA_S3_BUCKET}" --delete ${BDNA_S3_ENDPOINT_URL:+--endpoint-url "$BDNA_S3_ENDPOINT_URL"} --only-show-errors
  fi
  (cd backend && ${PYTHON:-.venv/bin/python} -m app.cli migrate && ${PYTHON:-.venv/bin/python} -m app.cli check)
fi
echo "restore complete"

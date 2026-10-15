#!/usr/bin/env bash
# Back up the database and all stored files into one timestamped directory with a checksum
# manifest, so a backup can be verified independently (sha256sum -c MANIFEST.sha256).
#
#   scripts/backup.sh [--compose] [OUTPUT_DIR]
#
#   --compose   run pg_dump / MinIO mirroring inside the Docker Compose stack (default when the
#               `postgres` service is running); otherwise uses local tools and the BDNA_* settings
#               from the environment (pg_dump, and either the local storage root or `aws s3 sync`).
#
# The database dump is pg_dump's custom format taken as the schema owner, so it contains the
# Row Level Security policies, grants and triggers along with the data.
set -euo pipefail
cd "$(dirname "$0")/.."

MODE=native
if [ "${1:-}" = "--compose" ]; then MODE=compose; shift; fi
if [ "$MODE" = native ] && command -v docker >/dev/null 2>&1 && docker compose ps --status running --services 2>/dev/null | grep -qx postgres; then
  MODE=compose
fi
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${1:-./backups}/bdna-$STAMP"
mkdir -p "$OUT"
OUT="$(cd "$OUT" && pwd)"
echo "backup → $OUT ($MODE)"

if [ "$MODE" = compose ]; then
  set -a; [ -f .env ] && . ./.env; set +a
  DB="${BDNA_DB_NAME:-bdna}"
  docker compose exec -T postgres pg_dump -U postgres -d "$DB" -Fc > "$OUT/database.dump"
  if [ "${BDNA_STORAGE_BACKEND:-local}" = "s3" ] && [ -z "${BDNA_S3_ENDPOINT_URL:-}" ]; then
    BUCKET="${BDNA_S3_BUCKET:-bdna-assets}"
    docker compose run --rm -T -v "$OUT:/backup" --entrypoint sh minio-init -c \
      "mc alias set local http://minio:9000 \"\$MINIO_ROOT_USER\" \"\$MINIO_ROOT_PASSWORD\" >/dev/null && mc mirror --quiet local/$BUCKET /backup/storage"
  elif [ "${BDNA_STORAGE_BACKEND:-local}" = "local" ]; then
    docker compose run --rm -T -v "$OUT:/backup" --entrypoint sh api -c "cp -a /app/var/storage /backup/storage"
  else
    echo "external object storage (${BDNA_S3_ENDPOINT_URL}) — back it up with the provider's tools (e.g. R2/S3 bucket versioning or rclone)." | tee "$OUT/STORAGE-NOT-INCLUDED.txt"
  fi
else
  : "${BDNA_DATABASE_OWNER_URL:?set BDNA_DATABASE_OWNER_URL (or run with --compose)}"
  PGURL="${BDNA_DATABASE_OWNER_URL/postgresql+psycopg:/postgresql:}"
  pg_dump "$PGURL" -Fc > "$OUT/database.dump"
  if [ "${BDNA_STORAGE_BACKEND:-local}" = "local" ]; then
    ROOT="${BDNA_STORAGE_LOCAL_ROOT:-backend/var/storage}"
    [ -d "$ROOT" ] || ROOT="backend/${ROOT#./}"
    mkdir -p "$OUT/storage" && cp -a "$ROOT/." "$OUT/storage/"
  elif command -v aws >/dev/null 2>&1; then
    aws s3 sync "s3://${BDNA_S3_BUCKET}" "$OUT/storage" ${BDNA_S3_ENDPOINT_URL:+--endpoint-url "$BDNA_S3_ENDPOINT_URL"} --only-show-errors
  else
    echo "aws CLI not found — object storage not included" | tee "$OUT/STORAGE-NOT-INCLUDED.txt"
  fi
fi

( cd "$OUT" && find . -type f ! -name MANIFEST.sha256 -print0 | sort -z | xargs -0 sha256sum > MANIFEST.sha256 )
cat > "$OUT/BACKUP-INFO.txt" <<INFO
created_utc=$STAMP
mode=$MODE
files=$(($(wc -l < "$OUT/MANIFEST.sha256")))
verify: cd $(basename "$OUT") && sha256sum -c MANIFEST.sha256
restore: scripts/restore.sh $OUT
INFO
echo "done: $(du -sh "$OUT" | cut -f1), $(wc -l < "$OUT/MANIFEST.sha256") files, manifest MANIFEST.sha256"

#!/usr/bin/env bash
# DEVELOPMENT ONLY — wipe the local database and file storage, re-apply migrations and load the
# three fictional demo customers. Never point this at a production database.
#
#   scripts/reset-dev.sh            (uses backend/.env or the defaults in backend/app/config.py)
set -euo pipefail
cd "$(dirname "$0")/../backend"
PY="${PYTHON:-.venv/bin/python}"
if [ "${BDNA_ENVIRONMENT:-development}" = "production" ]; then
  echo "refusing to reset a production environment" >&2
  exit 1
fi
"$PY" - <<'PY'
from sqlalchemy import create_engine, text
from app.config import get_settings
s = get_settings()
if s.is_production:
    raise SystemExit("refusing to reset a production environment")
with create_engine(s.database_owner_url).begin() as c:
    c.execute(text("DROP OWNED BY CURRENT_USER CASCADE"))
print("schema dropped")
PY
rm -rf "${BDNA_STORAGE_LOCAL_ROOT:-./var/storage}"
"$PY" -m app.cli migrate
"$PY" -m app.cli seed-demo --admin-email "${BDNA_ADMIN_EMAIL:-admin@platform.local}" --admin-password "${BDNA_ADMIN_PASSWORD:-admin-password-2026}"

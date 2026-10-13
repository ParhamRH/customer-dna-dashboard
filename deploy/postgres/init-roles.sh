#!/usr/bin/env bash
# Bootstrap the three database roles, the database and required extensions.
# Run once as a PostgreSQL superuser (docker-entrypoint-initdb.d runs it automatically).
#
#   BDNA_DB_NAME            database name                (default: bdna)
#   BDNA_DB_OWNER_PASSWORD  migration/owner role password
#   BDNA_DB_APP_PASSWORD    runtime role (RLS enforced)
#   BDNA_DB_SYSTEM_PASSWORD privileged platform role (BYPASSRLS)
set -euo pipefail
DB="${BDNA_DB_NAME:-bdna}"
OWNER_PW="${BDNA_DB_OWNER_PASSWORD:?set BDNA_DB_OWNER_PASSWORD}"
APP_PW="${BDNA_DB_APP_PASSWORD:?set BDNA_DB_APP_PASSWORD}"
SYS_PW="${BDNA_DB_SYSTEM_PASSWORD:?set BDNA_DB_SYSTEM_PASSWORD}"
PSQL=(psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER:-postgres}" --no-password)

"${PSQL[@]}" --dbname postgres <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bdna_owner') THEN
    CREATE ROLE bdna_owner LOGIN BYPASSRLS PASSWORD '${OWNER_PW}';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bdna_app') THEN
    CREATE ROLE bdna_app LOGIN NOBYPASSRLS NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD '${APP_PW}';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bdna_system') THEN
    CREATE ROLE bdna_system LOGIN BYPASSRLS NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD '${SYS_PW}';
  END IF;
END
\$\$;
SQL

if ! "${PSQL[@]}" --dbname postgres -tAc "SELECT 1 FROM pg_database WHERE datname='${DB}'" | grep -q 1; then
  "${PSQL[@]}" --dbname postgres -c "CREATE DATABASE \"${DB}\" OWNER bdna_owner"
fi

"${PSQL[@]}" --dbname "${DB}" <<SQL
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
REVOKE ALL ON DATABASE "${DB}" FROM PUBLIC;
GRANT CONNECT ON DATABASE "${DB}" TO bdna_app, bdna_system;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO bdna_app, bdna_system;
GRANT ALL ON SCHEMA public TO bdna_owner;
SQL
echo "bdna roles and database '${DB}' ready"

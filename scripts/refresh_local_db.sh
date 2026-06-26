#!/usr/bin/env bash
# refresh_local_db.sh
#
# Pulls a subset of prod data from Railway into the local dev DB.
# Run ad hoc: bash scripts/refresh_local_db.sh
#
# Requires in .env.local (repo root):
#   PROD_READONLY_URL   — Railway read-only connection string
#   DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD — local DB vars
#
# Subset windows:
#   retailers       — all rows
#   products        — all rows
#   price_history   — last 90 days (scraped_at)
#   price_drops     — last 90 days (new_scraped_at)
#   scrape_runs     — last 30 days (started_at)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$REPO_ROOT/.env.local"

# ---------------------------------------------------------------------------
# Load env
# ---------------------------------------------------------------------------
if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE not found." >&2
  exit 1
fi

# Source only assignment lines — skip comments and blank lines
set -a
# shellcheck disable=SC1090
source <(grep -E '^[A-Z_]+=.' "$ENV_FILE" | grep -v '^#')
set +a

# ---------------------------------------------------------------------------
# Validate required vars
# ---------------------------------------------------------------------------
missing=()
for var in PROD_READONLY_URL DB_HOST DB_PORT DB_NAME DB_USER DB_PASSWORD; do
  [[ -z "${!var:-}" ]] && missing+=("$var")
done

if [[ ${#missing[@]} -gt 0 ]]; then
  echo "ERROR: Missing required variables in $ENV_FILE: ${missing[*]}" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Safety guard: prod URL must point at Railway, local host must be localhost
# ---------------------------------------------------------------------------
if [[ "$PROD_READONLY_URL" != *railway* ]]; then
  echo "ERROR: PROD_READONLY_URL does not look like a Railway URL (missing 'railway')." >&2
  echo "       Refusing to run to avoid operating on the wrong database." >&2
  exit 1
fi

if [[ "$DB_HOST" != "localhost" && "$DB_HOST" != "127.0.0.1" ]]; then
  echo "ERROR: DB_HOST='$DB_HOST' does not look like a local host." >&2
  echo "       Refusing to run to avoid truncating a non-local database." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# psql helpers
# ---------------------------------------------------------------------------
# Prod: read-only via URL (Railway)
prod_psql() {
  psql "$PROD_READONLY_URL" --no-password "$@"
}

# Local: individual flags + PGPASSWORD to avoid URL-encoding special chars
local_psql() {
  PGPASSWORD="$DB_PASSWORD" psql \
    -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
    --no-password "$@"
}

# ---------------------------------------------------------------------------
# Step 1: Apply schema + migrations to local DB
# ---------------------------------------------------------------------------
echo "==> Applying schema to local DB..."
local_psql -f "$REPO_ROOT/sql/schema.sql" -q

echo "==> Applying migrations to local DB..."
for migration in "$REPO_ROOT"/sql/migrations/[0-9]*.sql; do
  echo "    $(basename "$migration")"
  local_psql -f "$migration" -q
done

# ---------------------------------------------------------------------------
# Step 2: Truncate local tables (reverse FK order)
# ---------------------------------------------------------------------------
echo "==> Truncating local tables..."
local_psql -c "TRUNCATE TABLE scrape_runs, price_drops, price_history, products, retailers RESTART IDENTITY CASCADE;"

# ---------------------------------------------------------------------------
# Step 3: Stream prod → local (no temp files)
# ---------------------------------------------------------------------------
stream() {
  local table="$1"
  local select="$2"
  echo "==> Copying $table..."
  prod_psql -c "\COPY ($select) TO STDOUT" \
    | local_psql -c "\COPY $table FROM STDIN"
}

stream "retailers" \
  "SELECT * FROM retailers ORDER BY id"

stream "products" \
  "SELECT * FROM products ORDER BY id"

stream "price_history" \
  "SELECT * FROM price_history WHERE scraped_at >= NOW() - INTERVAL '90 days' ORDER BY id"

stream "price_drops" \
  "SELECT * FROM price_drops WHERE new_scraped_at >= NOW() - INTERVAL '90 days' ORDER BY id"

stream "scrape_runs" \
  "SELECT * FROM scrape_runs WHERE started_at >= NOW() - INTERVAL '30 days' ORDER BY id"

echo ""
echo "Done. Local DB '$DB_NAME' refreshed from prod."

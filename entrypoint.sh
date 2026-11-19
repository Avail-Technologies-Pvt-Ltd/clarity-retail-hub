#!/bin/bash
# ============================================================
# entrypoint.sh — Clarity Retail Hub
# Automated database readiness, multi-tenant migrations,
# public/demo tenant seeding, static assets, and dynamic workers.
# ============================================================

set -e

echo "========================================"
echo "  Clarity Retail Hub - Starting"
echo "========================================"

mkdir -p /app/logs /app/media /app/staticfiles /app/tmp /app/data

# 1. Wait for PostgreSQL database readiness
DB_TARGET_HOST="${DB_HOST:-db}"
DB_TARGET_PORT="${DB_PORT:-5432}"

echo "Waiting for database at $DB_TARGET_HOST:$DB_TARGET_PORT..."
MAX_RETRIES=60
RETRY_COUNT=0
while ! nc -z "$DB_TARGET_HOST" "$DB_TARGET_PORT"; do
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ "$RETRY_COUNT" -ge "$MAX_RETRIES" ]; then
        echo "[ERROR] Database timed out after $MAX_RETRIES seconds."
        exit 1
    fi
    sleep 1
done
echo "[OK] PostgreSQL database is ready!"

# 2. Run multi-tenant schema migrations
echo "Running database schema migrations..."
python manage.py migrate_schemas --noinput
echo "[OK] Schema migrations completed!"

# 3. Ensure public and demo tenants exist
echo "Initializing public and demo tenants..."
python manage.py create_public_tenant --create-demo || true
echo "[OK] Tenant initialization complete!"

# 4. Smart static files collection (fast startup if image has not changed)
CURRENT_HASH="${APP_BUILD_HASH:-$(stat -c %Y /app/manage.py 2>/dev/null || echo "unknown")}"
MARKER_FILE="/app/staticfiles/.image_hash"

if [ ! -f "$MARKER_FILE" ] || [ "$(cat "$MARKER_FILE" 2>/dev/null)" != "$CURRENT_HASH" ]; then
    if [ "$DEBUG" = "True" ] || [ "$DEBUG" = "true" ] || [ "$DEBUG" = "1" ]; then
        echo "Dev mode: skipping static file collection"
    else
        echo "Collecting static files (Image hash: $CURRENT_HASH)..."
        python manage.py collectstatic --noinput --no-post-process
        echo "$CURRENT_HASH" > "$MARKER_FILE"
        echo "[OK] Static files collected!"
    fi
else
    echo "[OK] Static files already up to date with image version."
fi

echo ""
echo "  Clarity Retail Hub is ready!"
echo "========================================"

# 5. Dynamic Gunicorn workers calculation (2 * cores + 1, capped at 4, or GUNICORN_WORKERS env)
if [ "${GUNICORN_WORKERS:-0}" -gt 0 ] 2>/dev/null; then
    WORKERS="$GUNICORN_WORKERS"
else
    WORKERS=$(python -c "import os; print(min((os.cpu_count() or 1) * 2 + 1, 4))")
fi

if [ "$1" = "gunicorn" ]; then
    echo "[INFO] Starting Gunicorn with $WORKERS workers on port 8000..."
    exec "$@" --workers "$WORKERS"
else
    exec "$@"
fi

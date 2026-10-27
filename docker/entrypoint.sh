#!/bin/sh
set -e

echo "Applying database migrations..."
python -m alembic upgrade head

echo "Starting CraftFlow backend server..."
exec "$@"

#!/bin/sh
# Applies migrations then starts the API — real Postgres, no mocks.
set -e

alembic upgrade head
exec uvicorn gamebook_web.api.app:app --host 0.0.0.0 --port 8000

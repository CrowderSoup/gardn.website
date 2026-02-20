#!/bin/sh
set -eu

uv run manage.py migrate --noinput
uv run manage.py collectstatic --noinput

exec "$@"

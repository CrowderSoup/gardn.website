#!/bin/sh
set -eu

uv run manage.py migrate --noinput

exec "$@"

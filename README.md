# Gardn

IndieWeb plant-based blogroll with IndieAuth login, deterministic plant SVGs, pick/unpick via HTMX, and embeddable widgets.

## Quick start (uv)

1. `cp .env.example .env`
2. `uv sync --group dev`
3. `uv run manage.py migrate`
4. `uv run manage.py runserver`

## Docker

- Prod-ish: `docker compose up --build`
- Dev HTTPS (Caddy): `docker compose -f docker-compose.dev.yml up --build`
- Both compose files force `DATABASE_URL` to Postgres (`db` service) so data persists in the `postgres_data` volume across rebuilds.

## Core URLs

- `/login/` - IndieAuth login start
- `/dashboard/` - your plant + embed snippets
- `/u/<username>/` - public profile
- `/u/<username>/plant.svg` - deterministic plant SVG
- `/embed/<username>/plant/` - iframe widget
- `/embed/<username>/roll/` - picked plants widget
- `/api/<username>/plant.json` - JS embed payload
- `/api/<username>/roll.json` - roll JSON
- `/gardn.js` - JS embed loader

## Contributing

- Read `CONTRIBUTING.md` for local setup, checks, and PR expectations.

## License

This project is licensed under the MIT License. See `LICENSE`.

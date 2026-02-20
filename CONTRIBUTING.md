# Contributing

Thanks for your interest in contributing to `gardn`.

## Development setup

1. Fork and clone the repo.
2. Copy environment variables:
   - `cp .env.example .env`
3. Install dependencies:
   - `uv sync --group dev`
4. Run migrations:
   - `uv run python manage.py migrate`
5. Start the app:
   - `uv run python manage.py runserver`

## Running checks

- Django system checks:
  - `uv run python manage.py check`
- Test suite:
  - `uv run python manage.py test`

If you do not have Postgres running locally, you can run checks/tests against
SQLite:

`DATABASE_URL=sqlite:///db.sqlite3 uv run python manage.py test`

## Pull requests

- Keep changes focused and small.
- Add or update tests for behavior changes.
- Update docs when changing user-facing behavior.
- Ensure CI is green before requesting review.

## Reporting issues

- Bug reports and feature requests should be opened as GitHub issues.
- Security issues should follow the process in `SECURITY.md`.

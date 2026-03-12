Original prompt: We're building a Gardn game (in the app `game` inside this repo). Please evaluate this entire repo and help me make a plan to make our Gardn game an absolute banger that helps people not only build their websites but explore the indieweb. Basically I want the game to encourage people to maintain their websites, blog rolls, links, etc. So in-game actions need to be validated against their website. For instance a "Harvest" shouldn't be considered planted in a users in-game garden unless its actually posted to their website. Basically, I need you to be an expert in game design because I am not. I also need it to look better than it currently does. Feel free to ask me questions, and also the wiki at https://indieweb.org is a good place to start for indieweb related questions.

## 2026-03-12

- Planning pass completed: product direction is a cozy, website-first verified IndieWeb adventure with hybrid Micropub/manual publishing support.
- Repo baseline checked: Django system checks are clean; `tests.test_game` and the broader Django tests pass under `--settings=gardn.test_settings` with SQLite.
- Implementation started:
  - Add persisted site evidence and neighbor graph models.
  - Add a scanner service that discovers capabilities and verifies entries/bookmarks/blogroll links.
  - Rework game APIs/state to use verified and pending activities instead of fake counters.
  - Redesign Phaser UI/state flow and expose deterministic testing hooks.
- Implementation completed for this pass:
  - Added `SiteScan`, `VerifiedActivity`, and `NeighborLink`, plus `GardenPlot.verified_activity`.
  - Added a legacy backfill migration for existing planted plots.
  - Added Micropub-backed pending note/bookmark publishing and on-demand site scanning.
  - Replaced the old counter-based game state with verified inventory, pending inventory, site status, neighbors, and evidence-derived quest progress.
  - Reworked the Phaser shell, HUD, world interactions, action modal flow, and testing hooks (`render_game_to_text`, `advanceTime`, fullscreen).
  - Added a fourth zone (`Neighbor Grove`) and warmer "hopeful reclaimed web" presentation.
- Validation:
  - `DATABASE_URL=sqlite:////tmp/gardn-impl-tests.sqlite3 uv run manage.py test --settings=gardn.test_settings tests.test_game`
  - `DATABASE_URL=sqlite:////tmp/gardn-impl-tests.sqlite3 uv run manage.py test --settings=gardn.test_settings tests.test_home_cache tests.test_static_storage tests.test_settings tests.test_svg_cache tests.test_harvest_tasks`
  - `DATABASE_URL=sqlite:////tmp/gardn-impl-tests.sqlite3 uv run manage.py check --settings=gardn.test_settings`
- Follow-up ideas:
  - Add a Playwright-driven authenticated game smoke test once the local login/session setup is scripted.
  - Deepen quest rewards, watering rules, and Webmention-specific interaction rewards.

## 2026-03-12 Planting hotfix

- Investigated a production `DataError` from `POST /game/api/plant/` caused by verified activity titles exceeding the legacy `GardenPlot.link_title` varchar length.
- Added a schema migration to increase `GardenPlot.link_title` from 256 to 500 so it matches `VerifiedActivity.title`.
- Hardened `api_plant_seed` to clamp stored plot titles to the actual database column length before saving, which also protects deploys where code lands before migrations finish.
- Added a regression test covering long verified titles during planting against a smaller simulated database limit.
- Validation:
  - `DATABASE_URL=sqlite:////tmp/gardn-impl-tests.sqlite3 uv run manage.py test --settings=gardn.test_settings tests.test_game`
  - `DATABASE_URL=sqlite:////tmp/gardn-impl-tests.sqlite3 uv run manage.py check --settings=gardn.test_settings`
- Browser smoke note:
  - Prepared a local game smoke path, but the shared Playwright client could not run because the `playwright` Node package is not installed in the current environment.

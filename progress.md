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

## 2026-03-13 HUD safe-area pass

- Fixed the in-game HUD bars so they no longer render on top of the playable map area.
- Added a shared `static/game/js/layout.js` safe-area definition and updated `WorldScene` to inset the gameplay camera viewport beneath the top bar and above the bottom bar.
- Updated `UIScene` to anchor both bars and their text inside those reserved strips, so portals and other map elements are no longer hidden behind the HUD.
- Validation:
  - `node --check static/game/js/layout.js`
  - `node --check static/game/js/scenes/UIScene.js`
  - `node --check static/game/js/scenes/WorldScene.js`
  - `DATABASE_URL=sqlite:////tmp/gardn-impl-tests.sqlite3 uv run manage.py test --settings=gardn.test_settings tests.test_game`
  - `DATABASE_URL=sqlite:////tmp/gardn-impl-tests.sqlite3 uv run manage.py check --settings=gardn.test_settings`
- Browser smoke note:
  - A fresh Playwright-based visual pass is still blocked locally because the `playwright` Node package is not installed in this environment.

## 2026-03-13 Garden visits design pass

- Explored adding garden visits as a health input without replacing the current "site is source of truth" loop.
- Recommended treating visits as pollination/community vitality layered on top of verified site activity, not as the primary health source.
- Reuse existing relationship signals:
  - `Pick` remains lightweight intent/follow.
  - `NeighborLink` remains the verified travel permission derived from blogroll or Gardn roll evidence.
- Suggested flow:
  - Shared garden link can introduce a garden.
  - Travel from the Crossroads should unlock only after the visitor has picked that gardener and their next scan verifies the relationship into a `NeighborLink`.
  - Visiting should record unique, rate-limited guest visits that contribute a capped bonus to garden health.
- Suggested implementation slice:
  - Add a `GardenVisit` model keyed by visitor, host, and day.
  - Add a read-only public garden state endpoint plus a visit recording endpoint.
  - Expose visitable destinations in game state and render them from the Crossroads/Neighbor Grove.
  - Compute a composite garden health metric from site proof, recency, and unique recent visitors, then surface it in the HUD and/or plant bloom state.
- Guardrails:
  - Count only unique authenticated visitors.
  - Cap contribution per day/week to reduce popularity snowballing.
  - Keep solo gardens viable by making visits a bonus, not a survival requirement.

## 2026-03-13 Garden visits implementation pass

- Implemented the first garden-visits slice end to end.
- Backend:
  - Added `GardenVisit` with one counted visit per host/visitor/day.
  - Added composite garden health payloads using site scan state, recent verified activity, and recent unique visitors.
  - Added authenticated guest-garden endpoints for loading a visitable garden and recording a visit.
  - Added a shareable `/game/gardens/<username>/` route that can launch straight into a guest garden when the relationship is already verified.
- Frontend:
  - Added guest-garden runtime state and guest-garden API helpers.
  - Neighbor NPCs in the Neighbor Grove now act as travel points into visitable gardens.
  - Added read-only guest-garden mode using the existing garden map, with return travel back to the grove.
  - Surfaced health/pollination in the HUD and added a visible share link on the game page.
- Behavior notes:
  - Visits are a capped bonus and do not replace publishing/scanning as the main source of garden growth.
  - Guest gardens are read-only; visiting adds pollination but does not allow planting.
- Validation:
  - `DATABASE_URL=sqlite:////tmp/gardn-impl-tests.sqlite3 uv run manage.py check --settings=gardn.test_settings`
  - `DATABASE_URL=sqlite:////tmp/gardn-impl-tests.sqlite3 uv run manage.py test --settings=gardn.test_settings tests.test_game`
  - `node --check static/game/js/state.js`
  - `node --check static/game/js/scenes/TitleScene.js`
  - `node --check static/game/js/scenes/UIScene.js`
  - `node --check static/game/js/scenes/WorldScene.js`
- Browser smoke note:
  - Playwright is still unavailable in this environment: `npx` exists, but the local `playwright` Node package is not installed, so the shared web-game client could not be run yet.

## 2026-03-13 Modal input + joy pass

- Fixed the action modal input flow so text-entry dialogs suspend gameplay hotkeys while open.
- Frontend behavior:
  - Added shared hotkey-suspension helpers in game state.
  - Plant/note/bookmark/scan modals now disable gameplay keyboard capture while open, stop key propagation from the dialog, and autofocus the first field.
  - World hotkeys now ignore input/modal contexts, so `Space`, `WASD`, `R`, `N`, `B`, and `F` no longer interfere with typing.
  - Removed the duplicate world-scene fullscreen binding and kept the global `F` handler gated behind the hotkey-suspension check.
- Joy/feedback behavior:
  - Scan, note publish, and bookmark publish now close their modal immediately after valid submission.
  - Added a reusable world-scene celebration burst plus toast feedback for scan and publish actions.
  - Scan now gets both a "starting" pulse and a brighter completion bloom; note/bookmark publishing get their own themed bursts and success/error toasts.
- Validation:
  - `node --check static/game/js/state.js`
  - `node --check static/game/js/game.js`
  - `node --check static/game/js/scenes/WorldScene.js`
  - `node --check static/game/js/scenes/PlantScene.js`
  - `DATABASE_URL=sqlite:////tmp/gardn-impl-tests.sqlite3 uv run manage.py test --settings=gardn.test_settings tests.test_game`
  - `DATABASE_URL=sqlite:////tmp/gardn-impl-tests.sqlite3 uv run manage.py check --settings=gardn.test_settings`
- Browser smoke note:
  - `npx` is installed, but the local `playwright` Node package is still missing (`require.resolve('playwright')` fails), so the shared Playwright game client remains blocked in this environment.
- Follow-up fix:
  - Repaired the scan button handoff by passing the live `WorldScene` instance into `PlantScene` and adding a direct fallback scan path if that reference is ever unavailable.
  - Added Enter-to-submit support for the scan URL field so `Shift+R`, paste/type URL, `Enter` now triggers `/game/api/scan/` instead of leaving submission unwired.
  - Confirmed `gardn.dev` was already serving the updated JS; the remaining bug was that modal-originated scans still hit `WorldScene._triggerScan()` in the same tick and got short-circuited by the `PlantScene` active guard. Added an explicit `allowWhileModalOpen` override for modal submissions.
  - Updated the backend scan flow so the optional `page_url` is parsed for h-entry / bookmark evidence too, instead of being used only for blogroll discovery. This now promotes pending bookmarks when their permalink page is scanned directly, and avoids incorrectly flagging `missing_blogroll` when that manual page is clearly a post/bookmark page.

## 2026-03-13 Async verification pass

- Implemented background Micropub verification for pending note/bookmark seeds.
- Backend behavior:
  - Added `game.tasks.verify_published_activity`, a Celery task that rescans the Micropub-created permalink URL, retries with backoff while proof is not visible yet, and marks the activity `failed` after exhausting retries.
  - Wired publish endpoints to enqueue that task whenever Micropub returns a `Location` URL, so successful publishes immediately start trying to verify themselves.
- Frontend behavior:
  - Added lightweight pending-verification polling in `static/game/js/state.js` that refreshes `/game/api/state/` every few seconds only while pending inventory exists.
  - Poll-driven state refreshes now emit a dedicated inventory-promotion event so `WorldScene` can celebrate when pending proof blooms into a real seed without double-firing on manual scans.
- Tests and validation:
  - Updated publish endpoint tests to assert the verification worker is enqueued.
  - Added a regression test proving the worker can promote a Micropub-created pending note into a verified seed when its permalink exposes h-entry markup.
  - `node --check static/game/js/state.js`
  - `node --check static/game/js/scenes/WorldScene.js`
  - `DATABASE_URL=sqlite:////tmp/gardn-impl-tests.sqlite3 uv run manage.py test --settings=gardn.test_settings tests.test_game`
  - `DATABASE_URL=sqlite:////tmp/gardn-impl-tests.sqlite3 uv run manage.py check --settings=gardn.test_settings`
- Browser smoke note:
  - The shared Playwright loop is still blocked locally because the `playwright` Node package is not installed (`require.resolve('playwright')` fails).

## 2026-03-13 Portal + neighbor cleanup pass

- Cleaned up confusing legacy world markers:
  - Removed the obsolete yellow "echo node" pickups from the world scene so Crossroads and Link Library no longer show fake collectible-looking squares.
- Portal clarity pass:
  - Reworked portal rendering in `WorldScene` from faint translucent rectangles into animated glowing doorways with chevrons and destination labels so it is much clearer that they are traversable map transitions.
  - Removed the duplicate Neighbor Grove return portal overlay on the neighbors map while keeping the guest-garden return gate.
- Neighbor Grove / scan persistence pass:
  - The grove now renders the full discovered neighbor list in a grid instead of silently truncating at four NPCs.
  - Neighbor NPCs now distinguish visitable gardens from remembered-but-not-yet-visitable contacts, with dialog that explains why some neighbors cannot be entered yet instead of doing nothing.
  - Updated neighbor serialization to include a `visitable` flag for the frontend/testing hooks.
  - Updated site scans to automatically revisit previously discovered same-origin neighbor source pages, which keeps Gardn-roll/manual-page neighbors from disappearing on later home-page-only scans.
- Validation:
  - `node --check static/game/js/scenes/WorldScene.js`
  - `node --check static/game/js/state.js`
  - `DATABASE_URL=sqlite:////tmp/gardn-impl-tests.sqlite3 uv run manage.py test --settings=gardn.test_settings tests.test_game`
- Browser smoke note:
  - Installed `playwright` into `/tmp/codex-playwright`, but I still do not have a scripted authenticated browser session flow for `/game/`, so I could not complete the requested visual Playwright pass yet.

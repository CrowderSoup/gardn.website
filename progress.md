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

## 2026-03-13 Journey mapping pass

- Documented the current player journey in `docs/game-flow.md`.
- Added two Mermaid diagrams:
  - A spatial map graph for Crossroads, Homestead Garden, Link Library, Neighbor Grove, Guest Garden, and the shared-link entry path.
  - A progression flowchart covering login, tutorial branching, publish/scan/plant loops, Micropub pending verification, neighbor discovery, and guest-garden visits.
- Added a storyboard table describing the playable beats in plain English so design discussions can reference the current experience without re-reading scene code.
- Notes:
  - This is intentionally a "where we are so far" snapshot, not a future-state design doc.
  - `GardenScene` is still present in code, but the active playable journey runs through `WorldScene` plus overlay scenes/modals.

## 2026-03-13 Public beta systems pass

- Implemented the first large public-beta feature slice across backend and client:
  - Added persisted appearance settings (`body_style`, `skin_tone`, `outfit_key`) plus `appearance_configured`.
  - Added homestead settings (`garden_name`, `gate_state`, `homestead_level`, `path_style`, `fence_style`, `read_later_tag`) and anchored `GardenDecoration`.
  - Added Neighbor Grove social data models for short-poll presence and public chat (`GrovePresence`, `GroveMessage`).
- Backend/API work:
  - Extended `/game/api/state/` with `appearance`, `homestead`, `library_summary`, `padd_badges`, `gate_state`, and grove summary data.
  - Added endpoints for profile updates, homestead updates, decor placement, paginated Link Library data, grove presence listing/heartbeat, and grove message listing/posting.
  - Updated guest-garden access to require both a rooted neighbor link and an open host gate.
  - Added a migration plus backfill for garden names on existing profiles.
- Frontend/gameplay work:
  - Added a DOM-based PADD overlay opened with `Tab` or an on-screen button.
  - Shipped five tabs: Seeds, Library, Quests, Neighbors, and Profile.
  - Added forced first-launch profile setup via the PADD before play fully opens up.
  - Reworked the Neighbor Grove presentation from cloned NPCs toward gate/plaque visuals and connected the Archivist/Wanderer to the new PADD tabs.
  - Made homestead customization visible in-world with styled path/fence framing, decor sockets, signpost interactions, and light player appearance styling.
  - Slimmed the HUD copy and updated tutorial copy toward the new beta flow.
  - Retired the unused `GardenScene` from the active Phaser scene list.
- Validation:
  - `UV_CACHE_DIR=/tmp/uv-cache uv run python -m py_compile game/views.py game/models.py tests/test_game.py`
  - `node --check static/game/js/state.js`
  - `node --check static/game/js/padd.js`
  - `node --check static/game/js/game.js`
  - `node --check static/game/js/scenes/WorldScene.js`
  - `node --check static/game/js/scenes/TutorialScene.js`
  - `node --check static/game/js/scenes/UIScene.js`
  - `UV_CACHE_DIR=/tmp/uv-cache DATABASE_URL=sqlite:////tmp/gardn-impl-tests.sqlite3 uv run manage.py test --settings=gardn.test_settings tests.test_game`
  - `UV_CACHE_DIR=/tmp/uv-cache DATABASE_URL=sqlite:////tmp/gardn-impl-tests.sqlite3 uv run manage.py check --settings=gardn.test_settings`
- Browser smoke note:
  - Re-attempted the shared Playwright loop. The client script can run if copied under `/tmp/codex-playwright`, but a meaningful authenticated smoke remains blocked locally because the app still requires a real login/session flow and the available local settings use non-shared fake-cache sessions.
- Follow-up ideas:
  - Add a local debug login/session path or switch the smoke environment to a shared session backend so the Playwright authenticated flow can finally cover in-world states.
  - Add richer player sprite variations or layered art so appearance choices are more visually distinct than the current tint/scale treatment.

## 2026-03-13 PADD regression cleanup

- Fixed the Firefox-side profile form validation warning by removing the native `pattern` attribute from the read-later tag input and validating it in JS before submit.
- Fixed the large white bar seen over gameplay while the PADD is open:
  - Switched the PADD panel to border-box sizing.
  - Prevented horizontal overflow on the shell/panel.
  - Added `min-width: 0` safeguards to grid/form children so wide controls do not force a horizontal scrollbar.
- Disabled Phaser audio boot for now (`audio.noAudio = true`) since the game does not currently ship sound, which avoids the browser's auto-start `AudioContext` warning.
- Added a real site favicon (`static/favicon.svg`) and wired it into `templates/base.html` so browsers stop falling back to `/favicon.ico`.
- Validation:
  - `node --check static/game/js/padd.js`
  - `node --check static/game/js/game.js`
  - `UV_CACHE_DIR=/tmp/uv-cache DATABASE_URL=sqlite:////tmp/gardn-impl-tests.sqlite3 uv run manage.py check --settings=gardn.test_settings`
  - `UV_CACHE_DIR=/tmp/uv-cache DATABASE_URL=sqlite:////tmp/gardn-impl-tests.sqlite3 uv run manage.py test --settings=gardn.test_settings tests.test_game`
- Browser smoke note:
  - I verified a local Django server can be started for smoke work on `http://127.0.0.1:8010/`, but the shared Playwright client still cannot complete a run on this machine because the Playwright Chromium binary has not been downloaded yet (`npx playwright install` needed).
  - Even after that browser install, an authenticated in-world smoke would still need either a scripted local login path or a shared session backend because `gardn.test_settings` uses in-process fake-cache sessions that do not survive across the server/browser boundary.

## 2026-03-13 PADD hidden-state fix

- Fixed a follow-up regression where the PADD shell could still cover the game while "closed".
- Root cause: `.gardn-padd-shell { display: flex; }` and similar button styles were overriding the browser's default `[hidden] { display: none; }` behavior.
- Added explicit `[hidden]` rules for the PADD shell, button, and badge in `static/game/css/game-shell.css` so closed PADD UI truly leaves the playfield clickable again.

## 2026-03-13 Neighbor Grove safety + facelift pass

- Fixed the trap where players could get wedged between locked neighbor gates and lose access to the return portal.
- Reworked the grove layout in `static/game/js/scenes/WorldScene.js`:
  - Neighbor gates are no longer solid physics bodies; they are now proximity interactives, so they can still be examined/entered without blocking movement.
  - Replaced the dense grid with a more deliberate plaza layout that keeps the center lane open.
  - Added a clearer reclaimed-square atmosphere pass, with a central plaza and an obvious route from the grove interior back to the exit.
  - Added a much wider custom return portal plus a `RETURN TO THE CROSSROADS` label.
  - Moved the default Neighbor Grove spawn to a safe entrance position instead of dropping the player into the middle of the gate cluster.
  - Corrected initial player tile coordinates so saved position starts from the actual spawn point.
- Validation:
  - `node --check static/game/js/scenes/WorldScene.js`
  - `node --check static/game/js/game.js`
  - `UV_CACHE_DIR=/tmp/uv-cache DATABASE_URL=sqlite:////tmp/gardn-impl-tests.sqlite3 uv run manage.py test --settings=gardn.test_settings tests.test_game`
  - `UV_CACHE_DIR=/tmp/uv-cache DATABASE_URL=sqlite:////tmp/gardn-impl-tests.sqlite3 uv run manage.py check --settings=gardn.test_settings`
- Browser smoke note:
  - Re-ran the shared Playwright client, but it still cannot launch locally because the Playwright Chromium binary has not been downloaded yet (`npx playwright install` needed).

## 2026-03-13 Neighbor Grove bounce-back follow-up

- Investigated a new report that entering the Neighbor Grove could immediately kick the player back out again.
- Root cause:
  - The custom Neighbor Grove spawn override only applied when entering via a portal spawn (`player_start`), and the original override position sat too close to the new oversized return portal.
  - That meant a real transition from the Crossroads could land the player inside the return portal overlap zone and instantly bounce them back to the Crossroads.
- Fix:
  - Moved the Neighbor Grove entry spawn farther up the center lane in `static/game/js/scenes/WorldScene.js`.
  - Added a test-settings-only `/game/playwright-login/` helper route so local Playwright smoke runs can create a real authenticated session without touching production auth flows.
  - Added a regression test covering that smoke-login route.
- Validation:
  - `node --check static/game/js/scenes/WorldScene.js`
  - `UV_CACHE_DIR=/tmp/uv-cache DATABASE_URL=sqlite:////tmp/gardn-impl-tests.sqlite3 uv run manage.py test --settings=gardn.test_settings tests.test_game`
  - `UV_CACHE_DIR=/tmp/uv-cache DATABASE_URL=sqlite:////tmp/gardn-impl-tests.sqlite3 uv run manage.py check --settings=gardn.test_settings`
  - Local Playwright browser run now succeeds end-to-end with the shared client after `npx playwright install`.
  - A direct authenticated load into `current_map: "neighbors"` stayed in the grove instead of immediately returning to `overworld`.
- Remaining smoke limitation:
  - I could not fully automate the exact Crossroads-to-Grove walking transition with the shared client because its current virtual-time stepping under-moves the player in the overworld. The server/browser state after the direct grove load is good, and the portal-overlap root cause has been patched in code.

## 2026-03-13 Neighbor Grove size + art pass

- Expanded the Neighbor Grove into a larger bespoke scene instead of the tiny placeholder tilemap:
  - Added a world-size override so the grove can be substantially wider/taller than the old 16x16 map.
  - Stopped using the tiny tiled neighbor map for rendering and now draw the grove as a scene-authored square.
- Added better asset usage from `static/game/assets/tilesets/`:
  - Loaded the tilesets as sprite sheets in `BootScene` so they can be used as actual scene props instead of only as map tiles.
  - Built a grassy reclaimed ground pass from `lpc-base`.
  - Added market-stall, crate, barrel, hay, boardwalk, and trellis details from `lpc-farming` and `lpc-crops` around the grove to make it feel more like a town square.
  - Spread the neighbor gate slots out across the larger space so the grove reads as a plaza with lanes, not a cramped grid.
- Validation:
  - `node --check static/game/js/scenes/BootScene.js`
  - `node --check static/game/js/scenes/WorldScene.js`
  - `UV_CACHE_DIR=/tmp/uv-cache DATABASE_URL=sqlite:////tmp/gardn-impl-tests.sqlite3 uv run manage.py test --settings=gardn.test_settings tests.test_game`
  - `UV_CACHE_DIR=/tmp/uv-cache DATABASE_URL=sqlite:////tmp/gardn-impl-tests.sqlite3 uv run manage.py check --settings=gardn.test_settings`
  - Authenticated local Playwright load into `/game/` still boots into `current_map: "neighbors"` with the new art/layout pass.
- Note:
  - The shared Playwright client still captures black WebGL screenshots in headless mode on this machine, so the most reliable automated verification artifact here is the emitted `render_game_to_text` state plus the absence of console errors.
- Follow-up validation:
  - Re-ran the authenticated local Playwright smoke against `http://127.0.0.1:8010/game/playwright-login/?username=playwright&map=neighbors&next=/game/`.
  - The first captured state still shows the title boot before auth/state hydration finishes, but the settled state (`state-2.json`) lands in `current_map: "neighbors"` with the enlarged grove loaded and no console-error artifact emitted.
  - Re-ran:
    - `node --check static/game/js/scenes/BootScene.js`
    - `node --check static/game/js/scenes/WorldScene.js`
    - `UV_CACHE_DIR=/tmp/uv-cache DATABASE_URL=sqlite:////tmp/gardn-impl-tests.sqlite3 uv run manage.py check --settings=gardn.test_settings`
    - `UV_CACHE_DIR=/tmp/uv-cache DATABASE_URL=sqlite:////tmp/gardn-impl-tests.sqlite3 uv run manage.py test --settings=gardn.test_settings tests.test_game`

## 2026-03-13 Neighbor Grove pathing cleanup

- Followed up on visual feedback that the grove felt like random produce clutter instead of a believable plaza.
- Reworked the grove dressing in `static/game/js/scenes/WorldScene.js`:
  - Removed the fish / fruit / market scatter pass.
  - Added a more intentional path language built from `post-apoc-16` paver tiles for the main entry lane, plaza floor, and branch nodes toward the gates.
  - Shifted the gate connectors to read more like path spurs instead of wooden clutter.
  - Kept the scene alive with grass clumps and light ruin markers around the edges rather than dumping item props into the square.
- Validation:
  - `node --check static/game/js/scenes/WorldScene.js`
  - `UV_CACHE_DIR=/tmp/uv-cache DATABASE_URL=sqlite:////tmp/gardn-impl-tests.sqlite3 uv run manage.py check --settings=gardn.test_settings`
  - `UV_CACHE_DIR=/tmp/uv-cache DATABASE_URL=sqlite:////tmp/gardn-impl-tests.sqlite3 uv run manage.py test --settings=gardn.test_settings tests.test_game`
  - Authenticated Playwright smoke still settles into `current_map: "neighbors"` with no console-error artifact emitted.

## 2026-03-13 Broader world art pass

- Applied the same authored-scene treatment to the other major maps in `static/game/js/scenes/WorldScene.js`:
  - Crossroads now has clearer civic paving, route legibility toward the main exits, and a few deliberate ruin markers / grass clusters so it reads more like a central hub.
  - Link Library now has a more intentional ruined-archive floor plan with paver fields, framing ruins, and restrained wood details instead of mostly empty tilemap space.
  - Homestead got softer environmental dressing plus rebuild-safe path tiles, so the area around the plot grid feels more tended and the path-style setting has more visible presence.
- Refactored the paver stamping helper so it can be reused across maps and also participate in Homestead rebuilds after profile changes.
- Validation:
  - `node --check static/game/js/scenes/WorldScene.js`
  - `UV_CACHE_DIR=/tmp/uv-cache DATABASE_URL=sqlite:////tmp/gardn-impl-tests.sqlite3 uv run manage.py check --settings=gardn.test_settings`
  - `UV_CACHE_DIR=/tmp/uv-cache DATABASE_URL=sqlite:////tmp/gardn-impl-tests.sqlite3 uv run manage.py test --settings=gardn.test_settings tests.test_game`
  - Authenticated Playwright smoke with isolated users settled into:
    - `current_map: "overworld"`
    - `current_map: "ruins"`
    - `current_map: "garden"`
    - `current_map: "neighbors"`
  - No console-error artifact was emitted for those smoke loads.
- Remaining visual-validation caveat:
  - Headless WebGL screenshots from the shared client are still black on this machine, so the reliable automated artifact remains `render_game_to_text` state plus console cleanliness.

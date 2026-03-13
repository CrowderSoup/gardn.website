const runtimeState = window.__GARDN_RUNTIME_STATE || {
  server: null,
  guestGarden: null,
  currentMapId: 'overworld',
  playerSnapshot: {
    x: 0,
    y: 0,
    tileX: 0,
    tileY: 0,
    facing: 'down',
  },
  ui: {
    mode: 'boot',
    status: '',
    fullscreen: false,
    hotkeysSuspended: false,
    paddOpen: false,
    paddTab: 'seeds',
  },
};

window.__GARDN_RUNTIME_STATE = runtimeState;
const EDITABLE_TARGET_SELECTOR = 'input, textarea, select, [contenteditable=""], [contenteditable="true"]';
const PENDING_VERIFICATION_POLL_MS = 5000;
let pendingVerificationTimer = 0;
let pendingVerificationRequest = null;

function emitChange() {
  window.dispatchEvent(new CustomEvent('gardn:state-change', { detail: getRuntimeState() }));
}

function inventoryCounts(serverState) {
  return {
    verified: serverState?.verified_inventory?.length || 0,
    pending: serverState?.pending_inventory?.length ?? serverState?.player?.pending_count ?? 0,
  };
}

function emitInventoryPromotion(previousState, nextState) {
  if (!previousState || !nextState) return;
  const before = inventoryCounts(previousState);
  const after = inventoryCounts(nextState);
  if (after.pending >= before.pending) return;

  const promotedCount = Math.max(0, after.verified - before.verified);
  if (!promotedCount) return;

  window.dispatchEvent(new CustomEvent('gardn:inventory-promoted', {
    detail: {
      promotedCount,
      previous: before,
      current: after,
    },
  }));
}

function toElement(target) {
  if (!target) return null;
  if (target instanceof Element) return target;
  return target.parentElement || null;
}

function pendingVerificationCount(serverState = runtimeState.server) {
  const inventoryPending = serverState?.pending_inventory?.length;
  if (typeof inventoryPending === 'number') return inventoryPending;
  return serverState?.player?.pending_count || 0;
}

function clearPendingVerificationPolling() {
  if (!pendingVerificationTimer) return;
  window.clearTimeout(pendingVerificationTimer);
  pendingVerificationTimer = 0;
}

async function pollPendingVerificationState() {
  if (!pendingVerificationCount() || pendingVerificationRequest) return pendingVerificationRequest;
  pendingVerificationRequest = refreshServerState({ emitPromotion: true })
    .catch(() => null)
    .finally(() => {
      pendingVerificationRequest = null;
      ensurePendingVerificationPolling();
    });
  return pendingVerificationRequest;
}

export function ensurePendingVerificationPolling({ immediate = false } = {}) {
  if (!pendingVerificationCount()) {
    clearPendingVerificationPolling();
    return pendingVerificationRequest;
  }
  if (immediate) {
    clearPendingVerificationPolling();
    void pollPendingVerificationState();
    return pendingVerificationRequest;
  }
  if (pendingVerificationRequest || pendingVerificationTimer) return pendingVerificationRequest;
  pendingVerificationTimer = window.setTimeout(() => {
    pendingVerificationTimer = 0;
    void pollPendingVerificationState();
  }, PENDING_VERIFICATION_POLL_MS);
  return pendingVerificationRequest;
}

function cloneServerState() {
  return runtimeState.server ? structuredClone(runtimeState.server) : null;
}

function urlForUser(template, username) {
  return template.replace('__USERNAME__', encodeURIComponent(username));
}

async function requestJson(url, { method = 'GET', body = null } = {}) {
  const init = {
    method,
    credentials: 'same-origin',
    headers: {},
  };
  if (body !== null) {
    init.headers['Content-Type'] = 'application/json';
    init.headers['X-CSRFToken'] = window.GAME_CONFIG.csrfToken;
    init.body = JSON.stringify(body);
  }

  const response = await fetch(url, init);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || `Request failed (${response.status})`);
  }
  return payload;
}

export function getRuntimeState() {
  return runtimeState;
}

export function isEditableTarget(target = document.activeElement) {
  const element = toElement(target);
  return Boolean(element?.closest?.(EDITABLE_TARGET_SELECTOR));
}

export function areHotkeysSuspended(eventOrTarget = document.activeElement) {
  const target = eventOrTarget?.target ?? eventOrTarget;
  return Boolean(runtimeState.ui.hotkeysSuspended) || isEditableTarget(target);
}

export function setServerState(serverState, options = {}) {
  const { emitPromotion = false } = options;
  const previousServerState = runtimeState.server;
  runtimeState.server = serverState;
  if (!(runtimeState.guestGarden && runtimeState.currentMapId === 'guest_garden')) {
    runtimeState.currentMapId = serverState?.player?.map_id || runtimeState.currentMapId;
  }
  emitChange();
  if (emitPromotion) emitInventoryPromotion(previousServerState, serverState);
  ensurePendingVerificationPolling();
  return serverState;
}

export function setGuestGarden(guestGarden) {
  runtimeState.guestGarden = guestGarden;
  emitChange();
  return guestGarden;
}

export function clearGuestGarden() {
  runtimeState.guestGarden = null;
  emitChange();
}

export async function refreshServerState(options = {}) {
  const response = await fetch(window.GAME_CONFIG.stateUrl, { credentials: 'same-origin' });
  if (!response.ok) {
    throw new Error(`Could not load game state (${response.status})`);
  }
  const payload = await response.json();
  return setServerState(payload, options);
}

export async function fetchGuestGarden(username) {
  const response = await fetch(urlForUser(window.GAME_CONFIG.guestGardenUrlTemplate, username), {
    credentials: 'same-origin',
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || 'Could not load that garden');
  }
  return setGuestGarden(payload);
}

export async function recordGardenVisit(username) {
  const response = await fetch(urlForUser(window.GAME_CONFIG.guestGardenVisitUrlTemplate, username), {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': window.GAME_CONFIG.csrfToken,
    },
    body: JSON.stringify({}),
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || 'Could not record visit');
  }
  if (payload.garden_state) {
    setGuestGarden(payload.garden_state);
  }
  return payload;
}

export function patchServerState(patcher) {
  const nextState = cloneServerState() || {};
  patcher(nextState);
  return setServerState(nextState);
}

export function setCurrentMapId(mapId) {
  runtimeState.currentMapId = mapId;
  if (runtimeState.server?.player) {
    runtimeState.server.player.map_id = mapId;
  }
  emitChange();
}

export function setPlayerSnapshot(snapshot) {
  runtimeState.playerSnapshot = { ...runtimeState.playerSnapshot, ...snapshot };
  emitChange();
}

export function setUiState(patch) {
  runtimeState.ui = { ...runtimeState.ui, ...patch };
  emitChange();
}

export function openPadd(tab = runtimeState.ui.paddTab || 'seeds') {
  setUiState({ paddOpen: true, paddTab: tab });
}

export function closePadd() {
  setUiState({ paddOpen: false });
}

export function togglePadd(tab = null) {
  setUiState({
    paddOpen: !runtimeState.ui.paddOpen,
    paddTab: tab || runtimeState.ui.paddTab || 'seeds',
  });
}

export function updateGardenPlot(plotData) {
  patchServerState((server) => {
    server.garden = server.garden || [];
    const existing = server.garden.find((plot) => plot.slot_x === plotData.slot_x && plot.slot_y === plotData.slot_y);
    if (existing) {
      Object.assign(existing, plotData);
      return;
    }
    server.garden.push(plotData);
  });
}

export function replaceInventory(payload) {
  patchServerState((server) => {
    server.verified_inventory = payload.verified_inventory || [];
    server.pending_inventory = payload.pending_inventory || [];
    if (server.player) {
      server.player.links_harvested = server.verified_inventory.length;
      server.player.pending_count = server.pending_inventory.length;
    }
  });
}

export async function runSiteScan(pageUrl = '') {
  const response = await fetch(window.GAME_CONFIG.scanUrl, {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': window.GAME_CONFIG.csrfToken,
    },
    body: JSON.stringify({ page_url: pageUrl }),
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || 'Scan failed');
  }
  setServerState(payload.state);
  return payload;
}

export async function publishBookmark(targetUrl, title = '') {
  const response = await fetch(window.GAME_CONFIG.publishBookmarkUrl, {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': window.GAME_CONFIG.csrfToken,
    },
    body: JSON.stringify({ target_url: targetUrl, title }),
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || 'Could not publish bookmark');
  }
  patchServerState((server) => {
    server.pending_inventory = [payload.activity, ...(server.pending_inventory || [])];
    if (server.player) {
      server.player.pending_count = server.pending_inventory.length;
    }
  });
  ensurePendingVerificationPolling({ immediate: true });
  return payload.activity;
}

export async function publishNote(content, title = '') {
  const response = await fetch(window.GAME_CONFIG.publishNoteUrl, {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': window.GAME_CONFIG.csrfToken,
    },
    body: JSON.stringify({ content, title }),
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || 'Could not publish note');
  }
  patchServerState((server) => {
    server.pending_inventory = [payload.activity, ...(server.pending_inventory || [])];
    if (server.player) {
      server.player.pending_count = server.pending_inventory.length;
    }
  });
  ensurePendingVerificationPolling({ immediate: true });
  return payload.activity;
}

export async function plantVerifiedActivity(slotX, slotY, verifiedActivityId) {
  const response = await fetch(window.GAME_CONFIG.plantUrl, {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': window.GAME_CONFIG.csrfToken,
    },
    body: JSON.stringify({
      slot_x: slotX,
      slot_y: slotY,
      verified_activity_id: verifiedActivityId,
    }),
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || 'Could not plant verified activity');
  }
  return payload;
}

export async function toggleFullscreen(rootEl = document.getElementById('game-root')) {
  if (!rootEl) return false;
  if (!document.fullscreenElement) {
    await rootEl.requestFullscreen();
    setUiState({ fullscreen: true });
    return true;
  }
  await document.exitFullscreen();
  setUiState({ fullscreen: false });
  return false;
}

export async function updateProfileSettings(payload) {
  const response = await requestJson(window.GAME_CONFIG.profileUrl, {
    method: 'POST',
    body: payload,
  });
  patchServerState((server) => {
    server.appearance = response.appearance;
    server.homestead = response.homestead;
    server.library_summary = response.library_summary;
    server.gate_state = response.homestead?.gate_state || server.gate_state;
    if (server.player) {
      server.player.appearance_configured = Boolean(response.appearance?.configured);
    }
  });
  return response;
}

export async function updateHomesteadSettings(payload) {
  const response = await requestJson(window.GAME_CONFIG.homesteadUrl, {
    method: 'POST',
    body: payload,
  });
  patchServerState((server) => {
    server.homestead = response.homestead;
    server.gate_state = response.gate_state || response.homestead?.gate_state || server.gate_state;
    if (server.owner && response.homestead?.garden_name) {
      server.owner.garden_name = response.homestead.garden_name;
    }
  });
  return response;
}

export async function updateGardenDecoration(slotKey, decorKey, variantKey = '') {
  const response = await requestJson(window.GAME_CONFIG.homesteadDecorUrl, {
    method: 'POST',
    body: {
      slot_key: slotKey,
      decor_key: decorKey,
      variant_key: variantKey,
    },
  });
  patchServerState((server) => {
    server.homestead = response.homestead;
  });
  return response;
}

export async function fetchLibrary({ view = 'recent', q = '', page = 1 } = {}) {
  const params = new URLSearchParams({
    view,
    page: String(page),
  });
  if (q) params.set('q', q);
  return requestJson(`${window.GAME_CONFIG.libraryUrl}?${params.toString()}`);
}

export async function fetchGrovePresence() {
  return requestJson(window.GAME_CONFIG.grovePresenceUrl);
}

export async function heartbeatGrovePresence(currentMap = runtimeState.currentMapId) {
  return requestJson(window.GAME_CONFIG.grovePresenceHeartbeatUrl, {
    method: 'POST',
    body: { current_map: currentMap },
  });
}

export async function fetchGroveMessages() {
  return requestJson(window.GAME_CONFIG.groveMessagesUrl);
}

export async function postGroveMessage(content, currentMap = runtimeState.currentMapId) {
  return requestJson(window.GAME_CONFIG.grovePostMessageUrl, {
    method: 'POST',
    body: { content, current_map: currentMap },
  });
}

export async function completeQuest(questSlug) {
  const response = await requestJson(window.GAME_CONFIG.questCompleteUrl, {
    method: 'POST',
    body: { quest_slug: questSlug },
  });
  await refreshServerState();
  return response;
}

export function renderStateToText() {
  const server = runtimeState.server || {};
  const guestGarden = runtimeState.guestGarden || null;
  const activeGarden = guestGarden?.garden || server.garden || [];
  const activeOwner = guestGarden?.owner || server.owner || null;
  const activeHealth = guestGarden?.garden_health || server.garden_health || null;
  const payload = {
    mode: runtimeState.ui.mode,
    coordinate_system: 'tile coordinates use origin at top-left; +x right, +y down',
    current_map: runtimeState.currentMapId,
    player: {
      display_name: server.player?.display_name || '',
      x: runtimeState.playerSnapshot.x,
      y: runtimeState.playerSnapshot.y,
      tile_x: runtimeState.playerSnapshot.tileX,
      tile_y: runtimeState.playerSnapshot.tileY,
      facing: runtimeState.playerSnapshot.facing,
      appearance_configured: server.player?.appearance_configured || false,
    },
    active_garden_owner: activeOwner,
    garden_health: activeHealth,
    site_status: server.site_status || null,
    appearance: server.appearance || null,
    homestead: server.homestead || null,
    library_summary: server.library_summary || null,
    grove: server.grove || null,
    capabilities: server.capabilities || {},
    verified_inventory: (server.verified_inventory || []).map((item) => ({
      id: item.id,
      kind: item.kind,
      title: item.title,
      canonical_url: item.canonical_url,
      source_url: item.source_url,
    })),
    pending_inventory: (server.pending_inventory || []).map((item) => ({
      id: item.id,
      kind: item.kind,
      title: item.title,
      canonical_url: item.canonical_url,
      source_url: item.source_url,
    })),
    garden: activeGarden.map((plot) => ({
      slot_x: plot.slot_x,
      slot_y: plot.slot_y,
      title: plot.link_title,
      link_url: plot.link_url,
      kind: plot.kind,
      status: plot.status,
      growth_stage: plot.growth_stage,
    })),
    guest_garden: guestGarden ? {
      owner: guestGarden.owner,
      visit: guestGarden.visit,
    } : null,
    neighbors: (server.neighbors || []).map((neighbor) => ({
      username: neighbor.username,
      display_name: neighbor.display_name,
      target_url: neighbor.target_url,
      relationship: neighbor.relationship,
      visitable: Boolean(neighbor.visitable),
    })),
    quests: (server.quests || []).map((quest) => ({
      slug: quest.slug,
      status: quest.status,
      progress: quest.progress,
      target: quest.target,
    })),
    ui: {
      padd_open: Boolean(runtimeState.ui.paddOpen),
      padd_tab: runtimeState.ui.paddTab,
    },
  };
  return JSON.stringify(payload);
}

export function installTestingHooks(game) {
  window.render_game_to_text = renderStateToText;
  window.advanceTime = (ms = 16) => {
    const delta = 1000 / 60;
    const steps = Math.max(1, Math.round(ms / delta));
    const scenes = game.scene.getScenes(true);
    for (let i = 0; i < steps; i += 1) {
      scenes.forEach((scene) => {
        if (typeof scene.update === 'function') {
          scene.update(i * delta, delta);
        }
      });
    }
    return renderStateToText();
  };
  window.toggleGardnFullscreen = () => toggleFullscreen();
}

document.addEventListener('fullscreenchange', () => {
  setUiState({ fullscreen: Boolean(document.fullscreenElement) });
});

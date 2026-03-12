const runtimeState = window.__GARDN_RUNTIME_STATE || {
  server: null,
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
  },
};

window.__GARDN_RUNTIME_STATE = runtimeState;

function emitChange() {
  window.dispatchEvent(new CustomEvent('gardn:state-change', { detail: getRuntimeState() }));
}

function cloneServerState() {
  return runtimeState.server ? structuredClone(runtimeState.server) : null;
}

export function getRuntimeState() {
  return runtimeState;
}

export function setServerState(serverState) {
  runtimeState.server = serverState;
  runtimeState.currentMapId = serverState?.player?.map_id || runtimeState.currentMapId;
  emitChange();
  return serverState;
}

export async function refreshServerState() {
  const response = await fetch(window.GAME_CONFIG.stateUrl, { credentials: 'same-origin' });
  if (!response.ok) {
    throw new Error(`Could not load game state (${response.status})`);
  }
  const payload = await response.json();
  return setServerState(payload);
}

export function patchServerState(patcher) {
  const nextState = cloneServerState() || {};
  patcher(nextState);
  runtimeState.server = nextState;
  emitChange();
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

export function renderStateToText() {
  const server = runtimeState.server || {};
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
    },
    site_status: server.site_status || null,
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
    garden: (server.garden || []).map((plot) => ({
      slot_x: plot.slot_x,
      slot_y: plot.slot_y,
      title: plot.link_title,
      link_url: plot.link_url,
      kind: plot.kind,
      status: plot.status,
      growth_stage: plot.growth_stage,
    })),
    neighbors: (server.neighbors || []).map((neighbor) => ({
      username: neighbor.username,
      display_name: neighbor.display_name,
      target_url: neighbor.target_url,
      relationship: neighbor.relationship,
    })),
    quests: (server.quests || []).map((quest) => ({
      slug: quest.slug,
      status: quest.status,
      progress: quest.progress,
      target: quest.target,
    })),
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

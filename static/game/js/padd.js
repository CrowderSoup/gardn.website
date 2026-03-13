import {
  closePadd,
  completeQuest,
  fetchGroveMessages,
  fetchGrovePresence,
  fetchLibrary,
  getRuntimeState,
  heartbeatGrovePresence,
  isEditableTarget,
  openPadd,
  postGroveMessage,
  togglePadd,
  updateGardenDecoration,
  updateHomesteadSettings,
  updateProfileSettings,
} from './state.js';

const TAB_ORDER = ['seeds', 'library', 'quests', 'neighbors', 'profile'];
const TAB_LABELS = {
  seeds: 'Seeds',
  library: 'Library',
  quests: 'Quests',
  neighbors: 'Neighbors',
  profile: 'Profile',
};
const GROVE_POLL_MS = 5000;
const GROVE_HEARTBEAT_MS = 15000;

function escapeHtml(value) {
  return String(value || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

function badgeTotal(badges) {
  return Object.values(badges || {}).reduce((total, value) => total + Number(value || 0), 0);
}

class PaddController {
  constructor() {
    this.root = document.getElementById('game-ui-root');
    this.button = null;
    this.shell = null;
    this.panel = null;
    this.forceSetup = false;
    this.library = {
      view: 'recent',
      q: '',
      page: 1,
      payload: null,
      loading: false,
      error: '',
    };
    this.grove = {
      presences: [],
      messages: [],
      enabled: true,
      loading: false,
      error: '',
    };
    this._lastServer = null;
    this._lastGuest = null;
    this._lastMapId = '';
    this._lastPaddOpen = false;
    this._lastPaddTab = 'seeds';
    this._grovePollTimer = 0;
    this._groveHeartbeatTimer = 0;
  }

  init() {
    if (!this.root) return;
    this.button = document.createElement('button');
    this.button.type = 'button';
    this.button.className = 'gardn-padd-button';
    this.button.innerHTML = '<span>PADD</span><span class="gardn-padd-button-badge" hidden>0</span>';
    this.button.addEventListener('click', () => {
      if (!getRuntimeState().server) return;
      if (this.forceSetup) {
        openPadd('profile');
        return;
      }
      togglePadd();
    });

    this.shell = document.createElement('div');
    this.shell.className = 'gardn-padd-shell';
    this.shell.hidden = true;

    this.panel = document.createElement('section');
    this.panel.className = 'gardn-padd';
    this.panel.setAttribute('role', 'dialog');
    this.panel.setAttribute('aria-modal', 'true');

    this.shell.appendChild(this.panel);
    this.root.appendChild(this.button);
    this.root.appendChild(this.shell);

    window.addEventListener('gardn:state-change', this._handleStateChange);
    window.addEventListener('gardn:open-padd', this._handleOpenRequest);
    window.addEventListener('keydown', this._handleKeyDown);
    this._handleStateChange();
  }

  destroy() {
    window.removeEventListener('gardn:state-change', this._handleStateChange);
    window.removeEventListener('gardn:open-padd', this._handleOpenRequest);
    window.removeEventListener('keydown', this._handleKeyDown);
    window.clearInterval(this._grovePollTimer);
    window.clearInterval(this._groveHeartbeatTimer);
  }

  _handleOpenRequest = (event) => {
    const tab = event.detail?.tab || 'seeds';
    openPadd(tab);
  };

  _handleKeyDown = (event) => {
    const runtime = getRuntimeState();
    if (event.key === 'Tab') {
      if (isEditableTarget(event.target)) return;
      if (!runtime.server) return;
      event.preventDefault();
      if (this.forceSetup) {
        openPadd('profile');
        return;
      }
      togglePadd();
      return;
    }
    if (event.key === 'Escape' && runtime.ui.paddOpen && !this.forceSetup) {
      event.preventDefault();
      closePadd();
    }
  };

  _handleStateChange = () => {
    const runtime = getRuntimeState();
    const serverChanged = this._lastServer !== runtime.server;
    const guestChanged = this._lastGuest !== runtime.guestGarden;
    const mapChanged = this._lastMapId !== runtime.currentMapId;
    const uiChanged = this._lastPaddOpen !== runtime.ui.paddOpen || this._lastPaddTab !== runtime.ui.paddTab;

    this._lastServer = runtime.server;
    this._lastGuest = runtime.guestGarden;
    this._lastMapId = runtime.currentMapId;
    this._lastPaddOpen = runtime.ui.paddOpen;
    this._lastPaddTab = runtime.ui.paddTab;

    if (runtime.server && !runtime.server.appearance?.configured) {
      this.forceSetup = true;
      if (!runtime.ui.paddOpen || runtime.ui.paddTab !== 'profile') {
        openPadd('profile');
        return;
      }
    } else {
      this.forceSetup = false;
    }

    this._syncButtonBadge();
    if (mapChanged) this._syncGrovePolling();
    if (runtime.ui.paddOpen && runtime.ui.paddTab === 'library' && (!this.library.payload || serverChanged)) {
      void this._loadLibrary();
    }
    if (runtime.ui.paddOpen && runtime.ui.paddTab === 'neighbors') {
      void this._refreshGrove();
    }
    if (serverChanged || guestChanged || mapChanged || uiChanged) {
      this.render();
    }
  };

  _syncButtonBadge() {
    const badge = this.button?.querySelector('.gardn-padd-button-badge');
    if (!badge || !this.button) return;
    this.button.hidden = !getRuntimeState().server;
    const total = badgeTotal(getRuntimeState().server?.padd_badges);
    badge.hidden = total <= 0;
    badge.textContent = String(total);
  }

  _syncGrovePolling() {
    window.clearInterval(this._grovePollTimer);
    window.clearInterval(this._groveHeartbeatTimer);
    this._grovePollTimer = 0;
    this._groveHeartbeatTimer = 0;

    if (getRuntimeState().currentMapId !== 'neighbors') return;

    void this._refreshGrove({ heartbeat: true });
    this._groveHeartbeatTimer = window.setInterval(() => {
      void this._refreshGrove({ heartbeat: true });
    }, GROVE_HEARTBEAT_MS);
    this._grovePollTimer = window.setInterval(() => {
      void this._refreshGrove();
    }, GROVE_POLL_MS);
  }

  async _loadLibrary() {
    this.library.loading = true;
    this.library.error = '';
    this.render();
    try {
      this.library.payload = await fetchLibrary({
        view: this.library.view,
        q: this.library.q,
        page: this.library.page,
      });
    } catch (error) {
      this.library.error = error.message || 'Could not load the Link Library.';
    } finally {
      this.library.loading = false;
      this.render();
    }
  }

  async _refreshGrove({ heartbeat = false } = {}) {
    if (getRuntimeState().currentMapId !== 'neighbors') return;
    this.grove.loading = true;
    try {
      const [presencePayload, messagePayload] = await Promise.all([
        heartbeat ? heartbeatGrovePresence('neighbors') : fetchGrovePresence(),
        fetchGroveMessages(),
      ]);
      this.grove.presences = presencePayload.presences || [];
      this.grove.messages = messagePayload.messages || [];
      this.grove.enabled = messagePayload.enabled !== false;
      this.grove.error = '';
    } catch (error) {
      this.grove.error = error.message || 'Could not refresh the Neighbor Grove.';
    } finally {
      this.grove.loading = false;
      if (getRuntimeState().ui.paddOpen && getRuntimeState().ui.paddTab === 'neighbors') {
        this.render();
      }
    }
  }

  render() {
    if (!this.panel || !this.shell) return;
    const runtime = getRuntimeState();
    const visible = runtime.ui.paddOpen || this.forceSetup;
    this.shell.hidden = !visible;
    if (!visible) {
      this.panel.innerHTML = '';
      return;
    }

    const tab = runtime.ui.paddTab || 'seeds';
    const server = runtime.server || {};
    const title = this.forceSetup ? 'Calibrate Your Gardener' : 'PADD';

    this.panel.innerHTML = `
      <header class="gardn-padd-header">
        <div>
          <p class="gardn-padd-kicker">Pocket Archive and Discovery Device</p>
          <h2>${escapeHtml(title)}</h2>
        </div>
        <div class="gardn-padd-header-actions">
          ${this.forceSetup ? '<span class="gardn-padd-lock">Finish setup to begin</span>' : ''}
          ${this.forceSetup ? '' : '<button type="button" class="gardn-padd-close" data-action="close">Close</button>'}
        </div>
      </header>
      <nav class="gardn-padd-tabs" aria-label="PADD tabs">
        ${TAB_ORDER.map((key) => `
          <button
            type="button"
            class="gardn-padd-tab${tab === key ? ' is-active' : ''}"
            data-tab="${key}"
          >
            ${escapeHtml(TAB_LABELS[key])}
          </button>
        `).join('')}
      </nav>
      <section class="gardn-padd-body">
        ${this._renderTab(tab, server)}
      </section>
    `;

    this._bindPanelEvents(tab);
  }

  _renderTab(tab, server) {
    if (tab === 'library') return this._renderLibrary(server);
    if (tab === 'quests') return this._renderQuests(server);
    if (tab === 'neighbors') return this._renderNeighbors(server);
    if (tab === 'profile') return this._renderProfile(server);
    return this._renderSeeds(server);
  }

  _renderSeeds(server) {
    const verified = server.verified_inventory || [];
    const pending = server.pending_inventory || [];
    return `
      <div class="gardn-padd-grid">
        <section class="gardn-padd-card">
          <h3>Verified Seeds</h3>
          <p class="gardn-padd-subtle">These are ready to plant in your homestead.</p>
          ${verified.length ? verified.map((item) => `
            <article class="gardn-padd-item">
              <strong>${escapeHtml(item.title || item.canonical_url)}</strong>
              <span>${escapeHtml((item.kind || '').replaceAll('_', ' '))}</span>
              <a href="${escapeHtml(item.canonical_url || item.source_url || '#')}" target="_blank" rel="noopener">Open link</a>
            </article>
          `).join('') : '<p class="gardn-padd-empty">No verified seeds yet. Publish, scan, and come back.</p>'}
        </section>
        <section class="gardn-padd-card">
          <h3>Pending Proof</h3>
          <p class="gardn-padd-subtle">Fresh notes and bookmarks wait here until your site proves them.</p>
          ${pending.length ? pending.map((item) => `
            <article class="gardn-padd-item">
              <strong>${escapeHtml(item.title || item.canonical_url || 'Pending seed')}</strong>
              <span>${escapeHtml(item.source_url || item.canonical_url || '')}</span>
            </article>
          `).join('') : '<p class="gardn-padd-empty">No pending proof right now.</p>'}
        </section>
      </div>
    `;
  }

  _renderLibrary(server) {
    const payload = this.library.payload;
    const summary = payload?.summary || server.library_summary || {};
    const itemsHtml = payload?.items?.length ? payload.items.map((item) => `
      <article class="gardn-padd-item">
        <div>
          <strong>${escapeHtml(item.title || item.url)}</strong>
          <span>${escapeHtml((item.tags || []).join(', '))}</span>
        </div>
        <div class="gardn-padd-item-actions">
          <a href="${escapeHtml(item.url)}" target="_blank" rel="noopener">Open</a>
        </div>
      </article>
    `).join('') : '<p class="gardn-padd-empty">No harvests match this shelf yet.</p>';

    return `
      <section class="gardn-padd-card">
        <div class="gardn-padd-toolbar">
          <div class="gardn-padd-pill-group">
            ${['recent', 'all', 'read_later'].map((view) => `
              <button
                type="button"
                class="gardn-pill${this.library.view === view ? ' is-active' : ''}"
                data-library-view="${view}"
              >
                ${view === 'read_later' ? 'Read Later' : view[0].toUpperCase() + view.slice(1)}
              </button>
            `).join('')}
          </div>
          <form class="gardn-inline-form" data-library-search>
            <input type="search" name="q" value="${escapeHtml(this.library.q)}" placeholder="Search title, URL, note, or tag">
            <button type="submit">Search</button>
          </form>
        </div>
        <p class="gardn-padd-subtle">
          ${escapeHtml(summary.total_count || 0)} harvests total.
          Read-later tag: <code>${escapeHtml(summary.read_later_tag || 'read-later')}</code>
        </p>
        ${this.library.loading ? '<p class="gardn-padd-empty">Loading the shelves...</p>' : itemsHtml}
        ${this.library.error ? `<p class="gardn-padd-error">${escapeHtml(this.library.error)}</p>` : ''}
        <div class="gardn-padd-toolbar">
          <span class="gardn-padd-subtle">Page ${escapeHtml(payload?.page || 1)} of ${escapeHtml(payload?.total_pages || 1)}</span>
          <div class="gardn-padd-pill-group">
            <button type="button" class="gardn-pill" data-library-page="${Math.max(1, (payload?.page || 1) - 1)}">Prev</button>
            <button type="button" class="gardn-pill" data-library-page="${Math.min(payload?.total_pages || 1, (payload?.page || 1) + 1)}">Next</button>
          </div>
        </div>
      </section>
    `;
  }

  _renderQuests(server) {
    const quests = server.quests || [];
    return `
      <section class="gardn-padd-card">
        <h3>Quest Log</h3>
        <p class="gardn-padd-subtle">Short prompts to help your site and garden grow together.</p>
        ${quests.map((quest) => `
          <article class="gardn-padd-item">
            <div>
              <strong>${escapeHtml(quest.title)}</strong>
              <span>${escapeHtml(quest.description)}</span>
              <span>${escapeHtml(String(quest.progress))}/${escapeHtml(String(quest.target))} • ${escapeHtml(quest.status)}</span>
            </div>
            ${quest.status === 'claimable' ? `<button type="button" data-quest-claim="${escapeHtml(quest.slug)}">Claim</button>` : ''}
          </article>
        `).join('')}
      </section>
    `;
  }

  _renderNeighbors(server) {
    const neighbors = server.neighbors || [];
    const presenceHtml = this.grove.presences.length ? this.grove.presences.map((presence) => `
      <article class="gardn-padd-item">
        <div>
          <strong>${escapeHtml(presence.display_name)}</strong>
          <span>${escapeHtml(presence.garden_name || '')}</span>
        </div>
      </article>
    `).join('') : '<p class="gardn-padd-empty">No one is standing in the grove right now.</p>';
    const messageHtml = this.grove.messages.length ? this.grove.messages.map((message) => `
      <article class="gardn-chat-line">
        <strong>${escapeHtml(message.display_name)}:</strong>
        <span>${escapeHtml(message.content)}</span>
      </article>
    `).join('') : '<p class="gardn-padd-empty">The grove is quiet.</p>';
    return `
      <div class="gardn-padd-grid">
        <section class="gardn-padd-card">
          <h3>Neighbor Gates</h3>
          <p class="gardn-padd-subtle">Rooted links become paths. Open gates become visits.</p>
          ${neighbors.length ? neighbors.map((neighbor) => `
            <article class="gardn-padd-item">
              <div>
                <strong>${escapeHtml(neighbor.display_name || neighbor.target_url)}</strong>
                <span>${escapeHtml(neighbor.relationship.replaceAll('_', ' '))}</span>
              </div>
              <div class="gardn-padd-item-actions">
                ${neighbor.username ? `<a href="/game/gardens/${encodeURIComponent(neighbor.username)}/" target="_blank" rel="noopener">Open gate</a>` : ''}
                <a href="${escapeHtml(neighbor.target_url)}" target="_blank" rel="noopener">Site</a>
              </div>
            </article>
          `).join('') : '<p class="gardn-padd-empty">Find neighbors by linking out and rescanning your site.</p>'}
        </section>
        <section class="gardn-padd-card">
          <h3>Live Grove</h3>
          <p class="gardn-padd-subtle">Presence and public chat light up when you walk into Neighbor Grove.</p>
          ${getRuntimeState().currentMapId === 'neighbors' ? '' : '<p class="gardn-padd-empty">Walk into Neighbor Grove to send messages.</p>'}
          ${this.grove.error ? `<p class="gardn-padd-error">${escapeHtml(this.grove.error)}</p>` : ''}
          <div class="gardn-padd-split">
            <div>
              <h4>Present Now</h4>
              ${presenceHtml}
            </div>
            <div>
              <h4>Public Chat</h4>
              <div class="gardn-chat-log">${messageHtml}</div>
              ${this.grove.enabled ? `
                <form class="gardn-inline-form" data-grove-chat>
                  <input type="text" name="content" maxlength="280" placeholder="Say hello to the grove">
                  <button type="submit">Send</button>
                </form>
              ` : '<p class="gardn-padd-empty">Chat is disabled right now.</p>'}
            </div>
          </div>
        </section>
      </div>
    `;
  }

  _renderProfile(server) {
    const appearance = server.appearance || { options: { body_styles: [], skin_tones: [], outfits: [] } };
    const homestead = server.homestead || {};
    const shareUrl = server.owner?.garden_url || window.GAME_CONFIG.shareGardenUrl;
    const decorSlots = homestead.available_slots || [];
    const decorOptions = homestead.decor_options || [];
    const decorations = new Map((homestead.decorations || []).map((item) => [item.slot_key, item.decor_key]));
    return `
      <div class="gardn-padd-grid">
        <section class="gardn-padd-card">
          <h3>Avatar</h3>
          <p class="gardn-padd-subtle">Choose your launch-day look. More outfits can grow in later.</p>
          ${this.forceSetup ? '<p class="gardn-padd-callout">Pick a look before stepping fully into The Gardn.</p>' : ''}
          <form data-profile-form class="gardn-stacked-form">
            <label>
              Gender expression
              <select name="body_style">
                ${(appearance.options?.body_styles || []).map((option) => `
                  <option value="${escapeHtml(option.key)}" ${appearance.body_style === option.key ? 'selected' : ''}>
                    ${escapeHtml(option.label)}
                  </option>
                `).join('')}
              </select>
            </label>
            <label>
              Skin tone
              <select name="skin_tone">
                ${(appearance.options?.skin_tones || []).map((option) => `
                  <option value="${escapeHtml(option.key)}" ${appearance.skin_tone === option.key ? 'selected' : ''}>
                    ${escapeHtml(option.label)}
                  </option>
                `).join('')}
              </select>
            </label>
            <label>
              Starter outfit
              <select name="outfit_key">
                ${(appearance.options?.outfits || []).map((option) => `
                  <option value="${escapeHtml(option.key)}" ${appearance.outfit_key === option.key ? 'selected' : ''}>
                    ${escapeHtml(option.label)}
                  </option>
                `).join('')}
              </select>
            </label>
            <label>
              Read-later tag
              <input type="text" name="read_later_tag" value="${escapeHtml(homestead.read_later_tag || 'read-later')}">
            </label>
            <button type="submit">Save avatar + shelf</button>
          </form>
        </section>
        <section class="gardn-padd-card">
          <h3>Homestead</h3>
          <p class="gardn-padd-subtle">Level ${escapeHtml(homestead.homestead_level || 1)} homestead.</p>
          <form data-homestead-form class="gardn-stacked-form">
            <label>
              Garden name
              <input type="text" name="garden_name" maxlength="80" value="${escapeHtml(homestead.garden_name || server.owner?.garden_name || '')}">
            </label>
            <label>
              Gate
              <select name="gate_state">
                <option value="open" ${homestead.gate_state === 'open' ? 'selected' : ''}>Open to rooted neighbors</option>
                <option value="closed" ${homestead.gate_state === 'closed' ? 'selected' : ''}>Closed for quiet tending</option>
              </select>
            </label>
            <label>
              Path style
              <select name="path_style">
                ${(HOMESTEAD_PATH_OPTIONS(homestead)).map((option) => `
                  <option value="${escapeHtml(option.key)}" ${homestead.path_style === option.key ? 'selected' : ''} ${option.locked ? 'disabled' : ''}>
                    ${escapeHtml(option.label)}
                  </option>
                `).join('')}
              </select>
            </label>
            <label>
              Fence style
              <select name="fence_style">
                ${(HOMESTEAD_FENCE_OPTIONS(homestead)).map((option) => `
                  <option value="${escapeHtml(option.key)}" ${homestead.fence_style === option.key ? 'selected' : ''} ${option.locked ? 'disabled' : ''}>
                    ${escapeHtml(option.label)}
                  </option>
                `).join('')}
              </select>
            </label>
            <button type="submit">Save homestead</button>
          </form>
          <p class="gardn-padd-subtle">Share your homestead: <a href="${escapeHtml(shareUrl)}" target="_blank" rel="noopener">${escapeHtml(shareUrl)}</a></p>
        </section>
        <section class="gardn-padd-card gardn-padd-card--wide">
          <h3>Decor sockets</h3>
          <p class="gardn-padd-subtle">A small, anchored build system for launch. More expressive building can come later.</p>
          <div class="gardn-decor-grid">
            ${decorSlots.map((slot) => `
              <label>
                ${escapeHtml(slot.label)}
                <select data-decor-slot="${escapeHtml(slot.key)}">
                  <option value="">Empty</option>
                  ${decorOptions.map((option) => `
                    <option value="${escapeHtml(option.key)}" ${decorations.get(slot.key) === option.key ? 'selected' : ''}>
                      ${escapeHtml(option.label)}
                    </option>
                  `).join('')}
                </select>
              </label>
            `).join('')}
          </div>
        </section>
      </div>
    `;
  }

  _bindPanelEvents(tab) {
    this.panel.querySelector('[data-action="close"]')?.addEventListener('click', () => closePadd());
    this.panel.querySelectorAll('[data-tab]').forEach((button) => {
      button.addEventListener('click', () => openPadd(button.getAttribute('data-tab') || 'seeds'));
    });

    if (tab === 'library') {
      this.panel.querySelectorAll('[data-library-view]').forEach((button) => {
        button.addEventListener('click', () => {
          this.library.view = button.getAttribute('data-library-view') || 'recent';
          this.library.page = 1;
          void this._loadLibrary();
        });
      });
      this.panel.querySelector('[data-library-search]')?.addEventListener('submit', (event) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        this.library.q = String(form.get('q') || '').trim();
        this.library.page = 1;
        void this._loadLibrary();
      });
      this.panel.querySelectorAll('[data-library-page]').forEach((button) => {
        button.addEventListener('click', () => {
          this.library.page = Number(button.getAttribute('data-library-page') || '1');
          void this._loadLibrary();
        });
      });
    }

    if (tab === 'quests') {
      this.panel.querySelectorAll('[data-quest-claim]').forEach((button) => {
        button.addEventListener('click', async () => {
          button.disabled = true;
          try {
            await completeQuest(button.getAttribute('data-quest-claim') || '');
          } catch (error) {
            window.alert(error.message || 'Could not claim that quest yet.');
          } finally {
            button.disabled = false;
          }
        });
      });
    }

    if (tab === 'neighbors') {
      this.panel.querySelector('[data-grove-chat]')?.addEventListener('submit', async (event) => {
        event.preventDefault();
        const form = event.currentTarget;
        const data = new FormData(form);
        const content = String(data.get('content') || '').trim();
        if (!content) return;
        const input = form.querySelector('input[name="content"]');
        const button = form.querySelector('button[type="submit"]');
        if (button) button.disabled = true;
        try {
          const response = await postGroveMessage(content, getRuntimeState().currentMapId);
          this.grove.messages = response.messages || this.grove.messages;
          if (input) input.value = '';
          this.render();
        } catch (error) {
          window.alert(error.message || 'Could not send that message.');
        } finally {
          if (button) button.disabled = false;
        }
      });
    }

    if (tab === 'profile') {
      this.panel.querySelector('[data-profile-form]')?.addEventListener('submit', async (event) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        const submit = event.currentTarget.querySelector('button[type="submit"]');
        const readLaterTag = String(form.get('read_later_tag') || '').trim();
        if (!/^[a-z0-9_-]{1,64}$/.test(readLaterTag)) {
          window.alert('Read-later tag must be 1-64 characters using lowercase letters, numbers, hyphens, or underscores.');
          return;
        }
        if (submit) submit.disabled = true;
        try {
          await updateProfileSettings({
            body_style: form.get('body_style'),
            skin_tone: form.get('skin_tone'),
            outfit_key: form.get('outfit_key'),
            read_later_tag: readLaterTag,
            appearance_configured: true,
          });
          this.forceSetup = false;
        } catch (error) {
          window.alert(error.message || 'Could not save your profile.');
        } finally {
          if (submit) submit.disabled = false;
        }
      });

      this.panel.querySelector('[data-homestead-form]')?.addEventListener('submit', async (event) => {
        event.preventDefault();
        const form = new FormData(event.currentTarget);
        const submit = event.currentTarget.querySelector('button[type="submit"]');
        if (submit) submit.disabled = true;
        try {
          await updateHomesteadSettings({
            garden_name: form.get('garden_name'),
            gate_state: form.get('gate_state'),
            path_style: form.get('path_style'),
            fence_style: form.get('fence_style'),
          });
          window.dispatchEvent(new CustomEvent('gardn:homestead-updated'));
        } catch (error) {
          window.alert(error.message || 'Could not save your homestead.');
        } finally {
          if (submit) submit.disabled = false;
        }
      });

      this.panel.querySelectorAll('[data-decor-slot]').forEach((select) => {
        select.addEventListener('change', async () => {
          try {
            await updateGardenDecoration(select.getAttribute('data-decor-slot') || '', select.value);
            window.dispatchEvent(new CustomEvent('gardn:homestead-updated'));
          } catch (error) {
            window.alert(error.message || 'Could not update that decor slot.');
          }
        });
      });
    }
  }
}

function HOMESTEAD_PATH_OPTIONS(homestead) {
  return [
    { key: 'stone', label: 'Stone Path', locked: false },
    { key: 'clover', label: 'Clover Path', locked: Number(homestead.homestead_level || 1) < 2 },
    { key: 'sunbaked', label: 'Sunbaked Clay', locked: Number(homestead.homestead_level || 1) < 2 },
  ];
}

function HOMESTEAD_FENCE_OPTIONS(homestead) {
  return [
    { key: 'split_rail', label: 'Split Rail', locked: false },
    { key: 'hedge', label: 'Hedge Border', locked: Number(homestead.homestead_level || 1) < 2 },
    { key: 'woven', label: 'Woven Fence', locked: Number(homestead.homestead_level || 1) < 2 },
  ];
}

export function initPaddController() {
  const controller = new PaddController();
  controller.init();
  return controller;
}

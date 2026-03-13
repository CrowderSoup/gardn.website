import {
  getRuntimeState,
  plantVerifiedActivity,
  publishBookmark,
  publishNote,
  replaceInventory,
  runSiteScan,
  setUiState,
  updateGardenPlot,
} from '../state.js';

const ACTION_CELEBRATIONS = {
  note: {
    startToast: 'Publishing note to your site...',
    successToast: 'Note published. Scan when your site updates to verify the seed.',
    retryHint: 'Press N to try again.',
    startBurst: {
      label: 'Sending a new note seed...',
      primaryColor: 0xf4ba77,
      secondaryColor: 0xf5de92,
      textColor: '#fff2d7',
    },
    successBurst: {
      label: 'Note seed tucked away!',
      primaryColor: 0xf5de92,
      secondaryColor: 0x8fd4a1,
      textColor: '#f4ffdc',
    },
  },
  bookmark: {
    startToast: 'Publishing bookmark to your site...',
    successToast: 'Bookmark published. Scan your site when the permalink is live.',
    retryHint: 'Press B to try again.',
    startBurst: {
      label: 'Trellising a fresh bookmark...',
      primaryColor: 0x8dcde0,
      secondaryColor: 0xf5de92,
      textColor: '#ecfbff',
    },
    successBurst: {
      label: 'Bookmark vine is climbing!',
      primaryColor: 0xf5de92,
      secondaryColor: 0x90d8b7,
      textColor: '#f1ffe2',
    },
  },
};

export default class PlantScene extends Phaser.Scene {
  constructor() {
    super({ key: 'PlantScene' });
  }

  init(data) {
    this.mode = data.mode || 'plant';
    this.slotX = data.slotX ?? 0;
    this.slotY = data.slotY ?? 0;
    this.onPlanted = data.onPlanted || null;
    this.worldScene = data.worldScene || null;
    this._overlay = null;
    this._statusEl = null;
    this._focusTarget = null;
  }

  create() {
    const { width, height } = this.cameras.main;
    this.add.rectangle(width / 2, height / 2, width, height, 0x000000, 0.42);
    this._buildOverlay();
  }

  _buildOverlay() {
    const root = document.getElementById('game-ui-root') || document.body;
    const overlay = document.createElement('div');
    overlay.className = 'gardn-modal-backdrop';

    const box = document.createElement('div');
    box.className = 'gardn-modal';
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-modal', 'true');

    const title = document.createElement('h2');
    title.textContent = this._modalTitle();

    const description = document.createElement('p');
    description.className = 'gardn-modal-note';
    description.textContent = this._modalDescription();

    this._statusEl = document.createElement('div');
    this._statusEl.className = 'gardn-modal-status';

    box.appendChild(title);
    box.appendChild(description);
    box.appendChild(this._statusEl);

    if (this.mode === 'plant') {
      this._buildPlantForm(box);
    } else if (this.mode === 'note') {
      this._buildNoteForm(box);
    } else if (this.mode === 'bookmark') {
      this._buildBookmarkForm(box);
    } else if (this.mode === 'scan') {
      this._buildScanForm(box);
    }

    overlay.appendChild(box);
    root.appendChild(overlay);
    this._overlay = overlay;
    this._setHotkeysSuspended(true);

    box.addEventListener('keydown', this._stopKeyPropagation);

    overlay.addEventListener('click', (event) => {
      if (event.target === overlay) this._cancel();
    });
    document.addEventListener('keydown', this._onKeyDown);
    requestAnimationFrame(() => this._focusTarget?.focus?.());
  }

  _modalTitle() {
    if (this.mode === 'note') return 'Publish a note';
    if (this.mode === 'bookmark') return 'Publish a bookmark';
    if (this.mode === 'scan') return 'Scan your site';
    return 'Plant a verified seed';
  }

  _modalDescription() {
    if (this.mode === 'note') return 'Micropub can publish directly. The seed stays pending until your site scan confirms it.';
    if (this.mode === 'bookmark') return 'Bookmarking through Micropub creates a pending seed tied to a real URL on your site.';
    if (this.mode === 'scan') return 'Run a fresh scan to discover entries, bookmarks, endpoints, and neighbor links.';
    return 'Only verified entries and bookmarks can be planted. Pending actions must be scanned first.';
  }

  _buildPlantForm(box) {
    const runtime = getRuntimeState();
    const verifiedInventory = runtime.server?.verified_inventory || [];
    const pendingInventory = runtime.server?.pending_inventory || [];

    this._selectEl = document.createElement('select');
    this._selectEl.className = 'gardn-modal-field';
    this._focusTarget = this._selectEl;
    box.appendChild(this._selectEl);

    if (!verifiedInventory.length) {
      const opt = document.createElement('option');
      opt.textContent = 'No verified seeds yet';
      opt.disabled = true;
      opt.selected = true;
      this._selectEl.appendChild(opt);
      this._statusEl.textContent = pendingInventory.length
        ? 'You have pending seeds. Run a scan after your site updates.'
        : 'Publish to your site or use Micropub, then scan for proof.';
    } else {
      const placeholder = document.createElement('option');
      placeholder.textContent = 'Choose a verified seed';
      placeholder.value = '';
      placeholder.selected = true;
      this._selectEl.appendChild(placeholder);
      verifiedInventory.forEach((item) => {
        const opt = document.createElement('option');
        opt.value = item.id;
        opt.textContent = `${item.title || item.canonical_url} (${item.kind.replace('published_', '')})`;
        this._selectEl.appendChild(opt);
      });
    }

    if (pendingInventory.length) {
      const note = document.createElement('p');
      note.className = 'gardn-modal-note';
      note.textContent = `Pending: ${pendingInventory.length}. Press R or use the scan modal after your site updates.`;
      box.appendChild(note);
    }

    box.appendChild(this._actionRow([
      this._button('Cancel', 'btn-secondary', () => this._cancel()),
      this._button('Scan now', 'btn-secondary', () => this._submitScan()),
      this._button('Plant seed', 'btn', () => this._confirmPlant(), !verifiedInventory.length),
    ]));
  }

  _buildNoteForm(box) {
    this._titleInput = document.createElement('input');
    this._titleInput.placeholder = 'Optional title';

    this._contentInput = document.createElement('textarea');
    this._contentInput.rows = 5;
    this._contentInput.placeholder = 'Write a small note for your site...';
    this._focusTarget = this._contentInput;

    box.appendChild(this._titleInput);
    box.appendChild(this._contentInput);
    box.appendChild(this._actionRow([
      this._button('Cancel', 'btn-secondary', () => this._cancel()),
      this._button('Publish note', 'btn', () => this._confirmPublishNote()),
    ]));
  }

  _buildBookmarkForm(box) {
    this._targetUrlInput = document.createElement('input');
    this._targetUrlInput.type = 'url';
    this._targetUrlInput.placeholder = 'https://example.com/article';
    this._focusTarget = this._targetUrlInput;

    this._bookmarkTitleInput = document.createElement('input');
    this._bookmarkTitleInput.placeholder = 'Optional title';

    box.appendChild(this._targetUrlInput);
    box.appendChild(this._bookmarkTitleInput);
    box.appendChild(this._actionRow([
      this._button('Cancel', 'btn-secondary', () => this._cancel()),
      this._button('Publish bookmark', 'btn', () => this._confirmPublishBookmark()),
    ]));
  }

  _buildScanForm(box) {
    this._scanUrlInput = document.createElement('input');
    this._scanUrlInput.type = 'url';
    this._scanUrlInput.placeholder = 'Optional permalink, blogroll, or following page URL';
    this._scanUrlInput.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter') return;
      event.preventDefault();
      this._submitScan(this._scanUrlInput.value);
    });
    this._focusTarget = this._scanUrlInput;
    box.appendChild(this._scanUrlInput);

    const note = document.createElement('p');
    note.className = 'gardn-modal-note';
    note.textContent = 'Leave this empty for a home-page scan, or provide a specific page to look for a post, bookmark, or neighbor links.';
    box.appendChild(note);

    box.appendChild(this._actionRow([
      this._button('Cancel', 'btn-secondary', () => this._cancel()),
      this._button('Run scan', 'btn', () => this._submitScan(this._scanUrlInput.value)),
    ]));
  }

  _actionRow(buttons) {
    const row = document.createElement('div');
    row.className = 'gardn-modal-actions';
    buttons.forEach((button) => row.appendChild(button));
    return row;
  }

  _button(label, className, onClick, disabled = false) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = className;
    button.textContent = label;
    button.disabled = disabled;
    button.addEventListener('click', onClick);
    return button;
  }

  async _confirmPlant() {
    if (!this._selectEl?.value) {
      this._statusEl.textContent = 'Choose a verified seed first.';
      return;
    }

    try {
      const runtime = getRuntimeState();
      const selectedActivity = (runtime.server?.verified_inventory || []).find(
        (item) => item.id === Number(this._selectEl.value),
      );
      await plantVerifiedActivity(this.slotX, this.slotY, Number(this._selectEl.value));
      await this._scanNow();
      const plotData = {
        slot_x: this.slotX,
        slot_y: this.slotY,
        verified_activity_id: selectedActivity?.id || Number(this._selectEl.value),
        link_url: selectedActivity?.canonical_url || '',
        link_title: selectedActivity?.title || '',
        kind: selectedActivity?.kind || '',
        status: 'verified',
        plant_type: selectedActivity?.kind === 'published_bookmark' ? 'vine' : 'flower',
        growth_stage: 1,
      };
      updateGardenPlot(plotData);
      if (this.onPlanted) this.onPlanted(plotData);
      this._worldScene()?.syncRuntimeState({ rebuildGarden: true });
      this._removeOverlay();
      this.scene.stop('PlantScene');
    } catch (error) {
      this._statusEl.textContent = error.message || 'Could not plant the verified seed.';
    }
  }

  async _confirmPublishNote() {
    const content = this._contentInput?.value?.trim() || '';
    const title = this._titleInput?.value?.trim() || '';
    if (!content) {
      this._statusEl.textContent = 'Write a note first.';
      return;
    }
    await this._runJoyfulAction(ACTION_CELEBRATIONS.note, async () => {
      await publishNote(content, title);
      const inventoryResponse = await this._refreshInventory();
      replaceInventory(inventoryResponse);
    });
  }

  async _confirmPublishBookmark() {
    const targetUrl = this._targetUrlInput?.value?.trim() || '';
    const title = this._bookmarkTitleInput?.value?.trim() || '';
    if (!targetUrl) {
      this._statusEl.textContent = 'Enter a target URL first.';
      return;
    }
    await this._runJoyfulAction(ACTION_CELEBRATIONS.bookmark, async () => {
      await publishBookmark(targetUrl, title);
      const inventoryResponse = await this._refreshInventory();
      replaceInventory(inventoryResponse);
    });
  }

  async _refreshInventory() {
    const response = await fetch(window.GAME_CONFIG.harvestsUrl, { credentials: 'same-origin' });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || 'Could not refresh inventory');
    }
    return payload;
  }

  async _scanNow(pageUrl = '') {
    try {
      await runSiteScan(pageUrl);
      const inventoryResponse = await this._refreshInventory();
      replaceInventory(inventoryResponse);
      this._statusEl.textContent = 'Scan complete. Fresh proof is now in your inventory.';
    } catch (error) {
      this._statusEl.textContent = error.message || 'Scan failed.';
    }
  }

  async _submitScan(pageUrl = '') {
    const trimmedPageUrl = pageUrl?.trim?.() || '';
    const worldScene = this._worldScene();
    if (!worldScene) {
      try {
        await runSiteScan(trimmedPageUrl);
        const inventoryResponse = await this._refreshInventory();
        replaceInventory(inventoryResponse);
        this._cancel();
      } catch (error) {
        this._statusEl.textContent = error.message || 'Scan failed.';
      }
      return;
    }
    this._cancel();
    await worldScene.triggerScan(trimmedPageUrl, { allowWhileModalOpen: true });
  }

  async _runJoyfulAction(config, action) {
    this._cancel();
    this._worldScene()?.celebrateAction(config.startBurst);
    this._worldScene()?.showToast(config.startToast);
    try {
      await action();
      this._worldScene()?.syncRuntimeState();
      this._worldScene()?.celebrateAction(config.successBurst);
      this._worldScene()?.showToast(config.successToast);
    } catch (error) {
      const message = error.message || 'That action could not be completed.';
      this._worldScene()?.showToast(`${message} ${config.retryHint}`.trim(), '#ffd4a8');
    }
  }

  _worldScene() {
    return this.worldScene || window.game?.scene?.keys?.WorldScene || this.scene.manager?.keys?.WorldScene || null;
  }

  _setHotkeysSuspended(suspended) {
    setUiState({ hotkeysSuspended: suspended });
    const worldKeyboard = this._worldScene()?.input?.keyboard;
    if (worldKeyboard) worldKeyboard.enabled = !suspended;
    if (suspended) {
      this.input.keyboard?.disableGlobalCapture();
      return;
    }
    this.input.keyboard?.enableGlobalCapture();
  }

  _cancel() {
    this._removeOverlay();
    this.scene.stop('PlantScene');
  }

  _removeOverlay() {
    this._setHotkeysSuspended(false);
    document.removeEventListener('keydown', this._onKeyDown);
    if (this._overlay) {
      this._overlay.remove();
      this._overlay = null;
    }
  }

  shutdown() {
    this._removeOverlay();
  }

  _onKeyDown = (event) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      this._cancel();
    }
  };

  _stopKeyPropagation = (event) => {
    if (event.key !== 'Escape') event.stopPropagation();
  };
}

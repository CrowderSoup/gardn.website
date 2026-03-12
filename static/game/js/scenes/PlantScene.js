import {
  getRuntimeState,
  patchServerState,
  plantVerifiedActivity,
  publishBookmark,
  publishNote,
  replaceInventory,
  runSiteScan,
  updateGardenPlot,
} from '../state.js';

export default class PlantScene extends Phaser.Scene {
  constructor() {
    super({ key: 'PlantScene' });
  }

  init(data) {
    this.mode = data.mode || 'plant';
    this.slotX = data.slotX ?? 0;
    this.slotY = data.slotY ?? 0;
    this.onPlanted = data.onPlanted || null;
    this._overlay = null;
    this._statusEl = null;
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

    overlay.addEventListener('click', (event) => {
      if (event.target === overlay) this._cancel();
    });
    document.addEventListener('keydown', this._onKeyDown);
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
      this._button('Scan now', 'btn-secondary', () => this._scanNow()),
      this._button('Plant seed', 'btn', () => this._confirmPlant(), !verifiedInventory.length),
    ]));
  }

  _buildNoteForm(box) {
    this._titleInput = document.createElement('input');
    this._titleInput.placeholder = 'Optional title';

    this._contentInput = document.createElement('textarea');
    this._contentInput.rows = 5;
    this._contentInput.placeholder = 'Write a small note for your site...';

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
    this._scanUrlInput.placeholder = 'Optional blogroll/following page URL';
    box.appendChild(this._scanUrlInput);

    const note = document.createElement('p');
    note.className = 'gardn-modal-note';
    note.textContent = 'Leave this empty for a home-page scan, or provide a dedicated links page to look for neighbors.';
    box.appendChild(note);

    box.appendChild(this._actionRow([
      this._button('Cancel', 'btn-secondary', () => this._cancel()),
      this._button('Run scan', 'btn', () => this._scanNow(this._scanUrlInput.value)),
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
    try {
      await publishNote(content, title);
      this._statusEl.textContent = 'Published. Run a scan when your site updates to verify the seed.';
      const inventoryResponse = await this._refreshInventory();
      replaceInventory(inventoryResponse);
    } catch (error) {
      this._statusEl.textContent = error.message || 'Could not publish the note.';
    }
  }

  async _confirmPublishBookmark() {
    const targetUrl = this._targetUrlInput?.value?.trim() || '';
    const title = this._bookmarkTitleInput?.value?.trim() || '';
    if (!targetUrl) {
      this._statusEl.textContent = 'Enter a target URL first.';
      return;
    }
    try {
      await publishBookmark(targetUrl, title);
      this._statusEl.textContent = 'Bookmark published. Scan your site when the permalink is live.';
      const inventoryResponse = await this._refreshInventory();
      replaceInventory(inventoryResponse);
    } catch (error) {
      this._statusEl.textContent = error.message || 'Could not publish the bookmark.';
    }
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

  _cancel() {
    this._removeOverlay();
    this.scene.stop('PlantScene');
  }

  _removeOverlay() {
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
}

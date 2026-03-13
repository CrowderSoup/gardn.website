import {
  areHotkeysSuspended,
  clearGuestGarden,
  fetchGuestGarden,
  getRuntimeState,
  recordGardenVisit,
  refreshServerState,
  runSiteScan,
  setCurrentMapId,
  setPlayerSnapshot,
  setUiState,
  updateGardenPlot,
} from '../state.js';
import { GAME_HUD_LAYOUT, getGameplayViewport } from '../layout.js';

const TILE_SIZE = 32;
const PLAYER_SPEED = 160;
const WORLD_DIMENSIONS = {
  neighbors: { width: 832, height: 704 },
};
const NEIGHBOR_GRASS_FRAMES = [1, 4, 7, 10, 13, 16];
const PAVER_FRAMES = [190, 191, 192, 193, 194, 195, 196, 200];
const MAP_THEMES = {
  overworld: {
    label: 'Crossroads',
    background: '#284433',
    mist: 0x9fd3a8,
    glow: 0xf0c776,
    accent: 0x5f8f63,
  },
  garden: {
    label: 'Homestead Garden',
    background: '#355422',
    mist: 0xb4ddb1,
    glow: 0xf3d684,
    accent: 0x7aa95e,
  },
  guest_garden: {
    label: 'Guest Garden',
    background: '#314c2b',
    mist: 0xc0e0ba,
    glow: 0xf5df9f,
    accent: 0x8ab46a,
  },
  ruins: {
    label: 'Link Library',
    background: '#2c3341',
    mist: 0x8cb0cc,
    glow: 0xd8c783,
    accent: 0x6b7da0,
  },
  neighbors: {
    label: 'Neighbor Grove',
    background: '#24423f',
    mist: 0x9fd7ce,
    glow: 0xf5dda1,
    accent: 0x5f9a8c,
  },
};

const NPC_DATA = {
  elder_aldyn: {
    name: 'Elder Aldyn',
    sprite: 'npc-elder',
    cols: 24,
    dialog: [
      'The Gardn listens for proof, not promises.',
      'Write a little something on your own site. Scan it. Then let it bloom here.',
    ],
    tutorialDialog: {
      1: ['You have the road under your boots now.', 'If you need a starter plot on the web, I can point you toward one.'],
      5: ['Your homestead is awake.', 'Open your PADD with Tab if you want to tune your look before you keep going.'],
      6: ['The scan found real proof.', 'Walk to an empty bed and plant that seed.'],
      7: ['That is the rhythm of this place.', 'Publish, verify, plant, and let your garden tell the truth about your site.'],
    },
  },
  wanderer: {
    name: 'The Wanderer',
    sprite: 'npc-wanderer',
    dialog: [
      'A neighborhood is not a loot table.',
      'It forms when your links, rolls, and invitations become real paths.',
    ],
  },
  archivist: {
    name: 'The Archivist',
    sprite: 'npc-archivist',
    cols: 13,
    dialog: [
      'The library keeps what your site has already carried home.',
      'Open your PADD and I will show you the shelves.',
    ],
  },
};

export default class WorldScene extends Phaser.Scene {
  constructor() {
    super({ key: 'WorldScene' });
    this.gameState = null;
  }

  init(data) {
    this._initialMapId = data?.mapId || null;
    this.currentMapId = data?.mapId || 'overworld';
    this._spawnName = data?.spawnName || null;
    this._guestUsername = data?.guestUsername || '';
    this._queuedToast = '';
    this._transitioning = false;
    this._plotElements = [];
    this._customInteractives = [];
    this._inventoryPromotedListener = null;
    this._homesteadUpdatedListener = null;
  }

  async create() {
    setUiState({ mode: 'world' });
    try {
      this.gameState = await refreshServerState();
    } catch (_error) {
      this.gameState = {
        player: { tile_x: 10, tile_y: 10, tutorial_step: 0, has_website: false },
        verified_inventory: [],
        pending_inventory: [],
        neighbors: [],
      };
    }

    if (this.currentMapId === 'guest_garden' && this._guestUsername) {
      try {
        await fetchGuestGarden(this._guestUsername);
        const visitPayload = await recordGardenVisit(this._guestUsername);
        this._queuedToast = visitPayload.recorded
          ? 'Your visit added fresh pollination.'
          : 'You have already visited this garden today.';
      } catch (error) {
        clearGuestGarden();
        this._guestUsername = '';
        this.currentMapId = this.gameState.player.map_id || 'overworld';
        this._initialMapId = this.currentMapId;
        this._queuedToast = error.message || 'That garden is out of reach right now.';
      }
    } else {
      clearGuestGarden();
    }

    this.currentMapId = this._spawnName
      ? this.currentMapId
      : (this._initialMapId || this.gameState.player.map_id || this.currentMapId || 'overworld');
    setCurrentMapId(this.currentMapId);
    this._buildMap();
    this._buildAtmosphere();
    this._buildPlayer();
    this._buildNPCs();
    if (this.currentMapId === 'garden' || this.currentMapId === 'guest_garden') this._buildGardenPlots();
    this._buildPortals();
    this._buildInput();
    this._buildCamera();
    this._bindRuntimeListeners();

    if (this.player && this.npcs) this.physics.add.collider(this.player, this.npcs);
    if (this.player && this.portals) {
      this.physics.add.overlap(this.player, this.portals, (_player, portal) => {
        this._transitionTo(portal.targetMap, portal.targetSpawn);
      });
    }

    this._interactLabel = this.add.text(0, 0, '[E]', {
      fontFamily: 'monospace',
      fontSize: '9px',
      color: '#fff0a8',
    }).setOrigin(0.5, 1).setDepth(14).setVisible(false);

    this._worldLabel = this.add.text(18, 10, this._worldLabelText(), {
      fontFamily: 'monospace',
      fontSize: '10px',
      color: '#eaf4d8',
      backgroundColor: 'rgba(18, 31, 24, 0.65)',
      padding: { x: 6, y: 4 },
    }).setDepth(15).setScrollFactor(0);

    this.time.addEvent({
      delay: 30000,
      loop: true,
      callback: this.savePosition,
      callbackScope: this,
    });

    const step = this.gameState.player.tutorial_step;
    if (step < 9) {
      this.scene.launch('TutorialScene', { worldScene: this, gameState: this.gameState });
    }
    this._syncProgressHints();
    if (this._queuedToast) this._showToast(this._queuedToast);
  }

  _buildMap() {
    const TILESET_TEXTURE = {
      'lpc-base': 'tiles-lpc-base',
      'lpc-farming': 'tiles-lpc-farming',
      'lpc-crops': 'tiles-lpc-crops',
      'post-apoc-16': 'tiles-post-apoc',
    };
    const mapKey = this.currentMapId === 'guest_garden' ? 'map-garden' : `map-${this.currentMapId}`;

    if (this.currentMapId === 'neighbors') {
      this.map = null;
      const { width, height } = this._worldDimensions();
      this.physics.world.setBounds(0, 0, width, height);
      return;
    }

    try {
      this.map = this.make.tilemap({ key: mapKey });
      const tilesets = this.map.tilesets
        .map((tileset) => this.map.addTilesetImage(tileset.name, TILESET_TEXTURE[tileset.name] || 'tiles-lpc-base'))
        .filter(Boolean);
      if (tilesets.length) {
        this.groundLayer = this.map.createLayer('Ground', tilesets, 0, 0);
        this.aboveLayer = this.map.createLayer('Above Ground', tilesets, 0, 0);
        if (this.aboveLayer) this.aboveLayer.setDepth(12);
      }
      this.physics.world.setBounds(0, 0, this.map.widthInPixels, this.map.heightInPixels);
    } catch (_error) {
      this.map = null;
      this.physics.world.setBounds(0, 0, 640, 480);
    }
  }

  _worldDimensions() {
    const override = WORLD_DIMENSIONS[this.currentMapId];
    if (override) return override;
    if (this.map) {
      return {
        width: this.map.widthInPixels,
        height: this.map.heightInPixels,
      };
    }
    return { width: 640, height: 480 };
  }

  _buildAtmosphere() {
    const theme = MAP_THEMES[this.currentMapId] || MAP_THEMES.overworld;
    this.cameras.main.setBackgroundColor(theme.background);

    const { width: mapWidth, height: mapHeight } = this._worldDimensions();

    this.add.rectangle(mapWidth * 0.5, mapHeight * 0.5, mapWidth, mapHeight, theme.mist, 0.06).setDepth(-4);
    this.add.circle(mapWidth * 0.82, mapHeight * 0.16, 92, theme.glow, 0.08).setDepth(-3);

    if (this.currentMapId === 'garden' || this.currentMapId === 'guest_garden') {
      for (let row = 0; row < 8; row += 1) {
        this.add.rectangle(192, 84 + row * 32, 260, 22, 0x6b4b2d, 0.12).setDepth(-2);
      }
      this._drawGardenAtmosphere(mapWidth, mapHeight);
    }

    if (this.currentMapId === 'ruins') {
      for (let col = 0; col < 6; col += 1) {
        this.add.rectangle(70 + col * 90, 120 + (col % 2) * 30, 36, 72, 0x48556d, 0.18).setDepth(-2);
      }
      this._drawRuinsAtmosphere(mapWidth, mapHeight);
    }

    if (this.currentMapId === 'overworld') {
      this._drawOverworldAtmosphere(mapWidth, mapHeight);
    }

    if (this.currentMapId === 'neighbors') {
      const centerX = mapWidth / 2;
      const plazaY = 276;
      this._drawNeighborGround(mapWidth, mapHeight);
      this.add.rectangle(centerX, mapHeight - 106, 192, 236, 0x846d4f, 0.22).setDepth(-2.3);
      this.add.rectangle(centerX, mapHeight - 106, 140, 236, 0xd7c391, 0.1).setDepth(-2.2);
      this.add.circle(centerX, plazaY, 142, 0x13211d, 0.56).setDepth(-2);
      this.add.circle(centerX, plazaY, 116, 0x7d6b50, 0.24).setDepth(-1.9);
      this.add.circle(centerX, plazaY, 74, 0x9bcfc6, 0.14).setDepth(-1.8);
      this.add.circle(centerX, plazaY, 28, 0xf5dda1, 0.18).setDepth(-1.7);

      for (let step = 0; step < 7; step += 1) {
        this.add.circle(
          centerX + ((step % 2 === 0) ? -12 : 12),
          mapHeight - 164 - (step * 46),
          12 - Math.floor(step / 2),
          0xf2dfaf,
          0.28,
        ).setDepth(-1.6);
      }

      [
        { x: 136, y: 156, r: 42 },
        { x: 190, y: 414, r: 36 },
        { x: mapWidth - 136, y: 164, r: 42 },
        { x: mapWidth - 190, y: 428, r: 34 },
      ].forEach(({ x, y, r }) => {
        this.add.circle(x, y, r, 0x7bc6a0, 0.11).setDepth(-2.1);
        this.add.circle(x, y, r - 14, 0x14231d, 0.28).setDepth(-2);
      });

      this._drawNeighborProps(mapWidth, mapHeight);
    }
  }

  _drawNeighborGround(mapWidth, mapHeight) {
    const cols = Math.ceil(mapWidth / TILE_SIZE);
    const rows = Math.ceil(mapHeight / TILE_SIZE);
    for (let row = 0; row < rows; row += 1) {
      for (let col = 0; col < cols; col += 1) {
        const frame = NEIGHBOR_GRASS_FRAMES[(row + (col * 2)) % NEIGHBOR_GRASS_FRAMES.length];
        this.add.image((col * TILE_SIZE) + (TILE_SIZE / 2), (row * TILE_SIZE) + (TILE_SIZE / 2), 'tiles-lpc-base-sheet', frame)
          .setDepth(-6)
          .setAlpha(0.94);
      }
    }
  }

  _addSceneProp(x, y, texture, frame, {
    depth = 0,
    scale = 1,
    alpha = 1,
    originX = 0.5,
    originY = 0.5,
    tint = null,
  } = {}) {
    const image = this.add.image(x, y, texture, frame)
      .setDepth(depth)
      .setScale(scale)
      .setAlpha(alpha)
      .setOrigin(originX, originY);
    if (tint) image.setTint(tint);
    return image;
  }

  _stampPaverField(startX, startY, columns, rows, {
    depth = -1.15,
    alpha = 0.96,
    tint = null,
  } = {}) {
    const placed = [];
    for (let row = 0; row < rows; row += 1) {
      for (let col = 0; col < columns; col += 1) {
        const frame = PAVER_FRAMES[(row + (col * 3)) % PAVER_FRAMES.length];
        placed.push(this._addSceneProp(startX + (col * TILE_SIZE), startY + (row * TILE_SIZE), 'tiles-post-apoc-sheet', frame, {
          depth,
          scale: 2,
          alpha,
          tint,
        }));
      }
    }
    return placed;
  }

  _drawOverworldAtmosphere(mapWidth, mapHeight) {
    const centerX = mapWidth / 2;
    const centerY = mapHeight / 2;
    this._stampPaverField(centerX - 64, centerY - 64, 5, 5, { alpha: 0.92 });
    this._stampPaverField(centerX - 32, 32, 3, 7, { alpha: 0.9 });
    this._stampPaverField(centerX + 64, centerY - 32, 7, 3, { alpha: 0.9 });
    if ((this.gameState?.neighbors || []).length) {
      this._stampPaverField(32, 96, 6, 3, { alpha: 0.88 });
    }

    [
      { x: 112, y: 120, frame: 0 },
      { x: 124, y: 188, frame: 12 },
      { x: 136, y: 520, frame: 1 },
      { x: 526, y: 112, frame: 3 },
      { x: 512, y: 188, frame: 13 },
      { x: 498, y: 516, frame: 2 },
      { x: 286, y: 74, frame: 14 },
      { x: 404, y: 76, frame: 15 },
    ].forEach(({ x, y, frame }) => {
      this._addSceneProp(x, y, 'tiles-lpc-base-sheet', frame, {
        depth: -0.55,
        alpha: 0.94,
      });
    });

    [
      { x: centerX - 112, y: centerY - 146 },
      { x: centerX + 112, y: centerY - 146 },
      { x: centerX - 176, y: centerY + 102 },
      { x: centerX + 176, y: centerY + 102 },
    ].forEach(({ x, y }) => {
      this._addSceneProp(x, y, 'tiles-post-apoc-sheet', 200, {
        depth: 0.45,
        scale: 2,
        alpha: 0.86,
      });
      this._addSceneProp(x, y - 24, 'tiles-post-apoc-sheet', 220, {
        depth: 0.5,
        scale: 2,
        alpha: 0.84,
      });
    });
  }

  _drawRuinsAtmosphere(mapWidth, mapHeight) {
    const centerX = mapWidth / 2;
    this._stampPaverField(96, 288, 5, 3, { tint: 0xa3a8b4, alpha: 0.92 });
    this._stampPaverField(224, 224, 7, 6, { tint: 0xa3a8b4, alpha: 0.92 });
    this._stampPaverField(288, 128, 4, 3, { tint: 0xb6b0a1, alpha: 0.88 });

    [
      { x: 176, y: 184 },
      { x: 464, y: 184 },
      { x: 176, y: 448 },
      { x: 464, y: 448 },
    ].forEach(({ x, y }) => {
      this._addSceneProp(x, y, 'tiles-post-apoc-sheet', 200, {
        depth: 0.45,
        scale: 2,
        alpha: 0.88,
      });
      this._addSceneProp(x, y - 24, 'tiles-post-apoc-sheet', 220, {
        depth: 0.5,
        scale: 2,
        alpha: 0.86,
      });
    });

    [
      { x: centerX - 80, y: 176, frame: 34 },
      { x: centerX - 48, y: 176, frame: 35 },
      { x: centerX - 16, y: 176, frame: 36 },
      { x: centerX + 16, y: 176, frame: 37 },
      { x: centerX + 48, y: 176, frame: 38 },
      { x: centerX + 80, y: 176, frame: 39 },
      { x: 260, y: 400, frame: 26 },
      { x: 380, y: 400, frame: 27 },
    ].forEach(({ x, y, frame }) => {
      this._addSceneProp(x, y, 'tiles-lpc-farming-sheet', frame, {
        depth: 0.7,
        alpha: 0.9,
      });
    });

    [
      { x: 126, y: 146, frame: 17 },
      { x: 516, y: 148, frame: 18 },
      { x: 138, y: 514, frame: 16 },
      { x: 504, y: 508, frame: 15 },
    ].forEach(({ x, y, frame }) => {
      this._addSceneProp(x, y, 'tiles-lpc-base-sheet', frame, {
        depth: -0.45,
        alpha: 0.9,
      });
    });
  }

  _drawGardenAtmosphere(_mapWidth, mapHeight) {
    [
      { x: 84, y: 72, frame: 0 },
      { x: 428, y: 72, frame: 3 },
      { x: 76, y: 360, frame: 12 },
      { x: 436, y: 360, frame: 14 },
      { x: 94, y: mapHeight - 92, frame: 1 },
      { x: 420, y: mapHeight - 92, frame: 2 },
    ].forEach(({ x, y, frame }) => {
      this._addSceneProp(x, y, 'tiles-lpc-base-sheet', frame, {
        depth: -0.55,
        alpha: 0.94,
      });
    });

    [
      { x: 190, y: 382, frame: 294 },
      { x: 320, y: 382, frame: 295 },
      { x: 190, y: 420, frame: 342 },
      { x: 320, y: 420, frame: 343 },
    ].forEach(({ x, y, frame }) => {
      this._addSceneProp(x, y, 'tiles-lpc-crops-sheet', frame, {
        depth: 0.4,
        alpha: 0.9,
      });
    });
  }

  _drawNeighborProps(mapWidth, mapHeight) {
    const centerX = mapWidth / 2;
    const plazaY = 276;
    const entryY = mapHeight - 146;

    this._stampPaverField(centerX - 64, entryY - 144, 5, 6);
    this._stampPaverField(centerX - 96, plazaY - 96, 7, 6);
    this._drawNeighborGatePaths(mapWidth, mapHeight);
    this._drawNeighborGreenery(mapWidth, mapHeight);
    this._drawNeighborRuins(centerX, plazaY, mapHeight);
  }

  _drawNeighborGatePaths(mapWidth, mapHeight) {
    const centerX = mapWidth / 2;
    const laneY = mapHeight - 160;
    const slots = this._neighborGroveSlots(mapWidth, mapHeight);
    const anchorKeys = new Set();

    slots.forEach((slot) => {
      const key = `${slot.anchorX}:${slot.anchorY}`;
      if (anchorKeys.has(key)) return;
      anchorKeys.add(key);
      this._stampPaverField(slot.anchorX - 16, slot.anchorY - 16, 2, 2);
    });

    [
      { x: centerX - 16, y: laneY - 16, columns: 2, rows: 2 },
      { x: centerX - 16, y: laneY - 80, columns: 2, rows: 2 },
      { x: centerX - 16, y: laneY - 144, columns: 2, rows: 2 },
      { x: centerX - 16, y: laneY - 208, columns: 2, rows: 2 },
      { x: centerX - 16, y: laneY - 272, columns: 2, rows: 2 },
      { x: centerX - 16, y: laneY - 336, columns: 2, rows: 2 },
      { x: centerX - 80, y: 246, columns: 2, rows: 2 },
      { x: centerX + 16, y: 246, columns: 2, rows: 2 },
      { x: centerX - 144, y: 304, columns: 2, rows: 2 },
      { x: centerX + 80, y: 304, columns: 2, rows: 2 },
      { x: centerX - 176, y: 366, columns: 2, rows: 2 },
      { x: centerX + 112, y: 366, columns: 2, rows: 2 },
      { x: centerX - 160, y: 430, columns: 2, rows: 2 },
      { x: centerX + 96, y: 430, columns: 2, rows: 2 },
    ].forEach(({ x, y, columns, rows }) => {
      this._stampPaverField(x, y, columns, rows);
    });
  }

  _drawNeighborGreenery(mapWidth, mapHeight) {
    const edgeClusters = [
      { x: 76, y: 84, frame: 0, scale: 1 },
      { x: 116, y: 126, frame: 1, scale: 1 },
      { x: 98, y: 470, frame: 12, scale: 1 },
      { x: 140, y: 522, frame: 15, scale: 1 },
      { x: mapWidth - 76, y: 92, frame: 3, scale: 1 },
      { x: mapWidth - 118, y: 134, frame: 2, scale: 1 },
      { x: mapWidth - 102, y: 476, frame: 13, scale: 1 },
      { x: mapWidth - 144, y: 530, frame: 14, scale: 1 },
    ];
    edgeClusters.forEach(({ x, y, frame, scale }) => {
      this._addSceneProp(x, y, 'tiles-lpc-base-sheet', frame, {
        depth: -0.7,
        scale,
        alpha: 0.94,
      });
    });

    [
      { x: 166, y: 204, frame: 17 },
      { x: 190, y: 250, frame: 18 },
      { x: mapWidth - 164, y: 208, frame: 17 },
      { x: mapWidth - 188, y: 252, frame: 18 },
      { x: 180, y: mapHeight - 168, frame: 16 },
      { x: mapWidth - 178, y: mapHeight - 170, frame: 16 },
    ].forEach(({ x, y, frame }) => {
      this._addSceneProp(x, y, 'tiles-lpc-base-sheet', frame, {
        depth: -0.45,
        alpha: 0.9,
      });
    });
  }

  _drawNeighborRuins(centerX, plazaY, mapHeight) {
    [
      { x: centerX - 256, y: 206 },
      { x: centerX + 256, y: 206 },
      { x: centerX - 286, y: mapHeight - 208 },
      { x: centerX + 286, y: mapHeight - 208 },
    ].forEach(({ x, y }) => {
      this._addSceneProp(x, y, 'tiles-post-apoc-sheet', 200, {
        depth: 0.55,
        scale: 2,
        alpha: 0.92,
      });
      this._addSceneProp(x, y - 24, 'tiles-post-apoc-sheet', 220, {
        depth: 0.6,
        scale: 2,
        alpha: 0.9,
      });
    });

    [
      { x: centerX - 82, y: plazaY - 150, frame: 26 },
      { x: centerX + 82, y: plazaY - 150, frame: 27 },
      { x: centerX - 104, y: mapHeight - 140, frame: 60 },
      { x: centerX + 104, y: mapHeight - 140, frame: 63 },
    ].forEach(({ x, y, frame }) => {
      this._addSceneProp(x, y, 'tiles-lpc-farming-sheet', frame, {
        depth: 0.7,
        alpha: 0.92,
      });
    });
  }

  _buildPlayer() {
    let startX = (this.gameState.player.tile_x || 10) * TILE_SIZE + TILE_SIZE / 2;
    let startY = (this.gameState.player.tile_y || 10) * TILE_SIZE + TILE_SIZE / 2;

    if (this.map && this._spawnName) {
      const spawnLayer = this.map.getObjectLayer('Spawn');
      const spawnObj = spawnLayer?.objects.find((obj) => obj.name === this._spawnName);
      if (spawnObj) {
        startX = spawnObj.x + TILE_SIZE / 2;
        startY = spawnObj.y + TILE_SIZE / 2;
      }
    }

    const spawnOverride = this._spawnOverride();
    if (spawnOverride) {
      startX = spawnOverride.x;
      startY = spawnOverride.y;
    }

    const COLS = 13;
    const WALK_ROW_START = 8;
    const idleFrame = 10 * COLS;
    this.player = this.physics.add.sprite(startX, startY, 'player', idleFrame);
    this.player.setCollideWorldBounds(true);
    this.player.setDepth(6);
    ['up', 'left', 'down', 'right'].forEach((dir, index) => {
      const rowStart = (WALK_ROW_START + index) * COLS;
      if (!this.anims.exists(`walk-${dir}`)) {
        this.anims.create({
          key: `walk-${dir}`,
          frames: this.anims.generateFrameNumbers('player', { start: rowStart + 1, end: rowStart + 8 }),
          frameRate: 8,
          repeat: -1,
        });
      }
      if (!this.anims.exists(`idle-${dir}`)) {
        this.anims.create({
          key: `idle-${dir}`,
          frames: [{ key: 'player', frame: rowStart }],
          frameRate: 1,
        });
      }
    });

    this.player.tileX = Math.floor(startX / TILE_SIZE);
    this.player.tileY = Math.floor(startY / TILE_SIZE);
    this._facing = 'down';
    this._applyPlayerStyle();
    setPlayerSnapshot({ x: this.player.x, y: this.player.y, tileX: this.player.tileX, tileY: this.player.tileY, facing: this._facing });
  }

  _spawnOverride() {
    if (this.currentMapId !== 'neighbors' || this._spawnName !== 'player_start') return null;
    const { width: mapWidth, height: mapHeight } = this._worldDimensions();
    return {
      x: mapWidth / 2,
      y: mapHeight - 208,
    };
  }

  _applyPlayerStyle() {
    if (!this.player) return;
    const appearance = this.gameState?.appearance || {};
    const tone = {
      porcelain: 0xf3d9c6,
      sunset: 0xddb394,
      olive: 0xc09c75,
      amber: 0xa36b47,
      umbral: 0x714834,
    }[appearance.skin_tone] || 0xc09c75;
    const outfitTone = {
      starter: 0x7bb08a,
    }[appearance.outfit_key] || 0x7bb08a;
    const scale = {
      feminine: 0.97,
      androgynous: 1,
      masculine: 1.04,
    }[appearance.body_style] || 1;
    this.player.setTint(tone, tone, outfitTone, outfitTone);
    this.player.setScale(scale);
  }

  _buildNPCs() {
    this.npcs = this.physics.add.staticGroup();
    this._customInteractives = [];
    if (this.map) {
      const npcLayer = this.map.getObjectLayer('NPCs');
      npcLayer?.objects.forEach((obj) => {
        const npcId = obj.properties?.find((prop) => prop.name === 'npc_id')?.value || obj.name;
        const data = NPC_DATA[npcId];
        if (!data) return;
        const npcCols = data.cols || 13;
        const npc = this.npcs.create(obj.x + 16, obj.y + 16, data.sprite, 10 * npcCols);
        npc.setDepth(5);
        npc.body.setSize(20, 20);
        npc.body.setOffset(22, 36);
        npc.npcId = npcId;
        npc.npcData = data;
      });
    }

    if (this.currentMapId === 'neighbors') {
      this._buildNeighborNPCs();
    }
  }

  _buildNeighborNPCs() {
    const neighbors = this.gameState.neighbors || [];
    const { width: mapWidth, height: mapHeight } = this._worldDimensions();
    const sign = this.add.text(mapWidth / 2, 60, 'NEIGHBOR GROVE', {
      fontFamily: 'monospace',
      fontSize: '11px',
      color: '#f6f0c7',
      backgroundColor: 'rgba(13, 25, 20, 0.78)',
      padding: { x: 8, y: 4 },
    }).setOrigin(0.5).setDepth(5);
    const subtitle = this.add.text(mapWidth / 2, 84, neighbors.length
      ? 'A reclaimed square of rooted gates and quiet ruins.'
      : 'The ruins are waiting for your first rooted neighbor.', {
      fontFamily: 'monospace',
      fontSize: '8px',
      color: '#d9efe0',
      backgroundColor: 'rgba(13, 25, 20, 0.46)',
      padding: { x: 6, y: 3 },
    }).setOrigin(0.5).setDepth(5);
    this._plotElements.push(sign, subtitle);

    if (!neighbors.length) return;

    const slots = this._neighborGroveSlots(mapWidth, mapHeight);
    neighbors.slice(0, slots.length).forEach((neighbor, index) => {
      const slot = slots[index];
      const x = slot.x;
      const y = slot.y;
      const canVisit = Boolean(neighbor.visitable && neighbor.username);
      const displayName = neighbor.display_name || neighbor.username || neighbor.target_url || 'Neighbor';
      const relationshipLabel = (neighbor.relationship || 'neighbor link').replace(/_/g, ' ');
      const gateColor = canVisit ? 0x8bd7c2 : 0x6e7f79;
      const connectorLength = Phaser.Math.Distance.Between(slot.anchorX, slot.anchorY, x, y - 12);
      const connectorAngle = Phaser.Math.RadToDeg(Phaser.Math.Angle.Between(slot.anchorX, slot.anchorY, x, y - 12));
      const connector = this.add.rectangle(
        (slot.anchorX + x) / 2,
        (slot.anchorY + y - 12) / 2,
        connectorLength,
        16,
        canVisit ? 0x968a72 : 0x6f624e,
        canVisit ? 0.46 : 0.28,
      ).setDepth(1.2).setAngle(connectorAngle);
      connector.setStrokeStyle(1, canVisit ? 0xe3d8b4 : 0x8b7c63, canVisit ? 0.34 : 0.16);
      const gatePad = this.add.circle(x, y + 16, 26, 0x13211d, 0.62).setDepth(3.7);
      gatePad.setStrokeStyle(1, 0xdbc892, 0.18);
      const archLeft = this.add.rectangle(x - 11, y + 2, 6, 28, 0x2a362f, 0.96).setDepth(4.3);
      const archRight = this.add.rectangle(x + 11, y + 2, 6, 28, 0x2a362f, 0.96).setDepth(4.3);
      const gateLintel = this.add.arc(x, y - 11, 14, 14, 180, 360, false, 0x2a362f, 0.98).setDepth(4.35);
      const door = this.add.rectangle(x, y + 6, 18, 22, canVisit ? 0x18352d : 0x23302d, 0.96).setDepth(4.32);
      door.setStrokeStyle(2, gateColor, 0.9);
      const gateGlow = this.add.circle(x, y + 2, 24, gateColor, canVisit ? 0.14 : 0.06)
        .setDepth(4.1)
        .setBlendMode(Phaser.BlendModes.ADD);
      const lockSigil = canVisit
        ? this.add.circle(x, y + 4, 4, 0xf5dda1, 0.85).setDepth(4.5)
        : this.add.rectangle(x, y + 4, 8, 8, 0xcbbd8c, 0.84).setDepth(4.5).setAngle(45);
      const plaque = this.add.text(x, y + 40, displayName.slice(0, 12).toUpperCase(), {
        fontFamily: 'monospace',
        fontSize: '8px',
        color: canVisit ? '#eafff4' : '#c6d2cd',
        backgroundColor: 'rgba(10, 20, 16, 0.72)',
        padding: { x: 4, y: 2 },
      }).setOrigin(0.5).setDepth(5);
      const status = this.add.text(x, y + 54, canVisit ? 'ROOTED' : 'UNROOTED', {
        fontFamily: 'monospace',
        fontSize: '7px',
        color: canVisit ? '#b7f7de' : '#98aba4',
      }).setOrigin(0.5).setDepth(5);
      this._plotElements.push(
        connector,
        gatePad,
        archLeft,
        archRight,
        gateLintel,
        door,
        gateGlow,
        lockSigil,
        plaque,
        status,
      );

      this.tweens.add({
        targets: gateGlow,
        alpha: canVisit ? 0.32 : 0.14,
        scaleX: canVisit ? 1.08 : 1.03,
        scaleY: canVisit ? 1.08 : 1.03,
        duration: canVisit ? 780 : 980,
        yoyo: true,
        repeat: -1,
        ease: 'Sine.InOut',
      });

      this._customInteractives.push({
        x,
        y: y + 12,
        npcId: `neighbor-${neighbor.username || index}`,
        npcData: {
          name: displayName,
          dialog: canVisit
            ? [
              `${displayName}'s gate rooted itself through your ${relationshipLabel}.`,
              neighbor.target_url,
              `Step through and you can visit ${displayName}'s garden.`,
            ]
            : [
              `${displayName} is remembered through your ${relationshipLabel}.`,
              neighbor.target_url,
              'The path is marked, but the gate is still unrooted. Keep tending the relationship.',
            ],
          guestUsername: canVisit ? neighbor.username : '',
        },
      });
    });

    if (neighbors.length > slots.length) {
      const overflowCount = neighbors.length - slots.length;
      const overflow = this.add.text(mapWidth / 2, mapHeight - 154, `+${overflowCount} more paths will appear as the grove expands`, {
        fontFamily: 'monospace',
        fontSize: '8px',
        color: '#d6ead7',
        backgroundColor: 'rgba(13, 25, 20, 0.62)',
        padding: { x: 6, y: 3 },
      }).setOrigin(0.5).setDepth(5);
      this._plotElements.push(overflow);
    }
  }

  _neighborGroveSlots(mapWidth, mapHeight) {
    const centerX = mapWidth / 2;
    const laneX = centerX;
    return [
      { x: centerX - 224, y: 152, anchorX: laneX - 92, anchorY: 246 },
      { x: centerX - 112, y: 116, anchorX: laneX - 44, anchorY: 226 },
      { x: centerX + 112, y: 116, anchorX: laneX + 44, anchorY: 226 },
      { x: centerX + 224, y: 152, anchorX: laneX + 92, anchorY: 246 },
      { x: centerX - 312, y: 244, anchorX: laneX - 176, anchorY: 314 },
      { x: centerX - 176, y: 228, anchorX: laneX - 84, anchorY: 294 },
      { x: centerX + 176, y: 228, anchorX: laneX + 84, anchorY: 294 },
      { x: centerX + 312, y: 244, anchorX: laneX + 176, anchorY: 314 },
      { x: centerX - 320, y: 344, anchorX: laneX - 196, anchorY: 386 },
      { x: centerX - 192, y: 332, anchorX: laneX - 108, anchorY: 372 },
      { x: centerX + 192, y: 332, anchorX: laneX + 108, anchorY: 372 },
      { x: centerX + 320, y: 344, anchorX: laneX + 196, anchorY: 386 },
      { x: centerX - 304, y: 458, anchorX: laneX - 182, anchorY: 462 },
      { x: centerX - 176, y: 444, anchorX: laneX - 102, anchorY: 454 },
      { x: centerX + 176, y: 444, anchorX: laneX + 102, anchorY: 454 },
      { x: centerX + 304, y: 458, anchorX: laneX + 182, anchorY: 462 },
      { x: centerX - 232, y: mapHeight - 196, anchorX: laneX - 128, anchorY: mapHeight - 232 },
      { x: centerX - 120, y: mapHeight - 214, anchorX: laneX - 68, anchorY: mapHeight - 240 },
      { x: centerX + 120, y: mapHeight - 214, anchorX: laneX + 68, anchorY: mapHeight - 240 },
      { x: centerX + 232, y: mapHeight - 196, anchorX: laneX + 128, anchorY: mapHeight - 232 },
    ];
  }

  _portalDirection(x, y, width, height) {
    const { width: mapWidth, height: mapHeight } = this._worldDimensions();
    if (y <= TILE_SIZE / 2) return 'down';
    if (y + height >= mapHeight - TILE_SIZE / 2) return 'up';
    if (x <= TILE_SIZE / 2) return 'right';
    if (x + width >= mapWidth - TILE_SIZE / 2) return 'left';
    return height >= width ? 'up' : 'right';
  }

  _portalLabel(targetMap) {
    if (targetMap === 'guest_garden') return 'Guest Garden';
    return MAP_THEMES[targetMap]?.label || 'Unknown Path';
  }

  _createPortalChevron(x, y, direction, color) {
    let points = [-6, -6, -6, 6, 6, 0];
    if (direction === 'left') points = [6, -6, 6, 6, -6, 0];
    if (direction === 'up') points = [-6, 6, 6, 6, 0, -6];
    if (direction === 'down') points = [-6, -6, 6, -6, 0, 6];
    return this.add.triangle(x, y, ...points, color, 0.92)
      .setDepth(3)
      .setBlendMode(Phaser.BlendModes.ADD);
  }

  _drawPortalVisual(x, y, width, height, targetMap, color) {
    const centerX = x + (width / 2);
    const centerY = y + (height / 2);
    const direction = this._portalDirection(x, y, width, height);
    const label = this._portalLabel(targetMap).toUpperCase();
    const frame = this.add.rectangle(centerX, centerY, width + 14, height + 14, 0x08110e, 0.86)
      .setDepth(2.2);
    frame.setStrokeStyle(2, color, 0.95);

    const aura = this.add.rectangle(centerX, centerY, width + 22, height + 22, color, 0.1)
      .setDepth(1.9)
      .setBlendMode(Phaser.BlendModes.ADD);
    const surface = this.add.rectangle(
      centerX,
      centerY,
      Math.max(14, width - 4),
      Math.max(14, height - 4),
      color,
      0.28,
    ).setDepth(2.4).setBlendMode(Phaser.BlendModes.ADD);
    const core = this.add.rectangle(
      centerX,
      centerY,
      Math.max(8, width - 18),
      Math.max(8, height - 18),
      0xfff4bf,
      0.22,
    ).setDepth(2.5).setBlendMode(Phaser.BlendModes.ADD);

    this.tweens.add({
      targets: [aura, surface],
      alpha: { from: 0.16, to: 0.38 },
      duration: 840,
      yoyo: true,
      repeat: -1,
      ease: 'Sine.InOut',
    });
    this.tweens.add({
      targets: core,
      alpha: { from: 0.12, to: 0.34 },
      duration: 620,
      yoyo: true,
      repeat: -1,
      ease: 'Quad.InOut',
    });

    const directionOffsets = {
      up: { x: 0, y: -1 },
      down: { x: 0, y: 1 },
      left: { x: -1, y: 0 },
      right: { x: 1, y: 0 },
    };
    const offset = directionOffsets[direction] || directionOffsets.right;
    for (let index = 0; index < 3; index += 1) {
      const spacing = (index - 1) * 10;
      const chevron = this._createPortalChevron(
        centerX - (offset.x * spacing),
        centerY - (offset.y * spacing),
        direction,
        0xf9efb6,
      );
      this.tweens.add({
        targets: chevron,
        x: chevron.x + (offset.x * 10),
        y: chevron.y + (offset.y * 10),
        alpha: 0.18,
        duration: 700,
        delay: index * 120,
        yoyo: true,
        repeat: -1,
        ease: 'Sine.InOut',
      });
    }

    const labelYOffset = direction === 'down' ? (height / 2) + 16 : -((height / 2) + 16);
    this.add.text(centerX, centerY + labelYOffset, label, {
      fontFamily: 'monospace',
      fontSize: '8px',
      color: '#f2ffe2',
      backgroundColor: 'rgba(9, 20, 15, 0.8)',
      padding: { x: 4, y: 2 },
    }).setOrigin(0.5).setDepth(8);
  }

  _buildPortals() {
    this.portals = this.physics.add.staticGroup();
    const createPortal = (x, y, width, height, targetMap, targetSpawn, color = 0x73b8ff) => {
      const zone = this.add.zone(x + width / 2, y + height / 2, width, height);
      this.physics.world.enable(zone, Phaser.Physics.Arcade.STATIC_BODY);
      zone.targetMap = targetMap;
      zone.targetSpawn = targetSpawn || 'player_start';
      this.portals.add(zone);
      const portalColor = MAP_THEMES[targetMap]?.mist || MAP_THEMES[targetMap]?.glow || color;
      this._drawPortalVisual(x, y, width, height, targetMap, portalColor);
    };

    if (this.currentMapId === 'neighbors') {
      const { width: mapWidth, height: mapHeight } = this._worldDimensions();
      createPortal((mapWidth / 2) - 80, mapHeight - 112, 160, 64, 'overworld', 'player_start', 0x7be0c6);
      this.add.text(mapWidth / 2, mapHeight - 126, 'RETURN TO THE CROSSROADS', {
        fontFamily: 'monospace',
        fontSize: '8px',
        color: '#e7fae4',
        backgroundColor: 'rgba(9, 20, 15, 0.76)',
        padding: { x: 5, y: 3 },
      }).setOrigin(0.5).setDepth(8);
      return;
    }

    if (this.map && this.currentMapId !== 'guest_garden') {
      const portalLayer = this.map.getObjectLayer('Portals');
      portalLayer?.objects.forEach((obj) => {
        const targetMap = obj.properties?.find((prop) => prop.name === 'target_map')?.value;
        const targetSpawn = obj.properties?.find((prop) => prop.name === 'target_spawn')?.value || 'player_start';
        if (targetMap) createPortal(obj.x, obj.y, obj.width, obj.height, targetMap, targetSpawn);
      });
    }

    if (this.currentMapId === 'overworld' && (this.gameState.neighbors || []).length) {
      createPortal(0, 96, 32, 64, 'neighbors', 'player_start', 0x7be0c6);
    }
    if (this.currentMapId === 'guest_garden') {
      createPortal(304, 448, 32, 32, 'neighbors', 'player_start', 0x7be0c6);
    }
  }

  _buildInput() {
    this.cursors = this.input.keyboard.createCursorKeys();
    this.wasd = this.input.keyboard.addKeys({
      up: Phaser.Input.Keyboard.KeyCodes.W,
      down: Phaser.Input.Keyboard.KeyCodes.S,
      left: Phaser.Input.Keyboard.KeyCodes.A,
      right: Phaser.Input.Keyboard.KeyCodes.D,
    });

    this.input.keyboard.on('keydown-SPACE', (event) => {
      if (!this._canUseHotkey(event)) return;
      event.preventDefault();
      this._tryInteract();
    });
    this.input.keyboard.on('keydown-E', (event) => {
      if (!this._canUseHotkey(event)) return;
      this._tryInteract();
    });
    this.input.keyboard.on('keydown-N', (event) => {
      if (!this._canUseHotkey(event)) return;
      this._openActionModal('note');
    });
    this.input.keyboard.on('keydown-B', (event) => {
      if (!this._canUseHotkey(event)) return;
      this._openActionModal('bookmark');
    });
    this.input.keyboard.on('keydown-R', (event) => {
      if (!this._canUseHotkey(event)) return;
      if (event.shiftKey) {
        this._openActionModal('scan');
        return;
      }
      this._triggerScan();
    });
  }

  _buildCamera() {
    const { width: mapWidth, height: mapHeight } = this._worldDimensions();
    const layout = {
      ...GAME_HUD_LAYOUT,
      width: this.cameras.main.width,
      height: this.cameras.main.height,
    };
    const viewport = getGameplayViewport(layout);
    this.cameras.main.setViewport(viewport.x, viewport.y, viewport.width, viewport.height);
    this.cameras.main.setBounds(0, 0, mapWidth, mapHeight);
    this.cameras.main.startFollow(this.player, true, 0.09, 0.09);
  }

  _worldLabelText() {
    if (this.currentMapId === 'guest_garden') {
      const owner = this._activeGardenOwner();
      const homesteadName = getRuntimeState().guestGarden?.homestead?.garden_name;
      return homesteadName || `${owner?.display_name || owner?.username || 'Neighbor'}'s Garden`;
    }
    return MAP_THEMES[this.currentMapId]?.label || this.currentMapId;
  }

  _activeGardenOwner() {
    return getRuntimeState().guestGarden?.owner || this.gameState?.owner || null;
  }

  _activeGardenPlotsData() {
    return this.currentMapId === 'guest_garden'
      ? (getRuntimeState().guestGarden?.garden || [])
      : (this.gameState?.garden || []);
  }

  _activeHomestead() {
    return this.currentMapId === 'guest_garden'
      ? (getRuntimeState().guestGarden?.homestead || {})
      : (this.gameState?.homestead || {});
  }

  update() {
    const modalOpen = this.scene.isActive('DialogScene')
      || this.scene.isActive('PlantScene')
      || Boolean(getRuntimeState().ui?.paddOpen);
    if (this._transitioning || !this.player || !this.player.body || !this.cursors || modalOpen) {
      return;
    }

    const left = this.cursors.left.isDown || this.wasd.left.isDown;
    const right = this.cursors.right.isDown || this.wasd.right.isDown;
    const up = this.cursors.up.isDown || this.wasd.up.isDown;
    const down = this.cursors.down.isDown || this.wasd.down.isDown;

    this.player.setVelocity(0);
    if (left) {
      this.player.setVelocityX(-PLAYER_SPEED);
      this._facing = 'left';
    } else if (right) {
      this.player.setVelocityX(PLAYER_SPEED);
      this._facing = 'right';
    }
    if (up) {
      this.player.setVelocityY(-PLAYER_SPEED);
      this._facing = 'up';
    } else if (down) {
      this.player.setVelocityY(PLAYER_SPEED);
      this._facing = 'down';
    }

    const moving = left || right || up || down;
    if (moving) {
      this.player.anims.play(`walk-${this._facing}`, true);
    } else {
      this.player.anims.play(`idle-${this._facing}`, true);
    }

    this.player.tileX = Math.floor(this.player.x / TILE_SIZE);
    this.player.tileY = Math.floor(this.player.y / TILE_SIZE);
    setPlayerSnapshot({
      x: this.player.x,
      y: this.player.y,
      tileX: this.player.tileX,
      tileY: this.player.tileY,
      facing: this._facing,
    });
    this._updateInteractLabel();
  }

  _updateInteractLabel() {
    const targets = [...(this.npcs?.getChildren() || []), ...(this._customInteractives || [])];
    const reach = TILE_SIZE * 2;
    const px = this.player.x;
    const py = this.player.y;
    let nearest = null;
    let nearestDist = Infinity;
    targets.forEach((npc) => {
      const distance = Phaser.Math.Distance.Between(px, py, npc.x, npc.y);
      if (distance < reach && distance < nearestDist) {
        nearest = npc;
        nearestDist = distance;
      }
    });

    if (nearest) {
      this._interactLabel.setPosition(nearest.x, nearest.y - 20).setVisible(true);
      return;
    }
    this._interactLabel.setVisible(false);
  }

  _tryInteract() {
    const target = this._nearestNPC();
    if (target) {
      if (typeof target.onInteract === 'function') {
        target.onInteract();
        return;
      }
      this._openDialog(target);
      return;
    }

    if ((this.currentMapId === 'garden' || this.currentMapId === 'guest_garden') && this._gardenPlots) {
      const nearbyEmpty = this._gardenPlots.find((plot) => {
        if (plot.planted) return false;
        return Phaser.Math.Distance.Between(
          this.player.x,
          this.player.y,
          plot.wx + TILE_SIZE / 2,
          plot.wy + TILE_SIZE / 2,
        ) < TILE_SIZE * 1.5;
      });
      if (nearbyEmpty) {
        if (this.currentMapId === 'guest_garden') {
          this._showToast('This is a guest garden. Visits help it bloom, but only the owner can plant here.');
          return;
        }
        this._openActionModal('plant', {
          slotX: nearbyEmpty.gx,
          slotY: nearbyEmpty.gy,
          onPlanted: (plotData) => {
            nearbyEmpty.planted = true;
            this._drawPlant(nearbyEmpty.wx, nearbyEmpty.wy, plotData);
            updateGardenPlot(plotData);
            if ((this.gameState.player.tutorial_step || 0) === 6) this._advanceTutorialStep(7);
          },
        });
      }
    }
  }

  _nearestNPC() {
    const targets = [...(this.npcs?.getChildren() || []), ...(this._customInteractives || [])];
    const reach = TILE_SIZE * 2;
    let nearest = null;
    let nearestDist = Infinity;
    targets.forEach((npc) => {
      const distance = Phaser.Math.Distance.Between(this.player.x, this.player.y, npc.x, npc.y);
      if (distance < reach && distance < nearestDist) {
        nearest = npc;
        nearestDist = distance;
      }
    });
    return nearest;
  }

  _openDialog(target) {
    const step = this.gameState?.player?.tutorial_step || 0;
    const tutorialLines = target.npcData?.tutorialDialog?.[step];
    const lines = tutorialLines || target.npcData?.dialog || ['...'];
    const onClose = () => {
      if (target.npcId === 'elder_aldyn' && step === 1) this._advanceTutorialStep(2);
      if (target.npcId === 'wanderer' && step === 7 && (this.gameState.neighbors || []).length) this._advanceTutorialStep(8);
      if (target.npcId === 'archivist') {
        window.dispatchEvent(new CustomEvent('gardn:open-padd', { detail: { tab: 'library' } }));
      }
      if (target.npcId === 'wanderer' && this.currentMapId === 'neighbors') {
        window.dispatchEvent(new CustomEvent('gardn:open-padd', { detail: { tab: 'neighbors' } }));
      }
      if (target.npcData?.guestUsername) this._visitNeighborGarden(target.npcData.guestUsername);
    };
    this.scene.launch('DialogScene', {
      npcName: target.npcData.name,
      lines,
      worldScene: this,
      onClose,
    });
  }

  _visitNeighborGarden(username) {
    if (!username) return;
    this._transitionTo('guest_garden', 'player_start', { guestUsername: username });
  }

  _buildGardenPlots() {
    this._clearGardenElements();
    this._gardenPlots = [];
    const offsetX = 64;
    const offsetY = 64;
    const gridWidth = TILE_SIZE * 8;
    const gridHeight = TILE_SIZE * 8;
    this._drawHomesteadFrame(offsetX, offsetY, gridWidth, gridHeight);
    for (let gy = 0; gy < 8; gy += 1) {
      for (let gx = 0; gx < 8; gx += 1) {
        const wx = offsetX + gx * TILE_SIZE;
        const wy = offsetY + gy * TILE_SIZE;
        const rect = this.add.rectangle(wx + TILE_SIZE / 2, wy + TILE_SIZE / 2, TILE_SIZE - 2, TILE_SIZE - 2, 0x6a4628, 0.75);
        rect.setStrokeStyle(1, 0x51321a).setDepth(1);
        this._plotElements.push(rect);
        const planted = this._activeGardenPlotsData().find((plot) => plot.slot_x === gx && plot.slot_y === gy);
        if (planted) this._drawPlant(wx, wy, planted);
        this._gardenPlots.push({ gx, gy, wx, wy, planted: Boolean(planted) });
      }
    }
    this._drawGardenDecorations(offsetX, offsetY, gridWidth, gridHeight);
  }

  _clearGardenElements() {
    this._plotElements.forEach((element) => element.destroy());
    this._plotElements = [];
  }

  _drawHomesteadFrame(offsetX, offsetY, gridWidth, gridHeight) {
    const homestead = this._activeHomestead();
    const owner = this._activeGardenOwner();
    const pathColor = {
      stone: 0xb59e87,
      clover: 0x7b9563,
      sunbaked: 0xc69062,
    }[homestead.path_style] || 0xb59e87;
    const fenceColor = {
      split_rail: 0x7b5935,
      hedge: 0x477041,
      woven: 0x8d6848,
    }[homestead.fence_style] || 0x7b5935;

    const title = this.add.text(offsetX + (gridWidth / 2), offsetY - 26, homestead.garden_name || owner?.garden_name || 'Homestead Garden', {
      fontFamily: 'monospace',
      fontSize: '10px',
      color: '#f4f8dd',
      backgroundColor: 'rgba(17, 29, 22, 0.72)',
      padding: { x: 7, y: 4 },
    }).setOrigin(0.5).setDepth(4);
    this._plotElements.push(title);

    this._plotElements.push(
      ...this._stampPaverField(offsetX + (gridWidth / 2) - 48, offsetY + gridHeight - 24, 3, 2, {
        depth: 0.72,
        alpha: 0.9,
        tint: pathColor,
      }),
      ...this._stampPaverField(offsetX + (gridWidth / 2) - 32, offsetY + gridHeight + 8, 2, 4, {
        depth: 0.72,
        alpha: 0.92,
        tint: pathColor,
      }),
    );

    const walkway = this.add.rectangle(offsetX + (gridWidth / 2), offsetY + gridHeight + 18, gridWidth + 58, 24, pathColor, 0.26).setDepth(0.68);
    walkway.setStrokeStyle(1, 0xf4e0b5, 0.18);
    this._plotElements.push(walkway);

    const fenceSegments = [
      this.add.rectangle(offsetX + (gridWidth / 2), offsetY - 8, gridWidth + 20, 6, fenceColor, 0.9),
      this.add.rectangle(offsetX - 8, offsetY + (gridHeight / 2), 6, gridHeight + 18, fenceColor, 0.9),
      this.add.rectangle(offsetX + gridWidth + 8, offsetY + (gridHeight / 2), 6, gridHeight + 18, fenceColor, 0.9),
      this.add.rectangle(offsetX + (gridWidth / 2) - 66, offsetY + gridHeight + 2, (gridWidth / 2) - 36, 6, fenceColor, 0.9),
      this.add.rectangle(offsetX + (gridWidth / 2) + 66, offsetY + gridHeight + 2, (gridWidth / 2) - 36, 6, fenceColor, 0.9),
    ];
    fenceSegments.forEach((segment) => {
      segment.setDepth(1.1);
      this._plotElements.push(segment);
    });

    [
      { x: offsetX - 20, y: offsetY - 14, frame: 0 },
      { x: offsetX + gridWidth + 20, y: offsetY - 14, frame: 3 },
      { x: offsetX - 24, y: offsetY + gridHeight + 30, frame: 12 },
      { x: offsetX + gridWidth + 24, y: offsetY + gridHeight + 30, frame: 14 },
    ].forEach(({ x, y, frame }) => {
      this._plotElements.push(this._addSceneProp(x, y, 'tiles-lpc-base-sheet', frame, {
        depth: 1.25,
        alpha: 0.94,
      }));
    });
  }

  _drawGardenDecorations(offsetX, offsetY, gridWidth, gridHeight) {
    const homestead = this._activeHomestead();
    const owner = this._activeGardenOwner();
    const bySlot = new Map((homestead.decorations || []).map((decoration) => [decoration.slot_key, decoration]));
    const slotPositions = {
      north_west: { x: offsetX - 22, y: offsetY + 8 },
      north_east: { x: offsetX + gridWidth + 22, y: offsetY + 8 },
      south_west: { x: offsetX - 22, y: offsetY + gridHeight - 20 },
      south_east: { x: offsetX + gridWidth + 22, y: offsetY + gridHeight - 20 },
      signpost: { x: offsetX + gridWidth + 34, y: offsetY + gridHeight + 6 },
    };
    const drawDecoration = (slotKey, decoration) => {
      const position = slotPositions[slotKey];
      if (!position || !decoration) return;
      const key = decoration.decor_key;
      if (key === 'lantern' || key === 'stone_lantern') {
        const pole = this.add.rectangle(position.x, position.y, 6, 24, 0x6d573f, 1).setDepth(2.6);
        const glow = this.add.circle(position.x, position.y - 14, key === 'stone_lantern' ? 7 : 5, 0xf7dd9f, 0.28)
          .setDepth(2.8)
          .setBlendMode(Phaser.BlendModes.ADD);
        this._plotElements.push(pole, glow);
        return;
      }
      if (key === 'bench') {
        const bench = this.add.rectangle(position.x, position.y, 18, 8, 0x7b5935, 1).setDepth(2.5);
        this._plotElements.push(bench);
        return;
      }
      if (key === 'birdbath') {
        const bowl = this.add.circle(position.x, position.y - 6, 9, 0x8bb6c2, 0.68).setDepth(2.6);
        const stand = this.add.rectangle(position.x, position.y + 8, 4, 16, 0x8d8b84, 1).setDepth(2.5);
        this._plotElements.push(bowl, stand);
        return;
      }
      if (key === 'planter') {
        const box = this.add.rectangle(position.x, position.y + 6, 20, 12, 0x8a5d39, 1).setDepth(2.5);
        const bloom = this.add.circle(position.x, position.y - 2, 8, 0x8fd08d, 0.8).setDepth(2.6);
        this._plotElements.push(box, bloom);
        return;
      }
      if (key === 'trellis' || key === 'archway') {
        const frame = this.add.rectangle(position.x, position.y, 20, 32, 0x7d6147, 1).setDepth(2.5);
        frame.setStrokeStyle(2, 0xb8d39a, 0.45);
        this._plotElements.push(frame);
        return;
      }
      if (key === 'signpost') {
        const post = this.add.rectangle(position.x, position.y, 5, 28, 0x7c5f40, 1).setDepth(2.6);
        const sign = this.add.rectangle(position.x + 14, position.y - 8, 24, 14, 0xcfa86d, 0.96).setDepth(2.7);
        sign.setStrokeStyle(1, 0x6e4f2f, 0.9);
        const label = this.add.text(position.x + 14, position.y - 8, 'LINK', {
          fontFamily: 'monospace',
          fontSize: '7px',
          color: '#2e2417',
        }).setOrigin(0.5).setDepth(2.8);
        this._plotElements.push(post, sign, label);
        this._customInteractives.push({
          x: position.x + 14,
          y: position.y - 8,
          onInteract: () => {
            const link = owner?.garden_url || window.GAME_CONFIG.shareGardenUrl;
            window.open(link, '_blank', 'noopener');
            this._showToast('Opened this garden in a new tab.');
          },
        });
      }
    };

    ['north_west', 'north_east', 'south_west', 'south_east', 'signpost'].forEach((slotKey) => {
      drawDecoration(slotKey, bySlot.get(slotKey));
    });
  }

  _drawPlant(wx, wy, plotData) {
    const typeRows = { default: 0, herb: 1, flower: 2, vine: 3, tree: 4 };
    const frame = (typeRows[plotData.plant_type] || 0) * 32 + Math.min(plotData.growth_stage ?? 0, 4);
    const sprite = this.add.image(wx + TILE_SIZE / 2, wy + TILE_SIZE / 2, 'crop-sprites', frame).setDepth(3);
    this._plotElements.push(sprite);

    const label = this.add.text(wx + TILE_SIZE / 2, wy + 25, (plotData.link_title || 'seed').slice(0, 10), {
      fontFamily: 'monospace',
      fontSize: '7px',
      color: plotData.status === 'legacy' ? '#d0b68f' : '#d4ffd1',
    }).setOrigin(0.5).setDepth(4);
    this._plotElements.push(label);
  }

  _openActionModal(mode, data = {}) {
    if (this.scene.isActive('PlantScene')) return;
    this.scene.launch('PlantScene', { mode, worldScene: this, ...data });
  }

  _canUseHotkey(event) {
    if (areHotkeysSuspended(event)) return false;
    return !this.scene.isActive('DialogScene')
      && !this.scene.isActive('PlantScene')
      && !Boolean(getRuntimeState().ui?.paddOpen);
  }

  _bindRuntimeListeners() {
    if (this._inventoryPromotedListener) {
      window.removeEventListener('gardn:inventory-promoted', this._inventoryPromotedListener);
    }
    if (this._homesteadUpdatedListener) {
      window.removeEventListener('gardn:homestead-updated', this._homesteadUpdatedListener);
    }
    this._inventoryPromotedListener = (event) => {
      if (!this.scene.isActive('WorldScene')) return;
      const promotedCount = event.detail?.promotedCount || 0;
      if (!promotedCount) return;
      this.syncRuntimeState({ rebuildGarden: this.currentMapId === 'garden' });
      this.celebrateAction({
        label: promotedCount === 1 ? 'A waiting seed took root!' : `${promotedCount} waiting seeds took root!`,
        primaryColor: 0x93df95,
        secondaryColor: 0xf3d684,
        textColor: '#f5ffd9',
      });
      this._showToast(
        promotedCount === 1
          ? 'A pending verification bloomed into a seed.'
          : `${promotedCount} pending verifications bloomed into seeds.`,
      );
    };
    this._homesteadUpdatedListener = () => {
      if (!this.scene.isActive('WorldScene')) return;
      this.syncRuntimeState({
        rebuildGarden: this.currentMapId === 'garden' || this.currentMapId === 'guest_garden',
      });
      this._showToast('Homestead details updated.');
    };
    window.addEventListener('gardn:inventory-promoted', this._inventoryPromotedListener);
    window.addEventListener('gardn:homestead-updated', this._homesteadUpdatedListener);
  }

  syncRuntimeState({ rebuildGarden = false } = {}) {
    this.gameState = getRuntimeState().server || this.gameState;
    this._applyPlayerStyle();
    this._syncProgressHints();
    if (this._worldLabel) this._worldLabel.setText(this._worldLabelText());
    if (rebuildGarden && (this.currentMapId === 'garden' || this.currentMapId === 'guest_garden')) this._buildGardenPlots();
  }

  showToast(message, fill = '#eff9d7') {
    this._showToast(message, fill);
  }

  triggerScan(pageUrl = '', options = {}) {
    return this._triggerScan(pageUrl, options);
  }

  celebrateAction({
    label = '',
    primaryColor = 0xf3d684,
    secondaryColor = 0x9fd3a8,
    textColor = '#fff7cf',
  } = {}) {
    const centerX = this.cameras.main.width / 2;
    const centerY = this.cameras.main.height / 2 - 18;

    const flash = this.add.rectangle(
      centerX,
      centerY,
      this.cameras.main.width + 48,
      this.cameras.main.height + 48,
      secondaryColor,
      0.14,
    ).setDepth(21).setScrollFactor(0).setBlendMode(Phaser.BlendModes.ADD);

    const halo = this.add.circle(centerX, centerY, 18, primaryColor, 0.24)
      .setDepth(22)
      .setScrollFactor(0)
      .setBlendMode(Phaser.BlendModes.ADD);

    const core = this.add.circle(centerX, centerY, 6, 0xffffff, 0.92)
      .setDepth(23)
      .setScrollFactor(0)
      .setBlendMode(Phaser.BlendModes.ADD);

    this.tweens.add({
      targets: flash,
      alpha: 0,
      duration: 480,
      ease: 'Sine.Out',
      onComplete: () => flash.destroy(),
    });

    this.tweens.add({
      targets: halo,
      scale: 4.8,
      alpha: 0,
      duration: 760,
      ease: 'Cubic.Out',
      onComplete: () => halo.destroy(),
    });

    this.tweens.add({
      targets: core,
      scale: 0.3,
      alpha: 0,
      duration: 420,
      ease: 'Quad.In',
      onComplete: () => core.destroy(),
    });

    for (let index = 0; index < 12; index += 1) {
      const angle = Phaser.Math.DegToRad((360 / 12) * index + Phaser.Math.Between(-10, 10));
      const distance = Phaser.Math.Between(48, 116);
      const sparkle = this.add.circle(
        centerX,
        centerY,
        Phaser.Math.Between(3, 6),
        index % 2 === 0 ? primaryColor : secondaryColor,
        0.95,
      ).setDepth(23).setScrollFactor(0).setBlendMode(Phaser.BlendModes.ADD);

      this.tweens.add({
        targets: sparkle,
        x: centerX + Math.cos(angle) * distance,
        y: centerY + Math.sin(angle) * distance - Phaser.Math.Between(10, 32),
        alpha: 0,
        scale: Phaser.Math.FloatBetween(0.4, 1.6),
        duration: Phaser.Math.Between(620, 920),
        ease: 'Cubic.Out',
        onComplete: () => sparkle.destroy(),
      });
    }

    if (!label) return;
    const banner = this.add.text(centerX, centerY - 58, label, {
      fontFamily: 'monospace',
      fontSize: '12px',
      color: textColor,
      stroke: '#102018',
      strokeThickness: 4,
    }).setOrigin(0.5).setDepth(24).setScrollFactor(0);

    this.tweens.add({
      targets: banner,
      y: centerY - 88,
      alpha: 0,
      duration: 1300,
      ease: 'Sine.Out',
      onComplete: () => banner.destroy(),
    });
  }

  async _triggerScan(pageUrl = '', options = {}) {
    const { allowWhileModalOpen = false } = options;
    if (!allowWhileModalOpen && this.scene.isActive('PlantScene')) return;
    this.celebrateAction({
      label: 'Listening for fresh proof...',
      primaryColor: 0x8bd7c2,
      secondaryColor: 0xf3d684,
      textColor: '#eefee4',
    });
    this._showToast('Scanning your site...');
    try {
      await runSiteScan(pageUrl);
      this.syncRuntimeState({ rebuildGarden: true });
      this.celebrateAction({
        label: 'Fresh proof bloomed!',
        primaryColor: 0xf3d684,
        secondaryColor: 0x8bd7c2,
        textColor: '#fffad1',
      });
      this._showToast('Scan complete. Fresh proof is ready.');
    } catch (error) {
      this._showToast(error.message || 'Scan failed.', '#ffd4a8');
    }
  }

  _syncProgressHints() {
    const step = this.gameState?.player?.tutorial_step || 0;
    const verifiedSeeds = this.gameState?.verified_inventory?.length || 0;
    const neighbors = this.gameState?.neighbors?.length || 0;
    if (step === 5 && verifiedSeeds > 0) this._advanceTutorialStep(6);
    if (step === 7 && neighbors > 0) this._advanceTutorialStep(8);
  }

  _transitionTo(mapId, spawnName, extraData = {}) {
    if (this._transitioning) return;
    this._transitioning = true;
    const step = this.gameState?.player?.tutorial_step || 0;
    if (mapId === 'garden' && (step === 4 || (this.gameState?.player?.has_website && step === 3))) {
      this._advanceTutorialStep(5);
    }
    if (mapId === 'neighbors' && step === 7 && (this.gameState?.neighbors || []).length) {
      this._advanceTutorialStep(8);
    }
    if (mapId !== 'guest_garden') clearGuestGarden();
    setCurrentMapId(mapId);
    this.savePosition();
    this.scene.restart({ mapId, spawnName: spawnName || 'player_start', ...extraData });
  }

  _advanceTutorialStep(step) {
    if (step <= (this.gameState?.player?.tutorial_step || 0)) return;
    this.gameState.player.tutorial_step = step;
    fetch(window.GAME_CONFIG.tutorialUrl, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': window.GAME_CONFIG.csrfToken,
      },
      body: JSON.stringify({ step }),
    }).catch(() => {});
    if (this.scene.isActive('TutorialScene')) {
      this.scene.get('TutorialScene').advanceToStep(step);
    }
  }

  savePosition() {
    if (!this.player || this.currentMapId === 'guest_garden') return;
    fetch(window.GAME_CONFIG.saveUrl, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': window.GAME_CONFIG.csrfToken,
      },
      body: JSON.stringify({
        map_id: this.currentMapId,
        tile_x: this.player.tileX,
        tile_y: this.player.tileY,
      }),
    }).catch(() => {});
  }

  shutdown() {
    this.savePosition();
    if (this._inventoryPromotedListener) {
      window.removeEventListener('gardn:inventory-promoted', this._inventoryPromotedListener);
      this._inventoryPromotedListener = null;
    }
    if (this._homesteadUpdatedListener) {
      window.removeEventListener('gardn:homestead-updated', this._homesteadUpdatedListener);
      this._homesteadUpdatedListener = null;
    }
  }

  _showToast(message, fill = '#eff9d7') {
    if (this._toast) this._toast.destroy();
    this._toast = this.add.text(this.cameras.main.midPoint.x, this.cameras.main.height - 70, message, {
      fontFamily: 'monospace',
      fontSize: '11px',
      color: fill,
      backgroundColor: 'rgba(13, 24, 19, 0.78)',
      padding: { x: 8, y: 5 },
    }).setOrigin(0.5).setDepth(20).setScrollFactor(0);
    this.tweens.add({
      targets: this._toast,
      alpha: 0,
      duration: 1900,
      delay: 1200,
      onComplete: () => {
        this._toast?.destroy();
        this._toast = null;
      },
    });
  }
}

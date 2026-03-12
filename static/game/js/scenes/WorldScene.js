import {
  getRuntimeState,
  refreshServerState,
  runSiteScan,
  setCurrentMapId,
  setPlayerSnapshot,
  setUiState,
  toggleFullscreen,
  updateGardenPlot,
} from '../state.js';

const TILE_SIZE = 32;
const PLAYER_SPEED = 160;
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
      'A healthy garden starts with a healthy site.',
      'Publish something small. Then scan and let the proof take root.',
    ],
    tutorialDialog: {
      1: ['You made it. But you have no plot of land yet.', 'Let me help you claim one.'],
      5: ['Your homestead is ready.', 'Write on your site, then press R to scan the proof.'],
      6: ['The scan found a seed.', 'Walk to an empty plot and plant it.'],
      7: ['Good. A rooted post feeds the whole garden.', 'Keep publishing to water what you have planted.'],
    },
  },
  wanderer: {
    name: 'The Wanderer',
    sprite: 'npc-wanderer',
    dialog: [
      'Neighbors are not unlocked by grinding.',
      'They arrive when your blogroll, roll embed, or links make them real.',
    ],
  },
  archivist: {
    name: 'The Archivist',
    sprite: 'npc-archivist',
    cols: 13,
    dialog: [
      'The library remembers every format that still breathes.',
      'An h-entry with a real URL is stronger than any rumor.',
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
    this._transitioning = false;
    this._plotElements = [];
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

    this.currentMapId = this._spawnName
      ? this.currentMapId
      : (this._initialMapId || this.gameState.player.map_id || this.currentMapId || 'overworld');
    setCurrentMapId(this.currentMapId);
    this._buildMap();
    this._buildAtmosphere();
    this._buildPlayer();
    this._buildNPCs();
    this._buildEchoNodes();
    if (this.currentMapId === 'garden') this._buildGardenPlots();
    this._buildPortals();
    this._buildInput();
    this._buildCamera();

    if (this.player && this.npcs) this.physics.add.collider(this.player, this.npcs);
    if (this.player && this.echoNodes) this.physics.add.overlap(this.player, this.echoNodes, this._touchEchoNode, null, this);
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

    this._worldLabel = this.add.text(18, 46, MAP_THEMES[this.currentMapId]?.label || this.currentMapId, {
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
  }

  _buildMap() {
    const TILESET_TEXTURE = {
      'lpc-base': 'tiles-lpc-base',
      'lpc-farming': 'tiles-lpc-farming',
      'lpc-crops': 'tiles-lpc-crops',
      'post-apoc-16': 'tiles-post-apoc',
    };

    try {
      this.map = this.make.tilemap({ key: `map-${this.currentMapId}` });
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

  _buildAtmosphere() {
    const theme = MAP_THEMES[this.currentMapId] || MAP_THEMES.overworld;
    this.cameras.main.setBackgroundColor(theme.background);

    const mapWidth = this.map ? this.map.widthInPixels : 640;
    const mapHeight = this.map ? this.map.heightInPixels : 480;

    this.add.rectangle(mapWidth * 0.5, mapHeight * 0.5, mapWidth, mapHeight, theme.mist, 0.06).setDepth(-4);
    this.add.circle(mapWidth * 0.82, mapHeight * 0.16, 92, theme.glow, 0.08).setDepth(-3);

    if (this.currentMapId === 'garden') {
      for (let row = 0; row < 8; row += 1) {
        this.add.rectangle(192, 84 + row * 32, 260, 22, 0x6b4b2d, 0.12).setDepth(-2);
      }
    }

    if (this.currentMapId === 'ruins') {
      for (let col = 0; col < 6; col += 1) {
        this.add.rectangle(70 + col * 90, 120 + (col % 2) * 30, 36, 72, 0x48556d, 0.18).setDepth(-2);
      }
    }

    if (this.currentMapId === 'neighbors') {
      for (let i = 0; i < 5; i += 1) {
        this.add.circle(96 + i * 88, 86 + (i % 2) * 28, 24, 0x7bc6a0, 0.12).setDepth(-2);
      }
    }
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

    this.player.tileX = this.gameState.player.tile_x || 10;
    this.player.tileY = this.gameState.player.tile_y || 10;
    this._facing = 'down';
    setPlayerSnapshot({ x: this.player.x, y: this.player.y, tileX: this.player.tileX, tileY: this.player.tileY, facing: this._facing });
  }

  _buildNPCs() {
    this.npcs = this.physics.add.staticGroup();
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
    const positions = [
      { x: 128, y: 160 },
      { x: 224, y: 128 },
      { x: 320, y: 176 },
      { x: 416, y: 132 },
    ];
    neighbors.slice(0, positions.length).forEach((neighbor, index) => {
      const pos = positions[index];
      const npc = this.npcs.create(pos.x, pos.y, 'npc-archivist', 130);
      npc.setDepth(5);
      npc.body.setSize(20, 20);
      npc.body.setOffset(22, 36);
      npc.npcId = `neighbor-${neighbor.username || index}`;
      npc.npcData = {
        name: neighbor.display_name || neighbor.username || 'Neighbor',
        dialog: [
          `${neighbor.display_name || neighbor.username || 'This garden'} was discovered through your ${neighbor.relationship.replace('_', ' ')}.`,
          neighbor.target_url,
        ],
      };
    });
  }

  _buildEchoNodes() {
    this.echoNodes = this.physics.add.staticGroup();
    if (!this.map) return;
    const linksLayer = this.map.getObjectLayer('Links');
    if (!linksLayer) return;

    if (!this.textures.exists('echo-node')) {
      const graphics = this.make.graphics({ add: false });
      graphics.fillStyle(0xf2d17f, 1);
      graphics.fillRoundedRect(0, 0, 16, 16, 4);
      graphics.lineStyle(2, 0xfff0be, 0.9);
      graphics.strokeRoundedRect(1, 1, 14, 14, 4);
      graphics.generateTexture('echo-node', 16, 16);
      graphics.destroy();
    }

    linksLayer.objects.forEach((obj) => {
      const node = this.echoNodes.create(obj.x + 8, obj.y + 8, 'echo-node');
      node.setDepth(4);
      node._touched = false;
      this.tweens.add({
        targets: node,
        alpha: 0.45,
        duration: 850,
        yoyo: true,
        repeat: -1,
      });
    });
  }

  _touchEchoNode(_player, node) {
    if (node._touched) return;
    node._touched = true;
    const messages = {
      overworld: 'Echoes only become seeds when your site confirms them.',
      ruins: 'The library knows markup. h-entry URLs make the strongest roots.',
      garden: 'A waiting plot has room for your next verified post.',
      neighbors: 'Neighbor links become real when your blogroll or roll embed says so.',
    };
    this._showToast(messages[this.currentMapId] || 'Your site is the source of truth.');
  }

  _buildPortals() {
    this.portals = this.physics.add.staticGroup();
    const createPortal = (x, y, width, height, targetMap, targetSpawn, color = 0x73b8ff) => {
      const zone = this.add.zone(x + width / 2, y + height / 2, width, height);
      this.physics.world.enable(zone, Phaser.Physics.Arcade.STATIC_BODY);
      zone.targetMap = targetMap;
      zone.targetSpawn = targetSpawn || 'player_start';
      this.portals.add(zone);
      this.add.rectangle(x + width / 2, y + height / 2, width, height, color, 0.18).setDepth(2);
    };

    if (this.map) {
      const portalLayer = this.map.getObjectLayer('Portals');
      portalLayer?.objects.forEach((obj) => {
        const targetMap = obj.properties?.find((prop) => prop.name === 'target_map')?.value;
        const targetSpawn = obj.properties?.find((prop) => prop.name === 'target_spawn')?.value || 'player_start';
        if (targetMap) createPortal(obj.x, obj.y, obj.width, obj.height, targetMap, targetSpawn);
      });
    }

    if (this.currentMapId === 'overworld' && (this.gameState.neighbors || []).length) {
      createPortal(0, 96, 32, 64, 'neighbors', 'player_start', 0x7be0c6);
      this.add.text(18, 76, 'Neighbor Grove', {
        fontFamily: 'monospace',
        fontSize: '8px',
        color: '#ddfff0',
      }).setOrigin(0.5).setDepth(8);
    }
    if (this.currentMapId === 'neighbors') {
      createPortal(304, 448, 32, 32, 'overworld', 'player_start', 0x7be0c6);
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

    this.input.keyboard.on('keydown-SPACE', () => this._tryInteract());
    this.input.keyboard.on('keydown-E', () => this._tryInteract());
    this.input.keyboard.on('keydown-N', () => this._openActionModal('note'));
    this.input.keyboard.on('keydown-B', () => this._openActionModal('bookmark'));
    this.input.keyboard.on('keydown-R', (event) => {
      if (event.shiftKey) {
        this._openActionModal('scan');
        return;
      }
      this._triggerScan();
    });
    this.input.keyboard.on('keydown-F', () => toggleFullscreen());
  }

  _buildCamera() {
    const mapWidth = this.map ? this.map.widthInPixels : 640;
    const mapHeight = this.map ? this.map.heightInPixels : 480;
    this.cameras.main.setBounds(0, 0, mapWidth, mapHeight);
    this.cameras.main.startFollow(this.player, true, 0.09, 0.09);
  }

  update() {
    const modalOpen = this.scene.isActive('DialogScene') || this.scene.isActive('PlantScene');
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
    const targets = this.npcs?.getChildren() || [];
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
      this._openDialog(target);
      return;
    }

    if (this.currentMapId === 'garden' && this._gardenPlots) {
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
    const targets = this.npcs?.getChildren() || [];
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
    };
    this.scene.launch('DialogScene', {
      npcName: target.npcData.name,
      lines,
      worldScene: this,
      onClose,
    });
  }

  _buildGardenPlots() {
    this._clearGardenElements();
    this._gardenPlots = [];
    const offsetX = 64;
    const offsetY = 64;
    for (let gy = 0; gy < 8; gy += 1) {
      for (let gx = 0; gx < 8; gx += 1) {
        const wx = offsetX + gx * TILE_SIZE;
        const wy = offsetY + gy * TILE_SIZE;
        const rect = this.add.rectangle(wx + TILE_SIZE / 2, wy + TILE_SIZE / 2, TILE_SIZE - 2, TILE_SIZE - 2, 0x6a4628, 0.75);
        rect.setStrokeStyle(1, 0x51321a).setDepth(1);
        this._plotElements.push(rect);
        const planted = this.gameState?.garden?.find((plot) => plot.slot_x === gx && plot.slot_y === gy);
        if (planted) this._drawPlant(wx, wy, planted);
        this._gardenPlots.push({ gx, gy, wx, wy, planted: Boolean(planted) });
      }
    }
  }

  _clearGardenElements() {
    this._plotElements.forEach((element) => element.destroy());
    this._plotElements = [];
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
    this.scene.launch('PlantScene', { mode, ...data });
  }

  async _triggerScan(pageUrl = '') {
    if (this.scene.isActive('PlantScene')) return;
    this._showToast('Scanning your site...');
    try {
      await runSiteScan(pageUrl);
      this.gameState = getRuntimeState().server || this.gameState;
      this._syncProgressHints();
      if (this.currentMapId === 'garden') this._buildGardenPlots();
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

  _transitionTo(mapId, spawnName) {
    if (this._transitioning) return;
    this._transitioning = true;
    const step = this.gameState?.player?.tutorial_step || 0;
    if (mapId === 'garden' && (step === 4 || (this.gameState?.player?.has_website && step === 3))) {
      this._advanceTutorialStep(5);
    }
    if (mapId === 'neighbors' && step === 7 && (this.gameState?.neighbors || []).length) {
      this._advanceTutorialStep(8);
    }
    setCurrentMapId(mapId);
    this.savePosition();
    this.scene.restart({ mapId, spawnName: spawnName || 'player_start' });
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
    if (!this.player) return;
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

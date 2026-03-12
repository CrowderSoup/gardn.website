export default class BootScene extends Phaser.Scene {
  constructor() {
    super({ key: 'BootScene' });
  }

  preload() {
    const base = window.GAME_CONFIG.staticRoot + 'assets/';

    // Tilesets
    this.load.image('tiles-lpc-base', base + 'tilesets/lpc-base.png');
    this.load.image('tiles-lpc-farming', base + 'tilesets/lpc-farming.png');
    this.load.image('tiles-lpc-crops', base + 'tilesets/lpc-crops.png');
    this.load.image('tiles-post-apoc', base + 'tilesets/post-apoc-16.png');

    // Maps
    this.load.tilemapTiledJSON('map-overworld', base + 'maps/overworld.json');
    this.load.tilemapTiledJSON('map-garden', base + 'maps/garden.json');
    this.load.tilemapTiledJSON('map-ruins', base + 'maps/ruins.json');
    this.load.tilemapTiledJSON('map-neighbors', base + 'maps/neighbors.json');

    // Sprites
    this.load.spritesheet('player', base + 'sprites/player.png', {
      frameWidth: 64,
      frameHeight: 64,
    });
    this.load.spritesheet('npc-elder', base + 'sprites/npcs/elder.png', {
      frameWidth: 64,
      frameHeight: 64,
    });
    this.load.spritesheet('npc-wanderer', base + 'sprites/npcs/wanderer.png', {
      frameWidth: 64,
      frameHeight: 64,
    });
    this.load.spritesheet('npc-archivist', base + 'sprites/npcs/archivist.png', {
      frameWidth: 64,
      frameHeight: 64,
    });
    this.load.spritesheet('crop-sprites', base + 'tilesets/lpc-crops.png', {
      frameWidth: 32,
      frameHeight: 32,
    });

    // Loading bar
    const { width, height } = this.cameras.main;
    const bar = this.add.graphics();
    this.load.on('progress', (value) => {
      bar.clear();
      bar.fillStyle(0x4a7c59, 1);
      bar.fillRect(width * 0.1, height * 0.5 - 10, (width * 0.8) * value, 20);
    });
    this.load.on('complete', () => bar.destroy());
  }

  create() {
    // Generate placeholder tile textures for any tileset images that failed to load
    // (real assets should be downloaded to static/game/assets/tilesets/)
    const MISSING_KEY = '__MISSING';
    const tileConfigs = [
      { key: 'tiles-lpc-base',     color: 0x3d6b3d, size: 32 },
      { key: 'tiles-lpc-farming',  color: 0x5a8a3a, size: 32 },
      { key: 'tiles-lpc-crops',    color: 0x4a7a2a, size: 32 },
      { key: 'tiles-post-apoc',    color: 0x5a5a5a, size: 16 },
    ];
    tileConfigs.forEach(({ key, color, size }) => {
      const tex = this.textures.get(key);
      if (!tex || tex.key === MISSING_KEY || tex.key === '__DEFAULT') {
        const g = this.make.graphics({ add: false });
        g.fillStyle(color);
        g.fillRect(0, 0, size, size);
        g.lineStyle(1, 0x000000, 0.3);
        g.strokeRect(0.5, 0.5, size - 1, size - 1);
        g.generateTexture(key, size, size);
        g.destroy();
      }
    });

    this.scene.start('TitleScene');
  }
}

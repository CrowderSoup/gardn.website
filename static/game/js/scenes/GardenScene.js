const TILE_SIZE = 32;
const GRID_SIZE = 8;

export default class GardenScene extends Phaser.Scene {
  constructor() {
    super({ key: 'GardenScene' });
  }

  init(data) {
    this.gameState = data.gameState || null;
  }

  async create() {
    if (!this.gameState) {
      try {
        const resp = await fetch(window.GAME_CONFIG.stateUrl, { credentials: 'same-origin' });
        this.gameState = await resp.json();
      } catch (e) {
        this.gameState = { garden: [] };
      }
    }

    this.cameras.main.setBackgroundColor('#3d5a1e');
    this._buildMap();
    this._buildPlots();
    this._buildInput();
  }

  _buildMap() {
    const map = this.make.tilemap({ key: 'map-garden' });
    const tileset = map.addTilesetImage('lpc-farming', 'tiles-lpc-farming') ||
                    (map.tilesets[0] ? map.tilesets[0] : null);
    if (tileset) {
      map.createLayer('Ground', tileset, 0, 0);
    }
  }

  _buildPlots() {
    // Draw 8x8 garden grid
    const offsetX = 64;
    const offsetY = 64;

    for (let y = 0; y < GRID_SIZE; y++) {
      for (let x = 0; x < GRID_SIZE; x++) {
        const wx = offsetX + x * TILE_SIZE;
        const wy = offsetY + y * TILE_SIZE;

        // Plot background
        const plot = this.add.rectangle(wx + 16, wy + 16, TILE_SIZE - 2, TILE_SIZE - 2, 0x5a3a1a);
        plot.setStrokeStyle(1, 0x3a2010);

        // Check if something is planted here
        const planted = this.gameState?.garden?.find(
          (p) => p.slot_x === x && p.slot_y === y
        );
        if (planted) {
          this._drawPlant(wx, wy, planted);
        }
      }
    }
  }

  _drawPlant(wx, wy, plotData) {
    // Show growth stage as color intensity (placeholder until sprites are loaded)
    const growthColors = [0x336633, 0x448844, 0x55aa55, 0x66cc66, 0x77ee77];
    const color = growthColors[plotData.growth_stage] || growthColors[0];
    const plant = this.add.circle(wx + 16, wy + 16, 8, color);
    plant.setDepth(2);

    if (plotData.link_title) {
      this.add.text(wx + 16, wy + 26, plotData.link_title.slice(0, 8), {
        fontFamily: 'monospace',
        fontSize: '7px',
        color: '#ccffcc',
      }).setOrigin(0.5).setDepth(3);
    }
  }

  _buildInput() {
    this.input.keyboard.on('keydown-ESC', () => {
      this.scene.stop('GardenScene');
      this.scene.resume('WorldScene');
    });
  }
}

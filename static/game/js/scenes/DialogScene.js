export default class DialogScene extends Phaser.Scene {
  constructor() {
    super({ key: 'DialogScene' });
  }

  init(data) {
    this.npcName = data.npcName || 'NPC';
    this.lines = data.lines || ['...'];
    this.worldScene = data.worldScene || null;
    this.onClose = data.onClose || null;
    this.lineIndex = 0;
  }

  create() {
    const { width, height } = this.cameras.main;

    // Semi-transparent backdrop at bottom
    const boxHeight = 120;
    const boxY = height - boxHeight - 10;
    const padding = 16;

    this.bg = this.add.rectangle(width / 2, boxY + boxHeight / 2, width - 20, boxHeight, 0x1a1a1a, 0.9);
    this.bg.setStrokeStyle(2, 0x4a7c59);

    this.nameText = this.add.text(padding + 10, boxY + 10, this.npcName, {
      fontFamily: 'monospace',
      fontSize: '13px',
      color: '#7ab87a',
    });

    this.bodyText = this.add.text(padding + 10, boxY + 30, '', {
      fontFamily: 'monospace',
      fontSize: '12px',
      color: '#dddddd',
      wordWrap: { width: width - 60 },
      lineSpacing: 4,
    });

    this.promptText = this.add.text(width - 30, boxY + boxHeight - 20, '▼', {
      fontFamily: 'monospace',
      fontSize: '12px',
      color: '#666666',
    }).setOrigin(0.5);
    this.tweens.add({ targets: this.promptText, alpha: 0, duration: 400, yoyo: true, repeat: -1 });

    this._showLine();

    this._advanceHandler = () => this._advance();
    this.input.keyboard.on('keydown-SPACE', this._advanceHandler);
    this.input.keyboard.on('keydown-ENTER', this._advanceHandler);
    this.input.keyboard.on('keydown-E', this._advanceHandler);
    this.input.on('pointerdown', this._advanceHandler);
  }

  _showLine() {
    const line = this.lines[this.lineIndex] || '';
    this.bodyText.setText(line);
  }

  _advance() {
    this.lineIndex++;
    if (this.lineIndex >= this.lines.length) {
      this._close();
    } else {
      this._showLine();
    }
  }

  _close() {
    if (this._advanceHandler) {
      this.input.keyboard.off('keydown-SPACE', this._advanceHandler);
      this.input.keyboard.off('keydown-ENTER', this._advanceHandler);
      this.input.keyboard.off('keydown-E', this._advanceHandler);
      this.input.off('pointerdown', this._advanceHandler);
    }
    if (this.onClose) this.onClose();
    this.scene.stop('DialogScene');
  }
}

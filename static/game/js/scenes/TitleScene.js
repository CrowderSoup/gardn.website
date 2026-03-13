import { setUiState } from '../state.js';

export default class TitleScene extends Phaser.Scene {
  constructor() {
    super({ key: 'TitleScene' });
  }

  create() {
    const { width, height } = this.cameras.main;
    setUiState({ mode: 'title' });

    this.cameras.main.setBackgroundColor('#18281f');
    this.add.rectangle(width / 2, height / 2, width, height, 0x274533, 0.18);
    this.add.circle(width * 0.82, height * 0.18, 70, 0xf0c776, 0.14);

    const title = this.add.text(width / 2, height * 0.3, 'THE GARDN', {
      fontFamily: '"Iowan Old Style", serif',
      fontSize: '40px',
      color: '#f2f6da',
      align: 'center',
    }).setOrigin(0.5);

    const lore = this.add.text(width / 2, height * 0.48, [
      'The old feeds fell quiet.',
      '',
      'The small web kept growing anyway.',
      '',
      'Publish. Scan. Plant. Share.',
    ], {
      fontFamily: '"Avenir Next", sans-serif',
      fontSize: '15px',
      color: '#d6ddc6',
      align: 'center',
      lineSpacing: 7,
    }).setOrigin(0.5);

    const prompt = this.add.text(width / 2, height * 0.72, '[ Press any key to tend your site ]', {
      fontFamily: '"Avenir Next", sans-serif',
      fontSize: '13px',
      color: '#a3b78e',
      align: 'center',
    }).setOrigin(0.5);

    // Blink the prompt
    this.tweens.add({
      targets: prompt,
      alpha: 0,
      duration: 800,
      yoyo: true,
      repeat: -1,
    });

    // Fade in title elements
    [title, lore, prompt].forEach((obj, i) => {
      obj.setAlpha(0);
      this.tweens.add({
        targets: obj,
        alpha: 1,
        duration: 600,
        delay: i * 400,
      });
    });

    // Any key / click advances
    this.input.keyboard.once('keydown', () => this.startGame());
    this.input.once('pointerdown', () => this.startGame());
  }

  startGame() {
    this.cameras.main.fade(500, 0, 0, 0, false, (_cam, progress) => {
      if (progress === 1) {
        const startData = {};
        if (window.GAME_CONFIG.launchMapId) startData.mapId = window.GAME_CONFIG.launchMapId;
        if (window.GAME_CONFIG.launchGuestUsername) startData.guestUsername = window.GAME_CONFIG.launchGuestUsername;
        this.scene.start('WorldScene', startData);
        this.scene.launch('UIScene');
      }
    });
  }
}

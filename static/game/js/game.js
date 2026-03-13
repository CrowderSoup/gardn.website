import BootScene from './scenes/BootScene.js';
import TitleScene from './scenes/TitleScene.js';
import WorldScene from './scenes/WorldScene.js';
import DialogScene from './scenes/DialogScene.js';
import TutorialScene from './scenes/TutorialScene.js';
import UIScene from './scenes/UIScene.js';
import PlantScene from './scenes/PlantScene.js';
import { initPaddController } from './padd.js';
import { areHotkeysSuspended, installTestingHooks, setUiState, toggleFullscreen } from './state.js';

const config = {
  type: Phaser.AUTO,
  width: 640,
  height: 480,
  parent: 'game-container',
  pixelArt: true,
  antialias: false,
  audio: {
    noAudio: true,
  },
  physics: {
    default: 'arcade',
    arcade: { gravity: { y: 0 }, debug: false },
  },
  scene: [BootScene, TitleScene, WorldScene, DialogScene, TutorialScene, UIScene, PlantScene],
  scale: {
    mode: Phaser.Scale.FIT,
    autoCenter: Phaser.Scale.CENTER_BOTH,
  },
};

window.game = new Phaser.Game(config);
initPaddController();
installTestingHooks(window.game);
setUiState({ mode: 'title' });

window.addEventListener('keydown', (event) => {
  if (event.repeat || event.key.toLowerCase() !== 'f' || areHotkeysSuspended(event)) return;
  event.preventDefault();
  toggleFullscreen();
});

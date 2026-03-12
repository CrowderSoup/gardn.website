import BootScene from './scenes/BootScene.js';
import TitleScene from './scenes/TitleScene.js';
import WorldScene from './scenes/WorldScene.js';
import GardenScene from './scenes/GardenScene.js';
import DialogScene from './scenes/DialogScene.js';
import TutorialScene from './scenes/TutorialScene.js';
import UIScene from './scenes/UIScene.js';
import PlantScene from './scenes/PlantScene.js';
import { installTestingHooks, setUiState, toggleFullscreen } from './state.js';

const config = {
  type: Phaser.AUTO,
  width: 640,
  height: 480,
  parent: 'game-container',
  pixelArt: true,
  antialias: false,
  physics: {
    default: 'arcade',
    arcade: { gravity: { y: 0 }, debug: false },
  },
  scene: [BootScene, TitleScene, WorldScene, GardenScene, DialogScene, TutorialScene, UIScene, PlantScene],
  scale: {
    mode: Phaser.Scale.FIT,
    autoCenter: Phaser.Scale.CENTER_BOTH,
  },
};

window.game = new Phaser.Game(config);
installTestingHooks(window.game);
setUiState({ mode: 'title' });

window.addEventListener('keydown', (event) => {
  if (event.key.toLowerCase() === 'f') {
    event.preventDefault();
    toggleFullscreen();
  }
});

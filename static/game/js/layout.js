export const GAME_HUD_LAYOUT = Object.freeze({
  width: 640,
  height: 480,
  topSafeHeight: 42,
  bottomSafeHeight: 54,
  sideInset: 10,
  topBarHeight: 32,
  bottomBarHeight: 40,
  contentPadding: 12,
});

export function getGameplayViewport(layout = GAME_HUD_LAYOUT) {
  return {
    x: 0,
    y: layout.topSafeHeight,
    width: layout.width,
    height: layout.height - layout.topSafeHeight - layout.bottomSafeHeight,
  };
}

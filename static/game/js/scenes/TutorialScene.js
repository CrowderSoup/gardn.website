const TUTORIAL_STEPS = {
  0: null, // title screen — handled by TitleScene
  1: {
    text: 'You made it.\nSpeak with Elder Aldyn to get your bearings.',
    mastodonOnly: true,
  },
  2: {
    text: 'You still need a place on the web to tend.\nUse this helper if you want a quick starting plot, or come back once your site is ready.',
    mastodonOnly: true,
    showNeocitiesModal: true,
  },
  3: {
    text: 'Good. Your plot is registered.\nWalk north to reach your homestead.',
    mastodonOnly: true,
  },
  4: {
    text: 'Your homestead waits just to the north.\nThe path is open.',
    mastodonOnly: true,
  },
  5: {
    text: 'Welcome home.\nPress Tab to tune your look if you want, then publish on your site and press R to scan for proof.',
  },
  6: {
    text: 'A verified seed is ready.\nWalk up to an empty bed and plant it.',
  },
  7: {
    text: 'Your first plant is rooted.\nKeep publishing to feed the garden, and use the PADD to shape your homestead.',
  },
  8: {
    text: "Neighbors help gardens thrive.\nLink to someone, rescan, and the grove will start to remember them.",
  },
  9: {
    text: 'Tutorial complete.\nThe road is open. Keep tending your site, your shelves, and your grove.',
    complete: true,
  },
};

export default class TutorialScene extends Phaser.Scene {
  constructor() {
    super({ key: 'TutorialScene' });
  }

  init(data) {
    this.worldScene = data.worldScene;
    this.gameState = data.gameState;
    this.step = this.gameState?.player?.tutorial_step || 0;
    this.hasWebsite = this.gameState?.player?.has_website || false;
  }

  create() {
    this._showStep(this.step);
  }

  _showStep(step) {
    if (this._overlay) this._overlay.destroy(true);

    const stepData = TUTORIAL_STEPS[step];
    if (!stepData) return;

    // Skip mastodon-only steps for IndieAuth users
    if (stepData.mastodonOnly && this.hasWebsite) {
      this._advanceToStep(5);
      return;
    }

    if (stepData.showNeocitiesModal) {
      this._showNeocitiesModal();
      return;
    }

    const { width, height } = this.cameras.main;
    this._overlay = this.add.container(0, 0);

    const bg = this.add.rectangle(width / 2, 40, width - 20, 64, 0x1a1a1a, 0.85);
    bg.setStrokeStyle(1, 0x4a7c59);

    const txt = this.add.text(width / 2, 28, stepData.text, {
      fontFamily: 'monospace',
      fontSize: '12px',
      color: '#dddddd',
      align: 'center',
      wordWrap: { width: width - 40 },
      lineSpacing: 3,
    }).setOrigin(0.5, 0);

    const dismiss = this.add.text(width - 20, 18, '×', {
      fontFamily: 'monospace',
      fontSize: '16px',
      color: '#666666',
    }).setOrigin(1, 0).setInteractive({ useHandCursor: true });
    dismiss.on('pointerdown', () => this._overlay?.destroy(true));

    this._overlay.add([bg, txt, dismiss]);

    if (stepData.complete) {
      this._advanceTutorial(9);
    }
  }

  _showNeocitiesModal() {
    // Pause the WorldScene and inject the HTMX modal into the DOM
    if (this.worldScene) {
      this.worldScene.scene.pause();
    }
    const container = document.getElementById('neocities-modal-container');
    if (container) {
      fetch('/game/partials/neocities-modal/')
        .then((r) => r.text())
        .then((html) => {
          container.innerHTML = html;
          // Re-process HTMX on new content
          if (window.htmx) htmx.process(container);
        })
        .catch(() => {
          // Fallback: link out
          container.innerHTML = `
            <div style="background:#1a1a1a;border:1px solid #4a7c59;padding:24px;margin:16px;color:#ddd;font-family:monospace">
              <h3 style="color:#7ab87a">Claim your plot on NeoCities</h3>
              <p><a href="https://neocities.org/new" target="_blank" style="color:#7ab87a">Create your site →</a></p>
              <p>Then enter your URL below and press Enter.</p>
              <input id="nc-url" type="url" placeholder="https://yourname.neocities.org"
                     style="width:100%;padding:8px;background:#333;border:1px solid #555;color:#fff;font-family:monospace">
              <br><br>
              <button onclick="(function(){
                var url=document.getElementById('nc-url').value;
                if(!url)return;
                fetch(window.GAME_CONFIG.tutorialUrl,{
                  method:'POST',credentials:'same-origin',
                  headers:{'Content-Type':'application/json','X-CSRFToken':window.GAME_CONFIG.csrfToken},
                  body:JSON.stringify({step:3,neocities_url:url})
                }).then(()=>document.getElementById('neocities-modal-container').innerHTML='');
              })()" style="padding:8px 16px;background:#4a7c59;color:#fff;border:none;cursor:pointer;font-family:monospace">
                Claim your plot
              </button>
            </div>`;
        });
    }
  }

  advanceToStep(step) {
    if (step > this.step) {
      this._advanceToStep(step);
    }
  }

  _advanceToStep(step) {
    this.step = step;
    fetch(window.GAME_CONFIG.tutorialUrl, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': window.GAME_CONFIG.csrfToken,
      },
      body: JSON.stringify({ step }),
    }).catch(() => {});
    this._showStep(step);
  }

  _advanceTutorial(step) {
    fetch(window.GAME_CONFIG.tutorialUrl, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': window.GAME_CONFIG.csrfToken,
      },
      body: JSON.stringify({ step }),
    }).catch(() => {});
  }
}

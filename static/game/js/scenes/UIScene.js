import { getRuntimeState, setUiState } from '../state.js';

export default class UIScene extends Phaser.Scene {
  constructor() {
    super({ key: 'UIScene' });
    this._stateListener = null;
  }

  create() {
    const { width, height } = this.cameras.main;
    setUiState({ mode: 'world' });

    this.topBar = this.add.rectangle(width / 2, 18, width - 18, 34, 0x102018, 0.9);
    this.topBar.setStrokeStyle(1, 0x56775f);

    this.bottomBar = this.add.rectangle(width / 2, height - 18, width - 18, 42, 0x102018, 0.88);
    this.bottomBar.setStrokeStyle(1, 0x56775f);

    this.seedText = this.add.text(22, 10, '', {
      fontFamily: 'monospace',
      fontSize: '11px',
      color: '#d7f3c4',
    });

    this.pendingText = this.add.text(150, 10, '', {
      fontFamily: 'monospace',
      fontSize: '11px',
      color: '#f3dba1',
    });

    this.neighborText = this.add.text(290, 10, '', {
      fontFamily: 'monospace',
      fontSize: '11px',
      color: '#b9d8f5',
    });

    this.mapText = this.add.text(width - 24, 10, '', {
      fontFamily: 'monospace',
      fontSize: '11px',
      color: '#a3b98e',
      align: 'right',
    }).setOrigin(1, 0);

    this.siteText = this.add.text(22, height - 30, '', {
      fontFamily: 'monospace',
      fontSize: '10px',
      color: '#dce6d4',
      wordWrap: { width: width - 44 },
    });

    this.questText = this.add.text(width - 24, height - 30, '', {
      fontFamily: 'monospace',
      fontSize: '10px',
      color: '#f0e8bd',
      align: 'right',
      wordWrap: { width: 240 },
    }).setOrigin(1, 0);

    this._stateListener = () => this._renderFromState();
    window.addEventListener('gardn:state-change', this._stateListener);
    this._renderFromState();
  }

  shutdown() {
    if (this._stateListener) {
      window.removeEventListener('gardn:state-change', this._stateListener);
      this._stateListener = null;
    }
  }

  _renderFromState() {
    const runtime = getRuntimeState();
    const server = runtime.server || {};
    const player = server.player || {};
    const siteStatus = server.site_status || {};
    const claimableQuest = (server.quests || []).find((quest) => quest.status === 'claimable');
    const activeQuest = claimableQuest || (server.quests || []).find((quest) => quest.status !== 'complete');

    this.seedText.setText(`SEEDS ${player.links_harvested || 0}`);
    this.pendingText.setText(`PENDING ${player.pending_count || 0}`);
    this.neighborText.setText(`NEIGHBORS ${player.neighbor_count || 0}`);
    this.mapText.setText(this._labelForMap(runtime.currentMapId));

    const siteLabel = (siteStatus.status || 'never').replace(/_/g, ' ').toUpperCase();
    const issueLabel = siteStatus.issues?.length ? ` | ${siteStatus.issues.join(', ')}` : '';
    this.siteText.setText(`SITE ${siteLabel}${issueLabel}`);

    if (activeQuest) {
      this.questText.setText(`${activeQuest.title} ${activeQuest.progress}/${activeQuest.target}`);
    } else {
      this.questText.setText('All quests rooted');
    }
  }

  _labelForMap(mapId) {
    const labels = {
      overworld: 'Crossroads',
      garden: 'Homestead Garden',
      ruins: 'Link Library',
      neighbors: 'Neighbor Grove',
    };
    return labels[mapId] || mapId;
  }
}

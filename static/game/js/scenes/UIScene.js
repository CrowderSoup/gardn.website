import { getRuntimeState, setUiState } from '../state.js';
import { GAME_HUD_LAYOUT } from '../layout.js';

export default class UIScene extends Phaser.Scene {
  constructor() {
    super({ key: 'UIScene' });
    this._stateListener = null;
  }

  create() {
    const { width, height } = this.cameras.main;
    const layout = { ...GAME_HUD_LAYOUT, width, height };
    const topBarCenterY = layout.topSafeHeight / 2;
    const bottomStripTop = height - layout.bottomSafeHeight;
    const bottomBarCenterY = bottomStripTop + (layout.bottomSafeHeight / 2);
    const barWidth = width - layout.sideInset * 2;
    setUiState({ mode: 'world' });

    this.topBar = this.add.rectangle(width / 2, topBarCenterY, barWidth, layout.topBarHeight, 0x102018, 0.9);
    this.topBar.setStrokeStyle(1, 0x56775f);

    this.bottomBar = this.add.rectangle(width / 2, bottomBarCenterY, barWidth, layout.bottomBarHeight, 0x102018, 0.88);
    this.bottomBar.setStrokeStyle(1, 0x56775f);

    this.seedText = this.add.text(22, 12, '', {
      fontFamily: 'monospace',
      fontSize: '11px',
      color: '#d7f3c4',
    });

    this.pendingText = this.add.text(150, 12, '', {
      fontFamily: 'monospace',
      fontSize: '11px',
      color: '#f3dba1',
    });

    this.neighborText = this.add.text(290, 12, '', {
      fontFamily: 'monospace',
      fontSize: '11px',
      color: '#b9d8f5',
    });

    this.healthText = this.add.text(408, 12, '', {
      fontFamily: 'monospace',
      fontSize: '11px',
      color: '#f0e8bd',
    });

    this.mapText = this.add.text(width - 24, 12, '', {
      fontFamily: 'monospace',
      fontSize: '11px',
      color: '#a3b98e',
      align: 'right',
    }).setOrigin(1, 0);

    this.siteText = this.add.text(22, bottomStripTop + 10, '', {
      fontFamily: 'monospace',
      fontSize: '10px',
      color: '#dce6d4',
      wordWrap: { width: width - 290 },
    });

    this.questText = this.add.text(width - 24, bottomStripTop + 10, '', {
      fontFamily: 'monospace',
      fontSize: '10px',
      color: '#f0e8bd',
      align: 'right',
      wordWrap: { width: 250 },
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
    const guestGarden = runtime.guestGarden || null;
    const player = server.player || {};
    const siteStatus = server.site_status || {};
    const activeHealth = guestGarden?.garden_health || server.garden_health || {};
    const activeOwner = guestGarden?.owner || server.owner || {};
    const claimableQuest = (server.quests || []).find((quest) => quest.status === 'claimable');
    const activeQuest = claimableQuest || (server.quests || []).find((quest) => quest.status !== 'complete');

    this.seedText.setText(`SEEDS ${player.links_harvested || 0}`);
    this.pendingText.setText(`PENDING ${player.pending_count || 0}`);
    this.neighborText.setText(`NEIGHBORS ${player.neighbor_count || 0}`);
    this.healthText.setText(`HEALTH ${activeHealth.score || 0}`);
    this.mapText.setText(this._labelForMap(runtime.currentMapId));

    if (guestGarden) {
      const ownerLabel = activeOwner.display_name || activeOwner.username || 'Neighbor';
      const pollination = activeHealth.recent_visitor_count || 0;
      const bloom = (activeHealth.label || 'fragile').toUpperCase();
      this.siteText.setText(`VISITING ${ownerLabel} | POLLINATION ${pollination} | ${bloom}`);
    } else {
      const siteLabel = (siteStatus.status || 'never').replace(/_/g, ' ').toUpperCase();
      const issueLabel = siteStatus.issues?.length ? ` | ${siteStatus.issues.join(', ')}` : '';
      this.siteText.setText(`SITE ${siteLabel}${issueLabel} | POLLINATION ${activeHealth.recent_visitor_count || 0}`);
    }

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
      guest_garden: 'Guest Garden',
      ruins: 'Link Library',
      neighbors: 'Neighbor Grove',
    };
    return labels[mapId] || mapId;
  }
}

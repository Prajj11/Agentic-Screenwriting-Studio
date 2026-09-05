import { ClickHouseHealth } from '@/lib/api';

interface TopBarProps {
  onToggleSidebar: () => void;
  view: 'dashboard' | 'project';
  onBackToDashboard: () => void;
  projectTitle?: string;
  connected: boolean;
  chHealth: ClickHouseHealth | null;
}

export function TopBar({ onToggleSidebar, view, onBackToDashboard, projectTitle, connected, chHealth }: TopBarProps) {
  return (
    <header className="studio-header">
      <div className="studio-header__left">
        <button
          className="hamburger-btn"
          onClick={onToggleSidebar}
          aria-label="Toggle menu"
        >
          <span className="hamburger-btn__line" />
          <span className="hamburger-btn__line" />
          <span className="hamburger-btn__line" />
        </button>
        <div className="studio-header__brand">
          <span className="studio-header__icon">🎬</span>
          <h1 className="studio-header__title">Talevora</h1>
          <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginLeft: '6px', fontWeight: 400, opacity: 0.8 }}>Studio</span>
        </div>
      </div>
      <div className="studio-header__right">
        {view === 'project' && (
          <button className="header-back-btn" onClick={onBackToDashboard}>
            ← Projects
          </button>
        )}
        {view === 'project' && projectTitle && (
          <span className="studio-header__project-name">
            {projectTitle}
          </span>
        )}
        <div className="studio-header__status-badges">
          <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
            {connected ? '🟢 Live' : '🔴 Offline'}
          </span>
          {chHealth?.clickhouse && (
            <span
              className={`ch-status-badge ch-status-badge--${
                chHealth.clickhouse?.status === 'connected'
                  ? 'connected'
                  : chHealth.clickhouse?.status === 'not_configured'
                  ? 'fallback'
                  : 'error'
              }`}
              title={
                chHealth.clickhouse?.status === 'connected'
                  ? `ClickHouse: ${chHealth.clickhouse?.host} — ${chHealth.clickhouse?.scenes_indexed ?? 0} scenes`
                  : chHealth.clickhouse?.status === 'not_configured'
                  ? 'ClickHouse not configured — using local ChromaDB'
                  : `ClickHouse error: ${chHealth.clickhouse?.error}`
              }
            >
              {chHealth.clickhouse?.status === 'connected' ? '🟢' : chHealth.clickhouse?.status === 'not_configured' ? '🟡' : '🔴'}
              {' '}ClickHouse
            </span>
          )}
        </div>
      </div>
    </header>
  );
}

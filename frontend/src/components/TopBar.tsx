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
          <span className="studio-header__subtitle">Studio</span>
        </div>
      </div>
      <div className="studio-header__right">
        {view === 'project' && (
          <button className="header-back-btn" onClick={onBackToDashboard} title="Back to Projects">
            <span className="header-back-btn__icon">←</span>
            <span className="header-back-btn__label"> Projects</span>
          </button>
        )}
        {view === 'project' && projectTitle && (
          <span className="studio-header__project-name" title={projectTitle}>
            {projectTitle}
          </span>
        )}
        <div className="studio-header__status-badges">
          <span className="status-badge-live" title={connected ? 'Connected to backend' : 'Backend offline'}>
            <span className="status-dot">{connected ? '🟢' : '🔴'}</span>
            <span className="status-label">{connected ? ' Live' : ' Offline'}</span>
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
                  ? `ClickHouse: ${chHealth.clickhouse?.host} — ${chHealth.clickhouse?.scenes_indexed ?? 0} scenes, ${chHealth.clickhouse?.facts_indexed ?? 0} facts`
                  : chHealth.clickhouse?.status === 'not_configured'
                  ? 'ClickHouse not configured — using local ChromaDB'
                  : `ClickHouse error: ${chHealth.clickhouse?.error}`
              }
            >
              <span className="ch-status-dot">
                {chHealth.clickhouse?.status === 'connected' ? '🟢' : chHealth.clickhouse?.status === 'not_configured' ? '🟡' : '🔴'}
              </span>
              <span className="ch-status-label"> ClickHouse</span>
              <span className="ch-status-label-short"> CH</span>
            </span>
          )}
        </div>
      </div>
    </header>
  );
}


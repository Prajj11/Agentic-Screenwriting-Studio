import { ClickHouseHealth } from '@/lib/api';

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
  onNavigateDashboard: () => void;
  onAction: (prompt: string) => void;
  isLoading: boolean;
  connected: boolean;
  chHealth: ClickHouseHealth | null;
  activeTab: 'script' | 'beats' | 'characters' | 'media';
  setActiveTab: (tab: 'script' | 'beats' | 'characters' | 'media') => void;
  isProjectView: boolean;
}

const QUICK_ACTIONS = [
  { label: '📐 Beat Sheet', prompt: 'Generate the beat sheet for this story', icon: '📐' },
  { label: '✍️ Draft Scene', prompt: 'Draft the next scene from the beat sheet', icon: '✍️' },
  { label: '🎥 Analyze Media', prompt: 'Analyze uploaded reference image or video', icon: '🎥' },
  { label: '🔍 Check Continuity', prompt: 'Run a continuity check on the latest scene', icon: '🔍' },
  { label: '🎙️ Table Read', prompt: 'Perform a table read of the latest scene', icon: '🎙️' },
  { label: '🎨 Visualize', prompt: 'Generate a mood board for the latest scene', icon: '🎨' },
  { label: '⚖️ Clearance Check', prompt: 'Run a rights and clearance check on the latest scene', icon: '⚖️' },
  { label: '🌐 Research', prompt: 'Research: ', icon: '🌐' },
];

export function Sidebar({ isOpen, onClose, onNavigateDashboard, onAction, isLoading, connected, chHealth, activeTab, setActiveTab, isProjectView }: SidebarProps) {
  return (
    <>
      {isOpen && (
        <div className="sidebar-overlay" onClick={onClose} style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)', zIndex: 900
        }} />
      )}
      <aside className={`sidebar ${isOpen ? 'sidebar--open' : ''}`}>
        <div className="sidebar__header">
          <span className="sidebar__title">Menu</span>
          <button className="sidebar__close" onClick={onClose}>✕</button>
        </div>
        <nav className="sidebar__nav">
          <button
            className="sidebar__btn sidebar__btn--new"
            onClick={onNavigateDashboard}
          >
            <span className="sidebar__btn-icon">🎬</span>
            <span className="sidebar__btn-label">Projects</span>
            <span className="sidebar__btn-desc">Back to dashboard</span>
          </button>
          
          <div className="sidebar__divider" />
          
          {isProjectView && (
            <>
              <div style={{ padding: 'var(--space-xs) var(--space-md)', fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-tertiary)', letterSpacing: '0.1em', marginTop: 'var(--space-md)', fontWeight: 600 }}>Workspace</div>
              
              <button className="sidebar__btn" style={{ background: activeTab === 'script' ? 'var(--bg-active)' : 'transparent' }} onClick={() => setActiveTab('script')}>
                <span className="sidebar__btn-icon">📜</span>
                <span className="sidebar__btn-label">Script</span>
              </button>
              
              <button className="sidebar__btn" style={{ background: activeTab === 'beats' ? 'var(--bg-active)' : 'transparent' }} onClick={() => setActiveTab('beats')}>
                <span className="sidebar__btn-icon">📐</span>
                <span className="sidebar__btn-label">Beat Sheet</span>
              </button>
              
              <button className="sidebar__btn" style={{ background: activeTab === 'characters' ? 'var(--bg-active)' : 'transparent' }} onClick={() => setActiveTab('characters')}>
                <span className="sidebar__btn-icon">👥</span>
                <span className="sidebar__btn-label">Characters</span>
              </button>

              <button className="sidebar__btn" style={{ background: activeTab === 'media' ? 'var(--bg-active)' : 'transparent' }} onClick={() => setActiveTab('media')}>
                <span className="sidebar__btn-icon">🎥</span>
                <span className="sidebar__btn-label">Media Lab</span>
              </button>

              <div className="sidebar__divider" />
              <div style={{ padding: 'var(--space-xs) var(--space-md)', fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-tertiary)', letterSpacing: '0.1em', marginTop: 'var(--space-md)', fontWeight: 600 }}>Quick Actions</div>
              {QUICK_ACTIONS.map((action) => (
                <button
                  key={action.label}
                  className="sidebar__btn"
                  disabled={isLoading}
                  onClick={() => {
                    onAction(action.prompt);
                    onClose();
                  }}
                >
                  <span className="sidebar__btn-icon">{action.icon}</span>
                  <span className="sidebar__btn-label">{action.label.replace(/^[^\s]+\s/, '')}</span>
                </button>
              ))}
            </>
          )}
        </nav>
        <div className="sidebar__footer">
          <div className="sidebar__status">
            <span>{connected ? '🟢' : '🔴'}</span>
            <span>{connected ? 'Connected' : 'Offline'}</span>
          </div>
          {chHealth && (
            <div className="sidebar__status">
              <span>
                {chHealth.clickhouse.status === 'connected' ? '🟢' : chHealth.clickhouse.status === 'not_configured' ? '🟡' : '🔴'}
              </span>
              <span>ClickHouse</span>
            </div>
          )}
        </div>
      </aside>
    </>
  );
}

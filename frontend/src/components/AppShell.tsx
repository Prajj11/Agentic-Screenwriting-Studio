import { ReactNode } from 'react';
import { TopBar } from './TopBar';
import { Sidebar } from './Sidebar';
import { ClickHouseHealth } from '@/lib/api';

interface AppShellProps {
  children: ReactNode;
  view: 'dashboard' | 'project';
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  onBackToDashboard: () => void;
  onAction: (prompt: string) => void;
  projectTitle?: string;
  connected: boolean;
  isLoading: boolean;
  chHealth: ClickHouseHealth | null;
  activeTab: 'script' | 'beats' | 'characters';
  setActiveTab: (tab: 'script' | 'beats' | 'characters') => void;
}

export function AppShell({
  children,
  view,
  sidebarOpen,
  setSidebarOpen,
  onBackToDashboard,
  onAction,
  projectTitle,
  connected,
  isLoading,
  chHealth,
  activeTab,
  setActiveTab,
}: AppShellProps) {
  return (
    <div className="studio-layout">
      {/* ── Ambient Background Animation ────────────────────────── */}
      <div className="ambient-background">
        <div className="ambient-blob ambient-blob--1" />
        <div className="ambient-blob ambient-blob--2" />
        <div className="ambient-blob ambient-blob--3" />
      </div>

      <Sidebar
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onNavigateDashboard={onBackToDashboard}
        onAction={onAction}
        isLoading={isLoading}
        connected={connected}
        chHealth={chHealth}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        isProjectView={view === 'project'}
      />

      <TopBar
        onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
        view={view}
        onBackToDashboard={onBackToDashboard}
        projectTitle={projectTitle}
        connected={connected}
        chHealth={chHealth}
      />

      {children}
    </div>
  );
}

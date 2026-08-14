'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import {
  sendMessage,
  getScriptState,
  getAgentStatuses,
  getClickHouseHealth,
  recoverSession,
  getChatHistory,
  persistProjectId,
  loadPersistedProjectId,
  listProjects,
  deleteProject,
  type ChatResponse,
  type ScriptState,
  type Scene,
  type Beat,
  type AgentStatus,
  type ClickHouseHealth,
  type ProjectListItem,
} from '@/lib/api';
import { useWebSocket, type WSEvent } from '@/hooks/useWebSocket';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// ΓöÇΓöÇ Types ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

interface ChatMessage {
  id: string;
  role: 'user' | 'agent';
  text: string;
  agent?: string;
  timestamp: string;
}

// ΓöÇΓöÇ Quick Action Presets ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

const QUICK_ACTIONS = [
  { label: '≡ƒôÉ Beat Sheet', prompt: 'Generate the beat sheet for this story', icon: '≡ƒôÉ' },
  { label: 'Γ£ì∩╕Å Draft Scene', prompt: 'Draft the next scene from the beat sheet', icon: 'Γ£ì∩╕Å' },
  { label: '≡ƒöì Check Continuity', prompt: 'Run a continuity check on the latest scene', icon: '≡ƒöì' },
  { label: '≡ƒÄÖ∩╕Å Table Read', prompt: 'Perform a table read of the latest scene', icon: '≡ƒÄÖ∩╕Å' },
  { label: '≡ƒÄ¿ Visualize', prompt: 'Generate a mood board for the latest scene', icon: '≡ƒÄ¿' },
  { label: 'ΓÜû∩╕Å Clearance Check', prompt: 'Run a rights and clearance check on the latest scene', icon: 'ΓÜû∩╕Å' },
  { label: '≡ƒîÉ Research', prompt: 'Research: ', icon: '≡ƒîÉ' },
];

// ΓöÇΓöÇ Main Page Component ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

export default function StudioPage() {
  // View state
  const [view, setView] = useState<'dashboard' | 'project'>('dashboard');
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Project management
  const [projects, setProjects] = useState<ProjectListItem[]>([]);
  const [pinnedProjects, setPinnedProjects] = useState<Set<string>>(new Set());
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);

  // Chat/project state
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [scriptState, setScriptState] = useState<ScriptState | null>(null);
  const [agents, setAgents] = useState<AgentStatus[]>([]);
  const [activeScene, setActiveScene] = useState<number>(0);
  const [activeBeat, setActiveBeat] = useState<number | null>(null);
  const [chHealth, setChHealth] = useState<ClickHouseHealth | null>(null);

  // Refs
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // WebSocket for real-time events
  const onWSEvent = useCallback((event: WSEvent) => {
    if (event.type === 'agent_start' || event.type === 'agent_end') {
      getAgentStatuses().then(setAgents).catch(() => {});
    }
  }, []);

  const { connected } = useWebSocket(onWSEvent);

  // Auto-scroll messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Poll agent statuses
  useEffect(() => {
    const poll = setInterval(() => {
      getAgentStatuses().then(setAgents).catch(() => {});
    }, 3000);
    return () => clearInterval(poll);
  }, []);

  // Poll ClickHouse health
  useEffect(() => {
    getClickHouseHealth().then(setChHealth).catch(() => {});
    const poll = setInterval(() => {
      getClickHouseHealth().then(setChHealth).catch(() => {});
    }, 30000);
    return () => clearInterval(poll);
  }, []);

  // Load projects on mount
  useEffect(() => {
    listProjects().then(setProjects);
  }, []);

  // Load pinned projects from localStorage
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem('studio_pinned_projects');
      if (stored) {
        try {
          setPinnedProjects(new Set(JSON.parse(stored)));
        } catch { /* ignore */ }
      }
    }
  }, []);

  // Session recovery on mount
  useEffect(() => {
    const storedId = loadPersistedProjectId();
    if (!storedId) return;

    // Don't auto-navigate to project view on mount, just store the ID
    setProjectId(storedId);
  }, []);

  // Refresh script state after agent response
  const refreshScriptState = useCallback(async (pid: string) => {
    try {
      const state = await getScriptState(pid);
      setScriptState(state);
    } catch (e) {
      console.warn('Failed to refresh script state:', e);
    }
  }, []);

  // ΓöÇΓöÇ Project Management ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

  const refreshProjects = useCallback(async () => {
    const list = await listProjects();
    setProjects(list);
  }, []);

  const handleOpenProject = useCallback(async (pid: string) => {
    setProjectId(pid);
    persistProjectId(pid);
    setMessages([]);
    setScriptState(null);
    setView('project');
    // Recover session, load script state, and load chat history
    recoverSession(pid)
      .then((result) => {
        if (!result) return;
        return Promise.all([
          getScriptState(pid).catch(() => null),
          getChatHistory(pid).catch(() => ({ messages: [] }))
        ]);
      })
      .then((data) => {
        if (data) {
          const [state, history] = data;
          if (state) setScriptState(state);
          if (history && history.messages) {
            setMessages(history.messages);
          }
        }
      })
      .catch(() => {});
  }, []);

  const handleDeleteProject = useCallback(async (pid: string) => {
    const success = await deleteProject(pid);
    if (success) {
      setDeleteConfirm(null);
      if (projectId === pid) {
        setProjectId(null);
        setScriptState(null);
        setMessages([]);
        setView('dashboard');
      }
      // Remove from pinned
      setPinnedProjects(prev => {
        const next = new Set(prev);
        next.delete(pid);
        if (typeof window !== 'undefined') {
          localStorage.setItem('studio_pinned_projects', JSON.stringify([...next]));
        }
        return next;
      });
      await refreshProjects();
    }
  }, [projectId, refreshProjects]);

  const handlePinProject = useCallback((pid: string) => {
    setPinnedProjects(prev => {
      const next = new Set(prev);
      if (next.has(pid)) {
        next.delete(pid);
      } else {
        next.add(pid);
      }
      if (typeof window !== 'undefined') {
        localStorage.setItem('studio_pinned_projects', JSON.stringify([...next]));
      }
      return next;
    });
  }, []);

  const handleBackToDashboard = useCallback(() => {
    setView('dashboard');
    setSidebarOpen(false);
    refreshProjects();
  }, [refreshProjects]);

  // ΓöÇΓöÇ Send Message ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

  const handleSend = useCallback(async (text?: string) => {
    const message = text || input.trim();
    if (!message || isLoading) return;

    setInput('');
    setIsLoading(true);
    setSidebarOpen(false);

    // Add user message
    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      text: message,
      timestamp: new Date().toISOString(),
    };
    setMessages(prev => [...prev, userMsg]);

    try {
      const response: ChatResponse = await sendMessage({
        message,
        project_id: projectId || undefined,
      });

      // Set project ID from response and persist it
      if (response.project_id && !projectId) {
        setProjectId(response.project_id);
        persistProjectId(response.project_id);
        // Switch to project view if on dashboard
        setView('project');
      }

      // Add agent response
      const agentMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'agent',
        text: response.response_text,
        agent: 'Showrunner',
        timestamp: new Date().toISOString(),
      };
      setMessages(prev => [...prev, agentMsg]);

      // Refresh script state
      if (response.project_id) {
        await refreshScriptState(response.project_id);
      }
    } catch (error) {
      const errorText = error instanceof Error ? error.message : 'Unknown error';
      const errMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'agent',
        text: `ΓÜá∩╕Å The backend server took too long to respond. This usually means it's still starting up.\n\nPlease wait a few seconds and try again.\n\n_(${errorText})_`,
        agent: 'System',
        timestamp: new Date().toISOString(),
      };
      setMessages(prev => [...prev, errMsg]);
    } finally {
      setIsLoading(false);
      inputRef.current?.focus();
    }
  }, [input, isLoading, projectId, refreshScriptState]);

  // Keyboard handler
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // ΓöÇΓöÇ Current Scene ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

  const currentScene: Scene | null = scriptState?.scenes?.[activeScene] || null;
  const beats: Beat[] = scriptState?.beat_sheet || [];

  // ΓöÇΓöÇ Sort projects: pinned first ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

  const sortedProjects = [...projects].sort((a, b) => {
    const aPinned = pinnedProjects.has(a.project_id);
    const bPinned = pinnedProjects.has(b.project_id);
    if (aPinned && !bPinned) return -1;
    if (!aPinned && bPinned) return 1;
    return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
  });

  // ΓöÇΓöÇ Format date ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

  const formatDate = (dateStr: string) => {
    try {
      const d = new Date(dateStr);
      const now = new Date();
      const diffMs = now.getTime() - d.getTime();
      const diffMins = Math.floor(diffMs / 60000);
      const diffHours = Math.floor(diffMs / 3600000);
      const diffDays = Math.floor(diffMs / 86400000);
      if (diffMins < 1) return 'Just now';
      if (diffMins < 60) return `${diffMins}m ago`;
      if (diffHours < 24) return `${diffHours}h ago`;
      if (diffDays < 7) return `${diffDays}d ago`;
      return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    } catch { return ''; }
  };

  // ΓöÇΓöÇ Render ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

  return (
    <div className="studio-layout">
      {/* ΓöÇΓöÇ Ambient Background Animation ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ */}
      <div className="ambient-background">
        <div className="ambient-blob ambient-blob--1" />
        <div className="ambient-blob ambient-blob--2" />
        <div className="ambient-blob ambient-blob--3" />
      </div>

      {/* ΓöÇΓöÇ Sidebar Overlay ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ */}
      {sidebarOpen && (
        <div className="sidebar-overlay" onClick={() => setSidebarOpen(false)} />
      )}

      {/* ΓöÇΓöÇ Sidebar Menu ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ */}
      <aside className={`sidebar ${sidebarOpen ? 'sidebar--open' : ''}`}>
        <div className="sidebar__header">
          <span className="sidebar__title">Tools</span>
          <button className="sidebar__close" onClick={() => setSidebarOpen(false)}>Γ£ò</button>
        </div>
        <nav className="sidebar__nav">
          <button
            className="sidebar__btn sidebar__btn--new"
            onClick={handleBackToDashboard}
          >
            <span className="sidebar__btn-icon">≡ƒÄ¼</span>
            <span className="sidebar__btn-label">New Pitch</span>
            <span className="sidebar__btn-desc">Start a new project</span>
          </button>
          <div className="sidebar__divider" />
          {QUICK_ACTIONS.map((action) => (
            <button
              key={action.label}
              className="sidebar__btn"
              disabled={isLoading || view !== 'project'}
              onClick={() => {
                if (action.prompt.endsWith(': ')) {
                  setInput(action.prompt);
                  inputRef.current?.focus();
                  setSidebarOpen(false);
                } else {
                  handleSend(action.prompt);
                }
              }}
            >
              <span className="sidebar__btn-icon">{action.icon}</span>
              <span className="sidebar__btn-label">{action.label.replace(/^[^\s]+\s/, '')}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar__footer">
          <div className="sidebar__status">
            <span>{connected ? '≡ƒƒó' : '≡ƒö┤'}</span>
            <span>{connected ? 'Connected' : 'Offline'}</span>
          </div>
          {chHealth && (
            <div className="sidebar__status">
              <span>
                {chHealth.clickhouse.status === 'connected' ? '≡ƒƒó' : chHealth.clickhouse.status === 'not_configured' ? '≡ƒƒí' : '≡ƒö┤'}
              </span>
              <span>ClickHouse</span>
            </div>
          )}
        </div>
      </aside>

      {/* ΓöÇΓöÇ Header ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ */}
      <header className="studio-header">
        <div className="studio-header__left">
          <button
            className="hamburger-btn"
            onClick={() => setSidebarOpen(!sidebarOpen)}
            aria-label="Toggle menu"
          >
            <span className="hamburger-btn__line" />
            <span className="hamburger-btn__line" />
            <span className="hamburger-btn__line" />
          </button>
          <div className="studio-header__brand">
            <span className="studio-header__icon">≡ƒÄ¼</span>
            <h1 className="studio-header__title">Agentic Screenwriting Studio</h1>
          </div>
        </div>
        <div className="studio-header__right">
          {view === 'project' && (
            <button className="header-back-btn" onClick={handleBackToDashboard}>
              ΓåÉ Projects
            </button>
          )}
          {view === 'project' && scriptState && (
            <span className="studio-header__project-name">
              {scriptState.title || 'Untitled'}
            </span>
          )}
          <div className="studio-header__status-badges">
            <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
              {connected ? '≡ƒƒó Live' : '≡ƒö┤ Offline'}
            </span>
            {chHealth && (
              <span
                className={`ch-status-badge ch-status-badge--${
                  chHealth.clickhouse.status === 'connected'
                    ? 'connected'
                    : chHealth.clickhouse.status === 'not_configured'
                    ? 'fallback'
                    : 'error'
                }`}
                title={
                  chHealth.clickhouse.status === 'connected'
                    ? `ClickHouse: ${chHealth.clickhouse.host} ΓÇö ${chHealth.clickhouse.scenes_indexed ?? 0} scenes, ${chHealth.clickhouse.facts_indexed ?? 0} facts indexed`
                    : chHealth.clickhouse.status === 'not_configured'
                    ? 'ClickHouse not configured ΓÇö using local ChromaDB'
                    : `ClickHouse error: ${chHealth.clickhouse.error}`
                }
              >
                {chHealth.clickhouse.status === 'connected' ? '≡ƒƒó' : chHealth.clickhouse.status === 'not_configured' ? '≡ƒƒí' : '≡ƒö┤'}
                {' '}ClickHouse
              </span>
            )}
          </div>
        </div>
      </header>

      {/* ΓöÇΓöÇ Main Content ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ */}
      {view === 'dashboard' ? (
        /* ΓöÇΓöÇ Dashboard View ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ */
        <main className="dashboard">
          <div className="dashboard__hero">
            <h2 className="dashboard__heading">Your Projects</h2>
            <p className="dashboard__subtitle">
              Select a project to continue, or start a new screenplay pitch
            </p>
          </div>

          <div className="dashboard__grid">
            {/* New Project Card */}
            <button
              className="project-card project-card--new"
              onClick={() => {
                setProjectId(null);
                setMessages([]);
                setScriptState(null);
                setView('project');
                setTimeout(() => inputRef.current?.focus(), 100);
              }}
            >
              <div className="project-card__plus">+</div>
              <span className="project-card__new-label">New Project</span>
            </button>

            {/* Existing Projects */}
            {sortedProjects.map(proj => (
              <div
                key={proj.project_id}
                className={`project-card ${pinnedProjects.has(proj.project_id) ? 'project-card--pinned' : ''}`}
              >
                <div className="project-card__actions">
                  <button
                    className={`project-card__pin ${pinnedProjects.has(proj.project_id) ? 'project-card__pin--active' : ''}`}
                    onClick={(e) => { e.stopPropagation(); handlePinProject(proj.project_id); }}
                    title={pinnedProjects.has(proj.project_id) ? 'Unpin' : 'Pin'}
                  >
                    ≡ƒôî
                  </button>
                  <button
                    className="project-card__delete"
                    onClick={(e) => { e.stopPropagation(); setDeleteConfirm(proj.project_id); }}
                    title="Delete project"
                  >
                    ≡ƒùæ∩╕Å
                  </button>
                </div>
                <div
                  className="project-card__body"
                  onClick={() => handleOpenProject(proj.project_id)}
                >
                  <h3 className="project-card__title">{proj.title || 'Untitled Project'}</h3>
                  <div className="project-card__meta">
                    <span className="project-card__date">
                      {formatDate(proj.updated_at || proj.created_at)}
                    </span>
                  </div>
                </div>

                {/* Delete Confirmation */}
                {deleteConfirm === proj.project_id && (
                  <div className="project-card__confirm">
                    <p>Delete this project?</p>
                    <div className="project-card__confirm-actions">
                      <button
                        className="project-card__confirm-btn project-card__confirm-btn--danger"
                        onClick={(e) => { e.stopPropagation(); handleDeleteProject(proj.project_id); }}
                      >
                        Delete
                      </button>
                      <button
                        className="project-card__confirm-btn"
                        onClick={(e) => { e.stopPropagation(); setDeleteConfirm(null); }}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </main>
      ) : (
        /* ΓöÇΓöÇ Project View ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ */
        <>
          <main className="studio-main">
            {/* ΓöÇΓöÇ Left: Chat Panel ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ */}
            <div className="panel chat-panel">
              <div className="panel__header">
                <span className="panel__title">Writers&apos; Room</span>
              </div>

              {/* Messages */}
              <div className="panel__content">
                <div className="chat-messages">
                  {messages.length === 0 && (
                    <div style={{ padding: 'var(--space-lg)', textAlign: 'center' }}>
                      <p style={{ fontSize: '1.5rem', marginBottom: 'var(--space-md)' }}>≡ƒÄ¼</p>
                      <p style={{ color: 'var(--text-secondary)', fontSize: '0.88rem', lineHeight: 1.7 }}>
                        Welcome to the Writers&apos; Room.<br />
                        Start with a pitch, and your AI team will build your screenplay.
                      </p>
                    </div>
                  )}

                  {messages.map((msg, index) => (
                    <div
                      key={msg.id}
                      className={`chat-message chat-message--${msg.role}`}
                    >
                      <div className={`chat-message__author ${msg.role === 'agent' ? 'chat-message__author--agent' : ''}`}>
                        {msg.role === 'user' ? '≡ƒæñ You' : `≡ƒÄ¼ ${msg.agent || 'Agent'}`}
                      </div>
                      {msg.role === 'agent' ? (
                        <div className="markdown-body">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {msg.text}
                          </ReactMarkdown>
                        </div>
                      ) : (
                        <div className="chat-message__text">{msg.text}</div>
                      )}

                      {/* Step-by-step buttons for common tasks */}
                      {msg.role === 'agent' && index === messages.length - 1 && !isLoading && (
                        <div className="chat-message__actions" style={{ marginTop: 'var(--space-md)', display: 'flex', gap: 'var(--space-sm)', flexWrap: 'wrap' }}>
                          <button className="sidebar__btn" style={{ padding: '0.4rem 0.8rem', fontSize: '0.8rem', minHeight: 'auto', background: 'var(--surface-sunken)' }} onClick={() => handleSend("Generate the beat sheet")}>≡ƒôÉ Beat Sheet</button>
                          <button className="sidebar__btn" style={{ padding: '0.4rem 0.8rem', fontSize: '0.8rem', minHeight: 'auto', background: 'var(--surface-sunken)' }} onClick={() => handleSend("Draft the next scene")}>Γ£ì∩╕Å Draft Scene</button>
                          <button className="sidebar__btn" style={{ padding: '0.4rem 0.8rem', fontSize: '0.8rem', minHeight: 'auto', background: 'var(--surface-sunken)' }} onClick={() => handleSend("Check continuity for the latest scene")}>≡ƒöì Check Continuity</button>
                          <button className="sidebar__btn" style={{ padding: '0.4rem 0.8rem', fontSize: '0.8rem', minHeight: 'auto', background: 'var(--surface-sunken)' }} onClick={() => handleSend("Perform a Table Read of the latest scene")}>≡ƒÄÖ∩╕Å Table Read</button>
                          <button className="sidebar__btn" style={{ padding: '0.4rem 0.8rem', fontSize: '0.8rem', minHeight: 'auto', background: 'var(--surface-sunken)' }} onClick={() => handleSend("Visualize the latest scene")}>≡ƒÄ¿ Visualize Scene</button>
                        </div>
                      )}
                    </div>
                  ))}

                  {isLoading && (
                    <div className="chat-message chat-message--agent">
                      <div className="chat-message__author chat-message__author--agent">
                        ≡ƒÄ¼ Showrunner
                      </div>
                      <div className="typing-indicator">
                        <div className="typing-dot" />
                        <div className="typing-dot" />
                        <div className="typing-dot" />
                      </div>
                    </div>
                  )}

                  <div ref={messagesEndRef} />
                </div>
              </div>

              {/* Input */}
              <div className="chat-input-area">
                <div className="chat-input-wrapper">
                  <textarea
                    ref={inputRef}
                    className="chat-input"
                    placeholder="Enter your pitch, scene request, or direction..."
                    value={input}
                    onChange={e => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    rows={1}
                    disabled={isLoading}
                  />
                  <button
                    className="chat-send-btn"
                    onClick={() => handleSend()}
                    disabled={isLoading || !input.trim()}
                    aria-label="Send message"
                  >
                    Γû╢
                  </button>
                </div>
              </div>
            </div>

            {/* ΓöÇΓöÇ Center: Script Editor ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ */}
            <div className="panel script-editor">
              <div className="panel__header">
                <span className="panel__title">
                  Script{currentScene ? ` ΓÇö Scene ${currentScene.scene_number}` : ''}
                </span>
                {scriptState && (
                  <span style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)' }}>
                    {scriptState.metadata.total_scenes} scenes ┬╖ {scriptState.metadata.page_count} pages
                  </span>
                )}
              </div>

              <div className="panel__content">
                {!scriptState || scriptState.scenes.length === 0 ? (
                  <div className="script-empty">
                    <div className="script-empty__icon">≡ƒô¥</div>
                    <h2 className="script-empty__title">Your Script Awaits</h2>
                    <p className="script-empty__subtitle">
                      Start by entering a pitch in the Writers&apos; Room panel.
                      The Story Architect will generate a beat sheet, then the
                      Dialogue Specialist will draft each scene.
                    </p>
                  </div>
                ) : (
                  <div className="script-content">
                    {/* Script Header */}
                    <div style={{ marginBottom: 'var(--space-2xl)', textAlign: 'center' }}>
                      <h2 style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: '1.2rem',
                        fontWeight: 700,
                        textTransform: 'uppercase',
                        letterSpacing: '0.1em',
                        marginBottom: 'var(--space-sm)',
                      }}>
                        {scriptState.title}
                      </h2>
                      <p style={{
                        fontSize: '0.8rem',
                        color: 'var(--text-tertiary)',
                        fontStyle: 'italic',
                      }}>
                        {scriptState.logline}
                      </p>
                    </div>

                    {/* Scenes */}
                    {scriptState.scenes.map((scene) => (
                      <div
                        key={scene.scene_number}
                        style={{
                          marginBottom: 'var(--space-2xl)',
                          opacity: scene.scene_number === currentScene?.scene_number ? 1 : 0.6,
                          cursor: 'pointer',
                        }}
                        onClick={() => setActiveScene(
                          scriptState.scenes.findIndex(s => s.scene_number === scene.scene_number)
                        )}
                      >
                        {/* Scene Experience (Image + Audio) */}
                        {scene.scene_number === currentScene?.scene_number && (scene.mood_board_image || scene.table_read_audio) && (
                          <div className="scene-experience" style={{ marginBottom: 'var(--space-xl)', background: 'var(--bg-tertiary)', padding: 'var(--space-md)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)' }}>
                            <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--accent-primary)', marginBottom: 'var(--space-sm)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>≡ƒÄ¼ Scene Experience</div>
                            {scene.mood_board_image && (
                              <div className="scene-media-image" style={{ marginBottom: 'var(--space-md)' }}>
                                <img
                                  src={`http://localhost:8000${scene.mood_board_image}`}
                                  alt="Scene visual"
                                  style={{
                                    width: '100%',
                                    borderRadius: 'var(--radius-sm)',
                                    boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
                                  }}
                                />
                              </div>
                            )}
                            {scene.table_read_audio && (
                              <div className="scene-media-audio">
                                <audio
                                  controls
                                  src={`http://localhost:8000${scene.table_read_audio}`}
                                  style={{ width: '100%' }}
                                >
                                  Your browser does not support audio.
                                </audio>
                              </div>
                            )}
                          </div>
                        )}

                        {/* Slugline */}
                        {scene.slugline && (
                          <div className="screenplay-slugline">{scene.slugline}</div>
                        )}

                        {/* Action Lines */}
                        {scene.action_lines && (
                          <div className="screenplay-action">{scene.action_lines}</div>
                        )}

                        {/* Dialogue */}
                        {scene.dialogue?.map((dl, idx) => (
                          <div key={idx}>
                            <div className="screenplay-character">{dl.character}</div>
                            {dl.parenthetical && (
                              <div className="screenplay-parenthetical">({dl.parenthetical})</div>
                            )}
                            <div className="screenplay-dialogue">{dl.line}</div>
                          </div>
                        ))}

                        {/* Continuity Issues */}
                        {scene.continuity_issues?.filter(i => !i.resolved).map((issue, idx) => (
                          <div key={idx} className="continuity-flag">
                            <span style={{ fontSize: '0.75rem' }}>
                              ΓÜá∩╕Å <strong>Continuity:</strong> {issue.description}
                            </span>
                          </div>
                        ))}

                        {/* Clearance Flags */}
                        {scene.clearance_flags?.filter(f => !f.resolved).map((flag, idx) => (
                          <div key={idx} className="clearance-flag">
                            <span style={{ fontSize: '0.75rem' }}>
                              ≡ƒö┤ <strong>{flag.issue_type}:</strong> &ldquo;{flag.flagged_text}&rdquo;
                              {flag.suggested_rewrite && (
                                <span style={{ color: 'var(--status-success)' }}>
                                  {' ΓåÆ '}{flag.suggested_rewrite}
                                </span>
                              )}
                            </span>
                          </div>
                        ))}

                        {/* Scene status badge & Action Buttons */}
                        <div style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          marginTop: 'var(--space-lg)',
                          borderTop: '1px solid var(--border-subtle)',
                          paddingTop: 'var(--space-sm)',
                        }}>
                          <div style={{ display: 'flex', gap: 'var(--space-sm)', flexWrap: 'wrap' }}>
                            {scene.scene_number === currentScene?.scene_number && (
                              <>
                                {scene.status === 'final' && (
                                  <>
                                    <button className="sidebar__btn" style={{ padding: '0.3rem 0.6rem', fontSize: '0.75rem', minHeight: 'auto', background: 'var(--surface-sunken)' }} onClick={(e) => { e.stopPropagation(); handleSend(`Perform a Table Read for Scene ${scene.scene_number}`); }}>≡ƒÄÖ∩╕Å Table Read</button>
                                    <button className="sidebar__btn" style={{ padding: '0.3rem 0.6rem', fontSize: '0.75rem', minHeight: 'auto', background: 'var(--surface-sunken)' }} onClick={(e) => { e.stopPropagation(); handleSend(`Visualize Scene ${scene.scene_number}`); }}>≡ƒÄ¿ Visualize</button>
                                  </>
                                )}
                                <button className="sidebar__btn" style={{ padding: '0.3rem 0.6rem', fontSize: '0.75rem', minHeight: 'auto', background: 'var(--surface-sunken)' }} onClick={(e) => { e.stopPropagation(); handleSend(`Edit Scene ${scene.scene_number}`); }}>Γ£Å∩╕Å Edit</button>
                              </>
                            )}
                          </div>
                          <span style={{
                            fontSize: '0.65rem',
                            padding: '2px 8px',
                            borderRadius: 'var(--radius-full)',
                            background: scene.status === 'final' ? 'rgba(74, 222, 128, 0.15)' :
                                       scene.status === 'reviewed' ? 'rgba(96, 165, 250, 0.15)' :
                                       scene.status === 'drafted' ? 'rgba(251, 191, 36, 0.15)' :
                                       'rgba(255,255,255,0.05)',
                            color: scene.status === 'final' ? 'var(--status-success)' :
                                   scene.status === 'reviewed' ? 'var(--status-info)' :
                                   scene.status === 'drafted' ? 'var(--status-warning)' :
                                   'var(--text-muted)',
                            textTransform: 'uppercase',
                            letterSpacing: '0.06em',
                            fontWeight: 600,
                          }}>
                            {scene.status}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* ΓöÇΓöÇ Right: Agent Panel ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ */}
            <div className="panel agent-panel">
              <div className="panel__header">
                <span className="panel__title">Agents</span>
              </div>

              <div className="panel__content">
                {/* Agent Status Cards */}
                <div className="agent-cards">
                  {(agents.length > 0 ? agents : defaultAgents).map(agent => (
                    <div
                      key={agent.name}
                      className={`agent-card ${agent.status === 'working' ? 'agent-card--working' : ''}`}
                    >
                      <div className="agent-card__icon">{agent.icon || '≡ƒñû'}</div>
                      <div className="agent-card__info">
                        <div className="agent-card__name">
                          {agent.display_name.replace(/^[^\s]+ /, '')}
                        </div>
                        <div className="agent-card__status">
                          <span className={`agent-card__status-dot agent-card__status-dot--${agent.status}`} />
                          {agent.status}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>

                {/* Media Section */}
                {currentScene && (currentScene.mood_board_image || currentScene.table_read_audio) && (
                  <div className="agent-media">
                    {currentScene.mood_board_image && (
                      <>
                        <div className="agent-media__title">≡ƒû╝∩╕Å Mood Board</div>
                        <div className="mood-board-grid">
                          <img
                            className="mood-board-img"
                            src={`http://localhost:8000${currentScene.mood_board_image}`}
                            alt="Scene mood board"
                          />
                        </div>
                      </>
                    )}

                    {currentScene.table_read_audio && (
                      <>
                        <div className="agent-media__title" style={{ marginTop: 'var(--space-md)' }}>
                          ≡ƒöè Table Read
                        </div>
                        <div className="audio-player">
                          <audio
                            controls
                            src={`http://localhost:8000${currentScene.table_read_audio}`}
                          >
                            Your browser does not support audio.
                          </audio>
                        </div>
                      </>
                    )}
                  </div>
                )}

                {/* Character Bible */}
                {scriptState && Object.keys(scriptState.characters).length > 0 && (
                  <div className="agent-media">
                    <div className="agent-media__title">≡ƒôÜ Character Bible</div>
                    {Object.entries(scriptState.characters).map(([name, char]) => (
                      <div key={name} style={{
                        padding: 'var(--space-sm) var(--space-md)',
                        background: 'var(--bg-tertiary)',
                        borderRadius: 'var(--radius-sm)',
                        marginBottom: 'var(--space-xs)',
                        border: '1px solid var(--border-subtle)',
                      }}>
                        <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--accent-primary)' }}>
                          {name}
                        </div>
                        <div style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)', marginTop: '2px' }}>
                          {char.description?.slice(0, 80)}{char.description?.length > 80 ? 'ΓÇª' : ''}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </main>

          {/* ΓöÇΓöÇ Bottom: Beat Sheet Bar ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ */}
          <footer className="beat-sheet-bar">
            <span className="beat-sheet-bar__label">Beat Sheet</span>
            <div className="beat-sheet-bar__beats">
              {beats.length > 0 ? (
                beats.map(beat => (
                  <button
                    key={beat.beat_number}
                    className={`beat-chip beat-chip--${beat.status} ${activeBeat === beat.beat_number ? 'beat-chip--active' : ''}`}
                    onClick={() => setActiveBeat(beat.beat_number)}
                    title={`${beat.title}: ${beat.description.slice(0, 100)}`}
                  >
                    {beat.beat_number}. {beat.title}
                  </button>
                ))
              ) : (
                <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                  No beat sheet yet ΓÇö enter a pitch to get started
                </span>
              )}
            </div>
            <div className="beat-sheet-bar__meta">
              {scriptState && (
                <>
                  <span>≡ƒôä {scriptState.metadata.page_count} pg</span>
                  <span>ΓÅ▒ {scriptState.metadata.estimated_runtime_minutes} min</span>
                  <span>≡ƒÄ¡ {Object.keys(scriptState.characters).length} chars</span>
                </>
              )}
            </div>
          </footer>
        </>
      )}
    </div>
  );
}

// ΓöÇΓöÇ Default agent list (before backend connects) ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ

const defaultAgents: AgentStatus[] = [
  { name: 'Showrunner', display_name: '≡ƒÄ¼ Showrunner', status: 'idle', description: 'Coordinates all agents', last_active: null, icon: '≡ƒÄ¼' },
  { name: 'StoryArchitect', display_name: '≡ƒôÉ Story Architect', status: 'idle', description: 'Generates beat sheets', last_active: null, icon: '≡ƒôÉ' },
  { name: 'DialogueSpecialist', display_name: 'Γ£ì∩╕Å Dialogue Specialist', status: 'idle', description: 'Drafts scenes', last_active: null, icon: 'Γ£ì∩╕Å' },
  { name: 'ContinuityChecker', display_name: '≡ƒöì Continuity Checker', status: 'idle', description: 'Verifies consistency', last_active: null, icon: '≡ƒöì' },
  { name: 'ResearchAgent', display_name: '≡ƒîÉ Research Agent', status: 'idle', description: 'Fact-checks claims', last_active: null, icon: '≡ƒîÉ' },
  { name: 'RightsClearance', display_name: 'ΓÜû∩╕Å Rights & Clearance', status: 'idle', description: 'Flags legal issues', last_active: null, icon: 'ΓÜû∩╕Å' },
  { name: 'Visualizer', display_name: '≡ƒÄ¿ Visualizer', status: 'idle', description: 'Generates concept art', last_active: null, icon: '≡ƒÄ¿' },
  { name: 'TableRead', display_name: '≡ƒÄÖ∩╕Å Table Read', status: 'idle', description: 'Performs TTS audio', last_active: null, icon: '≡ƒÄÖ∩╕Å' },
];

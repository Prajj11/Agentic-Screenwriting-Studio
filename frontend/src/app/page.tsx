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
import { AppShell } from '@/components/AppShell';
import { Dashboard } from '@/components/Dashboard';
import { ChatPanel, type ChatMessage } from '@/components/ChatPanel';
import { AgentStatusPanel } from '@/components/AgentStatus';
import { ScriptWorkspace } from '@/components/ScriptWorkspace';
import { BeatSheet } from '@/components/BeatSheet';
import { CharacterBible } from '@/components/CharacterBible';
import { MediaLab } from '@/components/MediaLab';

// ── Types ─────────────────────────────────────────────────────────────



// ── Quick Action Presets ───────────────────────────────────────────────



// ── Main Page Component ────────────────────────────────────────────────

export default function StudioPage() {
  // View state
  const [view, setView] = useState<'dashboard' | 'project'>('dashboard');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<'script' | 'beats' | 'characters' | 'media'>('script');
  const [mobileSection, setMobileSection] = useState<'chat' | 'workspace' | 'agents'>('chat');

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

      // Smart auto-tab switching based on generated content
      const textLower = (message + ' ' + (response.response_text || '')).toLowerCase();
      if (textLower.includes('/api/media/videos/') || textLower.includes('/api/media/images/') || textLower.includes('visualize') || textLower.includes('video') || textLower.includes('concept art') || textLower.includes('portrait')) {
        setActiveTab('media');
        setMobileSection('workspace');
      } else if (textLower.includes('beat sheet') || textLower.includes('story architect') || textLower.includes('beat')) {
        setActiveTab('beats');
        setMobileSection('workspace');
      } else if (textLower.includes('character bible') || textLower.includes('character profile')) {
        setActiveTab('characters');
        setMobileSection('workspace');
      } else if (textLower.includes('draft scene') || textLower.includes('dialogue specialist') || textLower.includes('screenplay')) {
        setActiveTab('script');
        setMobileSection('workspace');
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
    <AppShell
      view={view}
      sidebarOpen={sidebarOpen}
      setSidebarOpen={setSidebarOpen}
      onBackToDashboard={handleBackToDashboard}
      onAction={handleSend}
      projectTitle={scriptState?.title}
      connected={connected}
      isLoading={isLoading}
      chHealth={chHealth}
      activeTab={activeTab}
      setActiveTab={setActiveTab}
    >
      {view === 'dashboard' ? (
        <Dashboard
          projects={projects}
          pinnedProjects={pinnedProjects}
          deleteConfirm={deleteConfirm}
          onNewProject={() => {
            setProjectId(null);
            setMessages([]);
            setScriptState(null);
            setView('project');
          }}
          onOpenProject={handleOpenProject}
          onPinProject={handlePinProject}
          onDeleteProject={handleDeleteProject}
          onSetDeleteConfirm={setDeleteConfirm}
        />
      ) : (
        <main className="studio-main">
          {/* Mobile Section Switcher (visible on screens <= 1024px) */}
          <div className="mobile-section-nav" role="tablist" aria-label="Studio views">
            <button
              type="button"
              role="tab"
              aria-selected={mobileSection === 'chat'}
              className={`mobile-section-btn ${mobileSection === 'chat' ? 'mobile-section-btn--active' : ''}`}
              onClick={() => setMobileSection('chat')}
            >
              <span className="mobile-section-btn__icon">💬</span>
              <span className="mobile-section-btn__text">Writers&apos; Room</span>
              {messages.length > 0 && (
                <span className="mobile-section-btn__count">{messages.length}</span>
              )}
            </button>
            
            <button
              type="button"
              role="tab"
              aria-selected={mobileSection === 'workspace'}
              className={`mobile-section-btn ${mobileSection === 'workspace' ? 'mobile-section-btn--active' : ''}`}
              onClick={() => setMobileSection('workspace')}
            >
              <span className="mobile-section-btn__icon">
                {activeTab === 'script' ? '📜' : activeTab === 'beats' ? '📐' : activeTab === 'characters' ? '👥' : '🎥'}
              </span>
              <span className="mobile-section-btn__text">Workspace</span>
              <span className="mobile-section-btn__tag">{activeTab}</span>
            </button>
            
            <button
              type="button"
              role="tab"
              aria-selected={mobileSection === 'agents'}
              className={`mobile-section-btn ${mobileSection === 'agents' ? 'mobile-section-btn--active' : ''}`}
              onClick={() => setMobileSection('agents')}
            >
              <span className="mobile-section-btn__icon">🤖</span>
              <span className="mobile-section-btn__text">AI Team</span>
              {agents.some(a => a.status === 'working') ? (
                <span className="mobile-section-btn__pulse" title="Agents working" />
              ) : (
                <span className="mobile-section-btn__count">{agents.length || 8}</span>
              )}
            </button>
          </div>

          {/* Slot 1: Writers' Room Chat */}
          <div className={`studio-panel-slot studio-panel-slot--chat ${mobileSection === 'chat' ? 'studio-panel-slot--active' : ''}`}>
            <ChatPanel 
              messages={messages} 
              isLoading={isLoading} 
              onSend={handleSend} 
              onSelectTab={(tab) => {
                setActiveTab(tab);
                setMobileSection('workspace');
              }}
            />
          </div>

          {/* Slot 2: Studio Workspace */}
          <div className={`studio-panel-slot studio-panel-slot--workspace ${mobileSection === 'workspace' ? 'studio-panel-slot--active' : ''}`}>
            <div className="workspace-subnav">
              <button
                type="button"
                className={`workspace-subnav-btn ${activeTab === 'script' ? 'workspace-subnav-btn--active' : ''}`}
                onClick={() => setActiveTab('script')}
              >
                📜 Script
              </button>
              <button
                type="button"
                className={`workspace-subnav-btn ${activeTab === 'beats' ? 'workspace-subnav-btn--active' : ''}`}
                onClick={() => setActiveTab('beats')}
              >
                📐 Beats {beats.length > 0 ? `(${beats.length})` : ''}
              </button>
              <button
                type="button"
                className={`workspace-subnav-btn ${activeTab === 'characters' ? 'workspace-subnav-btn--active' : ''}`}
                onClick={() => setActiveTab('characters')}
              >
                👥 Characters {Object.keys(scriptState?.characters || {}).length > 0 ? `(${Object.keys(scriptState?.characters || {}).length})` : ''}
              </button>
              <button
                type="button"
                className={`workspace-subnav-btn ${activeTab === 'media' ? 'workspace-subnav-btn--active' : ''}`}
                onClick={() => setActiveTab('media')}
              >
                🎥 Media Lab
              </button>
            </div>

            <div className="workspace-container" style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', background: 'var(--bg-primary)', width: '100%', height: '100%' }}>
               {activeTab === 'script' && (
                  <ScriptWorkspace 
                    scriptState={scriptState} 
                    currentScene={currentScene} 
                    activeScene={activeScene}
                    setActiveScene={setActiveScene}
                    onAction={handleSend}
                  />
               )}
               {activeTab === 'beats' && (
                  <BeatSheet 
                    beats={beats}
                    onDraftScene={(beatNum) => {
                      handleSend(`Draft scene for beat ${beatNum}`);
                      setMobileSection('chat');
                    }}
                    isLoading={isLoading}
                  />
               )}
               {activeTab === 'characters' && (
                  <CharacterBible 
                    characters={scriptState?.characters || {}}
                  />
               )}
               {activeTab === 'media' && (
                  <MediaLab
                    projectId={projectId}
                    scenes={scriptState?.scenes || []}
                    characters={scriptState?.characters || {}}
                    mediaAnalyses={scriptState?.media_analyses || []}
                    activeSceneNumber={currentScene?.scene_number || 0}
                    onAction={handleSend}
                  />
               )}
            </div>
          </div>

          {/* Slot 3: AI Team Status */}
          <div className={`studio-panel-slot studio-panel-slot--agents ${mobileSection === 'agents' ? 'studio-panel-slot--active' : ''}`}>
            <AgentStatusPanel agents={agents} />
          </div>
        </main>
      )}
    </AppShell>
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

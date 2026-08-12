'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import {
  sendMessage,
  getScriptState,
  getAgentStatuses,
  getClickHouseHealth,
  recoverSession,
  persistProjectId,
  loadPersistedProjectId,
  type ChatResponse,
  type ScriptState,
  type Scene,
  type Beat,
  type AgentStatus,
  type ClickHouseHealth,
} from '@/lib/api';
import { useWebSocket, type WSEvent } from '@/hooks/useWebSocket';

// ── Types ────────────────────────────────────────────────────────────

interface ChatMessage {
  id: string;
  role: 'user' | 'agent';
  text: string;
  agent?: string;
  timestamp: string;
}

// ── Quick Action Presets ─────────────────────────────────────────────

const QUICK_ACTIONS = [
  { label: '🎬 New Pitch', prompt: 'I have a pitch: ' },
  { label: '📐 Beat Sheet', prompt: 'Generate the beat sheet for this story' },
  { label: '✍️ Draft Scene', prompt: 'Draft the next scene from the beat sheet' },
  { label: '🔍 Check Continuity', prompt: 'Run a continuity check on the latest scene' },
  { label: '🎙️ Table Read', prompt: 'Perform a table read of the latest scene' },
  { label: '🎨 Visualize', prompt: 'Generate a mood board for the latest scene' },
  { label: '⚖️ Clearance Check', prompt: 'Run a rights and clearance check on the latest scene' },
  { label: '🌐 Research', prompt: 'Research: ' },
];

// ── Main Page Component ──────────────────────────────────────────────

export default function StudioPage() {
  // State
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
      // Refresh agent statuses
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

  // ── Session recovery on mount ────────────────────────────────────
  // Restore project_id from sessionStorage so a page refresh never loses state.
  useEffect(() => {
    const storedId = loadPersistedProjectId();
    if (!storedId) return;

    setProjectId(storedId);

    // Warm up the DB-backed ADK session so the next chat message succeeds
    recoverSession(storedId)
      .then(() => {
        // Also reload the script state so the UI populates after refresh
        return getScriptState(storedId);
      })
      .then(setScriptState)
      .catch((err) =>
        console.warn('Session recovery failed (non-fatal):', err)
      );
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // run once on mount

  // Refresh script state after agent response
  const refreshScriptState = useCallback(async (pid: string) => {
    try {
      const state = await getScriptState(pid);
      setScriptState(state);
    } catch (e) {
      console.warn('Failed to refresh script state:', e);
    }
  }, []);

  // ── Send Message ────────────────────────────────────────────────

  const handleSend = useCallback(async (text?: string) => {
    const message = text || input.trim();
    if (!message || isLoading) return;

    setInput('');
    setIsLoading(true);

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
      const errMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'agent',
        text: `⚠️ Connection error. Make sure the backend is running on http://localhost:8000\n\nError: ${error instanceof Error ? error.message : 'Unknown error'}`,
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

  // ── Current Scene ───────────────────────────────────────────────

  const currentScene: Scene | null = scriptState?.scenes?.[activeScene] || null;
  const beats: Beat[] = scriptState?.beat_sheet || [];

  // ── Render ──────────────────────────────────────────────────────

  return (
    <div className="studio-layout">
      {/* ── Header ──────────────────────────────────────────────── */}
      <header className="studio-header">
        <div className="studio-header__brand">
          <span className="studio-header__icon">🎬</span>
          <h1 className="studio-header__title">Agentic Screenwriting Studio</h1>
        </div>
        <div className="studio-header__project">
          <span className="studio-header__project-name">
            {scriptState?.title || 'No Project'}
          </span>
          <div className="studio-header__status-badges">
            <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
              {connected ? '🟢 Live' : '🔴 Offline'}
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
                    ? `ClickHouse: ${chHealth.clickhouse.host} — ${chHealth.clickhouse.scenes_indexed ?? 0} scenes, ${chHealth.clickhouse.facts_indexed ?? 0} facts indexed`
                    : chHealth.clickhouse.status === 'not_configured'
                    ? 'ClickHouse not configured — using local ChromaDB'
                    : `ClickHouse error: ${chHealth.clickhouse.error}`
                }
              >
                {chHealth.clickhouse.status === 'connected' ? '🟢' : chHealth.clickhouse.status === 'not_configured' ? '🟡' : '🔴'}
                {' '}ClickHouse
              </span>
            )}
          </div>
        </div>
      </header>

      {/* ── Main Content ────────────────────────────────────────── */}
      <main className="studio-main">
        {/* ── Left: Chat Panel ──────────────────────────────────── */}
        <div className="panel chat-panel">
          <div className="panel__header">
            <span className="panel__title">Writers' Room</span>
          </div>

          {/* Messages */}
          <div className="panel__content">
            <div className="chat-messages">
              {messages.length === 0 && (
                <div style={{ padding: 'var(--space-lg)', textAlign: 'center' }}>
                  <p style={{ fontSize: '1.5rem', marginBottom: 'var(--space-md)' }}>🎬</p>
                  <p style={{ color: 'var(--text-secondary)', fontSize: '0.88rem', lineHeight: 1.7 }}>
                    Welcome to the Writers&apos; Room.<br />
                    Start with a pitch, and your AI team will build your screenplay.
                  </p>
                </div>
              )}

              {messages.map(msg => (
                <div
                  key={msg.id}
                  className={`chat-message chat-message--${msg.role}`}
                >
                  <div className={`chat-message__author ${msg.role === 'agent' ? 'chat-message__author--agent' : ''}`}>
                    {msg.role === 'user' ? '👤 You' : `🎬 ${msg.agent || 'Agent'}`}
                  </div>
                  <div className="chat-message__text">{msg.text}</div>
                </div>
              ))}

              {isLoading && (
                <div className="chat-message chat-message--agent">
                  <div className="chat-message__author chat-message__author--agent">
                    🎬 Showrunner
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

          {/* Quick Actions */}
          <div className="quick-actions">
            {QUICK_ACTIONS.map((action) => (
              <button
                key={action.label}
                className="quick-action-btn"
                onClick={() => {
                  if (action.prompt.endsWith(': ')) {
                    setInput(action.prompt);
                    inputRef.current?.focus();
                  } else {
                    handleSend(action.prompt);
                  }
                }}
                disabled={isLoading}
              >
                {action.label}
              </button>
            ))}
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
                ▶
              </button>
            </div>
          </div>
        </div>

        {/* ── Center: Script Editor ─────────────────────────────── */}
        <div className="panel script-editor">
          <div className="panel__header">
            <span className="panel__title">
              Script{currentScene ? ` — Scene ${currentScene.scene_number}` : ''}
            </span>
            {scriptState && (
              <span style={{ fontSize: '0.72rem', color: 'var(--text-tertiary)' }}>
                {scriptState.metadata.total_scenes} scenes · {scriptState.metadata.page_count} pages
              </span>
            )}
          </div>

          <div className="panel__content">
            {!scriptState || scriptState.scenes.length === 0 ? (
              <div className="script-empty">
                <div className="script-empty__icon">📝</div>
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
                          ⚠️ <strong>Continuity:</strong> {issue.description}
                        </span>
                      </div>
                    ))}

                    {/* Clearance Flags */}
                    {scene.clearance_flags?.filter(f => !f.resolved).map((flag, idx) => (
                      <div key={idx} className="clearance-flag">
                        <span style={{ fontSize: '0.75rem' }}>
                          🔴 <strong>{flag.issue_type}:</strong> &ldquo;{flag.flagged_text}&rdquo;
                          {flag.suggested_rewrite && (
                            <span style={{ color: 'var(--status-success)' }}>
                              {' → '}{flag.suggested_rewrite}
                            </span>
                          )}
                        </span>
                      </div>
                    ))}

                    {/* Scene status badge */}
                    <div style={{
                      display: 'flex',
                      justifyContent: 'flex-end',
                      marginTop: 'var(--space-sm)',
                    }}>
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

        {/* ── Right: Agent Panel ────────────────────────────────── */}
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
                  <div className="agent-card__icon">{agent.icon || '🤖'}</div>
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
                    <div className="agent-media__title">🖼️ Mood Board</div>
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
                      🔊 Table Read
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
                <div className="agent-media__title">📚 Character Bible</div>
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
                      {char.description?.slice(0, 80)}{char.description?.length > 80 ? '…' : ''}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </main>

      {/* ── Bottom: Beat Sheet Bar ──────────────────────────────── */}
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
              No beat sheet yet — enter a pitch to get started
            </span>
          )}
        </div>
        <div className="beat-sheet-bar__meta">
          {scriptState && (
            <>
              <span>📄 {scriptState.metadata.page_count} pg</span>
              <span>⏱ {scriptState.metadata.estimated_runtime_minutes} min</span>
              <span>🎭 {Object.keys(scriptState.characters).length} chars</span>
            </>
          )}
        </div>
      </footer>
    </div>
  );
}

// ── Default agent list (before backend connects) ─────────────────────

const defaultAgents: AgentStatus[] = [
  { name: 'Showrunner', display_name: '🎬 Showrunner', status: 'idle', description: 'Coordinates all agents', last_active: null, icon: '🎬' },
  { name: 'StoryArchitect', display_name: '📐 Story Architect', status: 'idle', description: 'Generates beat sheets', last_active: null, icon: '📐' },
  { name: 'DialogueSpecialist', display_name: '✍️ Dialogue Specialist', status: 'idle', description: 'Drafts scenes', last_active: null, icon: '✍️' },
  { name: 'ContinuityChecker', display_name: '🔍 Continuity Checker', status: 'idle', description: 'Verifies consistency', last_active: null, icon: '🔍' },
  { name: 'ResearchAgent', display_name: '🌐 Research Agent', status: 'idle', description: 'Fact-checks claims', last_active: null, icon: '🌐' },
  { name: 'RightsClearance', display_name: '⚖️ Rights & Clearance', status: 'idle', description: 'Flags legal issues', last_active: null, icon: '⚖️' },
  { name: 'Visualizer', display_name: '🎨 Visualizer', status: 'idle', description: 'Generates concept art', last_active: null, icon: '🎨' },
  { name: 'TableRead', display_name: '🎙️ Table Read', status: 'idle', description: 'Performs TTS audio', last_active: null, icon: '🎙️' },
];

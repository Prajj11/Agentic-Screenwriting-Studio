import { useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ChatInput } from './ChatInput';

export interface ChatMessage {
  id: string;
  role: 'user' | 'agent';
  text: string;
  agent?: string;
  timestamp: string;
}

interface ChatPanelProps {
  messages: ChatMessage[];
  isLoading: boolean;
  onSend: (text: string) => void;
  onSelectTab?: (tab: 'script' | 'beats' | 'characters' | 'media') => void;
}

export function ChatPanel({ messages, isLoading, onSend, onSelectTab }: ChatPanelProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div className="panel chat-panel" style={{ display: 'flex', flexDirection: 'column', height: '100%', background: 'var(--glass-panel)' }}>
      <div className="panel__header">
        <span className="panel__title">🤖 Showrunner Assistant</span>
      </div>

      <div className="panel__content" style={{ flex: 1, overflowY: 'auto' }}>
        <div className="chat-messages" style={{ padding: 'var(--space-md)' }}>
          {messages.length === 0 && (
            <div style={{ padding: 'var(--space-lg)', textAlign: 'center' }}>
              <p style={{ fontSize: '1.5rem', marginBottom: 'var(--space-md)' }}>🎬</p>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.88rem', lineHeight: 1.7 }}>
                Welcome to the Writers&apos; Room.<br />
                Start with a pitch, and your AI team will build your screenplay.
              </p>
            </div>
          )}

          {messages.map((msg, index) => (
            <div key={msg.id} className={`chat-message chat-message--${msg.role}`} style={{ marginBottom: 'var(--space-md)' }}>
              <div className={`chat-message__author ${msg.role === 'agent' ? 'chat-message__author--agent' : ''}`}>
                {msg.role === 'user' ? '👤 You' : `🎬 ${msg.agent || 'Agent'}`}
              </div>
              
              {msg.role === 'agent' ? (
                <div className="markdown-body" style={{ fontSize: '0.95rem', lineHeight: 1.6, color: 'var(--text-primary)' }}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {msg.text}
                  </ReactMarkdown>

                  {/* Compact Video Media Badge */}
                  {msg.text.includes('/api/media/videos/') && (
                    <div style={{ marginTop: 'var(--space-md)', padding: 'var(--space-sm) var(--space-md)', background: 'var(--bg-tertiary)', border: '1px solid var(--border-accent)', borderRadius: 'var(--radius-md)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--space-sm)' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.82rem', color: 'var(--accent-primary)', fontWeight: 600 }}>
                        <span>🎬</span> Video Performance Generated
                      </div>
                      <button
                        className="sidebar__btn"
                        style={{ width: 'auto', padding: '0.3rem 0.7rem', fontSize: '0.75rem', background: 'var(--accent-primary)', color: '#fff', border: 'none' }}
                        onClick={() => onSelectTab?.('media')}
                      >
                        ▶ Open Media Lab
                      </button>
                    </div>
                  )}

                  {/* Compact Image Media Badge */}
                  {msg.text.includes('/api/media/images/') && !msg.text.includes('/api/media/videos/') && (
                    <div style={{ marginTop: 'var(--space-md)', padding: 'var(--space-sm) var(--space-md)', background: 'var(--bg-tertiary)', border: '1px solid var(--border-accent)', borderRadius: 'var(--radius-md)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--space-sm)' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.82rem', color: 'var(--accent-secondary)', fontWeight: 600 }}>
                        <span>🖼️</span> Visual Concept Art Created
                      </div>
                      <button
                        className="sidebar__btn"
                        style={{ width: 'auto', padding: '0.3rem 0.7rem', fontSize: '0.75rem', background: 'var(--surface-sunken)' }}
                        onClick={() => onSelectTab?.('media')}
                      >
                        🖼️ View in Center Canvas
                      </button>
                    </div>
                  )}

                  {/* Compact Audio Media Badge */}
                  {msg.text.includes('/api/media/audio/') && (
                    <div style={{ marginTop: 'var(--space-md)', padding: 'var(--space-sm) var(--space-md)', background: 'var(--bg-tertiary)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--space-sm)' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.82rem', color: 'var(--text-secondary)', fontWeight: 600 }}>
                        <span>🎵</span> Audio Performance Ready
                      </div>
                      <button
                        className="sidebar__btn"
                        style={{ width: 'auto', padding: '0.3rem 0.7rem', fontSize: '0.75rem', background: 'var(--surface-sunken)' }}
                        onClick={() => onSelectTab?.('script')}
                      >
                        📜 View in Script
                      </button>
                    </div>
                  )}
                </div>
              ) : (
                <div className="chat-message__text" style={{ fontSize: '0.95rem', lineHeight: 1.6 }}>{msg.text}</div>
              )}

              {/* Action Buttons */}
              {msg.role === 'agent' && index === messages.length - 1 && !isLoading && (
                <div className="chat-message__actions" style={{ marginTop: 'var(--space-md)', display: 'flex', gap: 'var(--space-sm)', flexWrap: 'wrap' }}>
                  <button className="sidebar__btn" style={{ padding: '0.4rem 0.8rem', fontSize: '0.8rem', minHeight: 'auto', background: 'var(--surface-sunken)', width: 'auto' }} onClick={() => onSend("Generate the beat sheet")}>📐 Beat Sheet</button>
                  <button className="sidebar__btn" style={{ padding: '0.4rem 0.8rem', fontSize: '0.8rem', minHeight: 'auto', background: 'var(--surface-sunken)', width: 'auto' }} onClick={() => onSend("Draft the next scene")}>✍️ Draft Scene</button>
                  <button className="sidebar__btn" style={{ padding: '0.4rem 0.8rem', fontSize: '0.8rem', minHeight: 'auto', background: 'var(--surface-sunken)', width: 'auto' }} onClick={() => onSend("Check continuity for the latest scene")}>🔍 Check Continuity</button>
                  <button className="sidebar__btn" style={{ padding: '0.4rem 0.8rem', fontSize: '0.8rem', minHeight: 'auto', background: 'var(--surface-sunken)', width: 'auto' }} onClick={() => onSend("Perform a Table Read of the latest scene")}>🎙️ Table Read</button>
                  <button className="sidebar__btn" style={{ padding: '0.4rem 0.8rem', fontSize: '0.8rem', minHeight: 'auto', background: 'var(--surface-sunken)', width: 'auto' }} onClick={() => onSend("Visualize the latest scene")}>🎨 Visualize Scene</button>
                </div>
              )}
            </div>
          ))}

          {isLoading && (
            <div className="chat-message chat-message--agent">
              <div className="chat-message__author chat-message__author--agent">🎬 Showrunner</div>
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

      <ChatInput onSend={onSend} isLoading={isLoading} />
    </div>
  );
}

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
}

export function ChatPanel({ messages, isLoading, onSend }: ChatPanelProps) {
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

                  {/* Inline Video Player */}
                  {msg.text.includes('/api/media/videos/') && (() => {
                    const match = msg.text.match(/\/api\/media\/videos\/[a-zA-Z0-9_\-\.]+\.mp4/);
                    if (!match) return null;
                    const videoUrl = match[0].startsWith('http') ? match[0] : `http://localhost:8000${match[0]}`;
                    return (
                      <div style={{ marginTop: 'var(--space-md)', borderRadius: 'var(--radius-md)', overflow: 'hidden', border: '1px solid var(--border-subtle)', background: '#000' }}>
                        <video
                          controls
                          src={videoUrl}
                          style={{ width: '100%', maxHeight: '320px', display: 'block' }}
                        />
                      </div>
                    );
                  })()}

                  {/* Inline Image Viewer */}
                  {msg.text.includes('/api/media/images/') && !msg.text.includes('/api/media/videos/') && (() => {
                    const match = msg.text.match(/\/api\/media\/images\/[a-zA-Z0-9_\-\.]+\.(jpg|png|webp|jpeg)/i);
                    if (!match) return null;
                    const imgUrl = match[0].startsWith('http') ? match[0] : `http://localhost:8000${match[0]}`;
                    return (
                      <div style={{ marginTop: 'var(--space-md)', borderRadius: 'var(--radius-md)', overflow: 'hidden', border: '1px solid var(--border-subtle)' }}>
                        <img
                          src={imgUrl}
                          alt="Generated Visual"
                          style={{ width: '100%', maxHeight: '350px', objectFit: 'cover', display: 'block' }}
                        />
                      </div>
                    );
                  })()}

                  {/* Inline Audio Player */}
                  {msg.text.includes('/api/media/audio/') && (() => {
                    const match = msg.text.match(/\/api\/media\/audio\/[a-zA-Z0-9_\-\.]+\.(wav|mp3|ogg)/i);
                    if (!match) return null;
                    const audioUrl = match[0].startsWith('http') ? match[0] : `http://localhost:8000${match[0]}`;
                    return (
                      <div style={{ marginTop: 'var(--space-md)', background: 'var(--surface-sunken)', padding: 'var(--space-sm)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)' }}>
                        <audio controls src={audioUrl} style={{ width: '100%', height: '36px' }} />
                      </div>
                    );
                  })()}
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

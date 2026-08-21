import { Scene, ScriptState, MediaAnalysis } from '@/lib/api';

interface ScriptWorkspaceProps {
  scriptState: ScriptState | null;
  currentScene: Scene | null;
  activeScene: number;
  setActiveScene: (index: number) => void;
  onAction: (prompt: string) => void;
}

export function ScriptWorkspace({ scriptState, currentScene, activeScene, setActiveScene, onAction }: ScriptWorkspaceProps) {
  if (!scriptState || scriptState.scenes.length === 0) {
    return (
      <div className="script-empty" style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 'var(--space-2xl)', textAlign: 'center' }}>
        <div className="script-empty__icon" style={{ fontSize: '4.5rem', marginBottom: 'var(--space-lg)', opacity: 0.4 }}>📜</div>
        <h2 className="script-empty__title" style={{ fontFamily: 'var(--font-display)', fontSize: '1.8rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 'var(--space-sm)' }}>Your Script Awaits</h2>
        <p className="script-empty__subtitle" style={{ fontSize: '1rem', color: 'var(--text-tertiary)', maxWidth: '440px', lineHeight: 1.6 }}>
          Start by entering a pitch in the Writers&apos; Room panel.
          The Story Architect will generate a beat sheet, then the Dialogue Specialist will draft each scene.
        </p>
      </div>
    );
  }

  return (
    <div className="script-content" style={{ padding: 'var(--space-xl) var(--space-2xl)', fontFamily: 'var(--font-mono)', fontSize: '0.95rem', lineHeight: 1.8, maxWidth: '720px', margin: '0 auto' }}>
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
          onClick={() => {
            const index = scriptState.scenes.findIndex(s => s.scene_number === scene.scene_number);
            setActiveScene(index);
          }}
        >
          {/* Scene Experience (Video + Image + Audio) */}
          {(() => {
            const videoItem = scene.concept_video || scriptState.media_analyses?.find((m: MediaAnalysis) => m.scene_number === scene.scene_number && m.media_type === 'video')?.media_url;
            const hasMedia = videoItem || scene.mood_board_image || scene.table_read_audio || scene.soundtrack_audio;
            if (scene.scene_number !== currentScene?.scene_number || !hasMedia) return null;

            return (
              <div className="scene-experience" style={{ marginBottom: 'var(--space-xl)', background: 'var(--bg-tertiary)', padding: 'var(--space-md)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)' }}>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--accent-primary)', marginBottom: 'var(--space-sm)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>🎬 Scene Experience</div>
                
                {videoItem && (
                  <div className="scene-media-video" style={{ marginBottom: 'var(--space-md)' }}>
                    <div style={{ fontSize: '0.7rem', color: 'var(--accent-primary)', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>🎥 Video Performance</div>
                    <video
                      controls
                      src={videoItem.startsWith('http') ? videoItem : `http://localhost:8000${videoItem}`}
                      style={{
                        width: '100%',
                        maxHeight: '360px',
                        borderRadius: 'var(--radius-sm)',
                        background: '#000',
                        display: 'block',
                        boxShadow: '0 4px 16px rgba(0,0,0,0.4)',
                      }}
                    />
                  </div>
                )}

                {scene.mood_board_image && (
                  <div className="scene-media-image" style={{ marginBottom: 'var(--space-md)' }}>
                    <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', marginBottom: '4px', textTransform: 'uppercase' }}>🖼️ Concept Art</div>
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

                {(scene.table_read_audio || scene.soundtrack_audio) && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-sm)' }}>
                    {scene.soundtrack_audio && (
                      <div className="scene-media-audio">
                        <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', marginBottom: '2px' }}>🎵 Scene Soundtrack</div>
                        <audio
                          controls
                          src={`http://localhost:8000${scene.soundtrack_audio}`}
                          style={{ width: '100%', height: '32px' }}
                        >
                          Your browser does not support audio.
                        </audio>
                      </div>
                    )}
                    {scene.table_read_audio && (
                      <div className="scene-media-audio">
                        <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', marginBottom: '2px' }}>🎙️ Table Read Dialogue</div>
                        <audio
                          controls
                          src={`http://localhost:8000${scene.table_read_audio}`}
                          style={{ width: '100%', height: '32px' }}
                        >
                          Your browser does not support audio.
                        </audio>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })()}

          {/* Slugline */}
          {scene.slugline && (
            <div className="screenplay-slugline" style={{ fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-primary)', marginTop: 'var(--space-xl)', marginBottom: 'var(--space-md)', letterSpacing: '0.04em', background: 'linear-gradient(90deg, rgba(255,255,255,0.05) 0%, transparent 100%)', padding: '4px 8px', borderRadius: '4px' }}>
              {scene.slugline}
            </div>
          )}

          {/* Action Lines */}
          {scene.action_lines && (
            <div className="screenplay-action" style={{ color: 'var(--text-secondary)', marginBottom: 'var(--space-md)', textAlign: 'justify' }}>
              {scene.action_lines}
            </div>
          )}

          {/* Dialogue */}
          {scene.dialogue?.map((dl, idx) => (
            <div key={idx}>
              <div className="screenplay-character" style={{ textAlign: 'center', fontWeight: 700, textTransform: 'uppercase', color: 'var(--accent-secondary)', marginTop: 'var(--space-lg)', marginBottom: '2px', letterSpacing: '0.08em' }}>
                {dl.character}
              </div>
              {dl.parenthetical && (
                <div className="screenplay-parenthetical" style={{ textAlign: 'center', color: 'var(--text-tertiary)', fontStyle: 'italic', fontSize: '0.9em', marginBottom: '2px' }}>
                  ({dl.parenthetical})
                </div>
              )}
              <div className="screenplay-dialogue" style={{ textAlign: 'center', color: 'var(--text-primary)', maxWidth: '440px', margin: '0 auto var(--space-md)' }}>
                {dl.line}
              </div>
            </div>
          ))}

          {/* Continuity Issues */}
          {scene.continuity_issues?.filter(i => !i.resolved).map((issue, idx) => (
            <div key={idx} className="continuity-flag" style={{ background: 'rgba(245, 166, 35, 0.08)', borderLeft: '3px solid var(--status-warning)', padding: 'var(--space-sm) var(--space-md)', borderRadius: '0 var(--radius-md) var(--radius-md) 0', marginTop: 'var(--space-sm)', boxShadow: 'inset 0 0 20px rgba(0,0,0,0.2)' }}>
              <span style={{ fontSize: '0.75rem' }}>
                ⚠️ <strong>Continuity:</strong> {issue.description}
              </span>
            </div>
          ))}

          {/* Clearance Flags */}
          {scene.clearance_flags?.filter(f => !f.resolved).map((flag, idx) => (
            <div key={idx} className="clearance-flag" style={{ background: 'rgba(248, 113, 113, 0.08)', borderLeft: '3px solid var(--status-error)', padding: 'var(--space-sm) var(--space-md)', borderRadius: '0 var(--radius-md) var(--radius-md) 0', marginTop: 'var(--space-sm)' }}>
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
                      <button className="sidebar__btn" style={{ padding: '0.3rem 0.6rem', fontSize: '0.75rem', minHeight: 'auto', background: 'var(--surface-sunken)', width: 'auto' }} onClick={(e) => { e.stopPropagation(); onAction(`Perform a Table Read for Scene ${scene.scene_number}`); }}>🎙️ Table Read</button>
                      <button className="sidebar__btn" style={{ padding: '0.3rem 0.6rem', fontSize: '0.75rem', minHeight: 'auto', background: 'var(--surface-sunken)', width: 'auto' }} onClick={(e) => { e.stopPropagation(); onAction(`Visualize Scene ${scene.scene_number}`); }}>🎨 Visualize</button>
                      <button className="sidebar__btn" style={{ padding: '0.3rem 0.6rem', fontSize: '0.75rem', minHeight: 'auto', background: 'var(--surface-sunken)', width: 'auto' }} onClick={(e) => { e.stopPropagation(); onAction(`Generate soundtrack for Scene ${scene.scene_number}`); }}>🎵 Soundtrack</button>
                    </>
                  )}
                  <button className="sidebar__btn" style={{ padding: '0.3rem 0.6rem', fontSize: '0.75rem', minHeight: 'auto', background: 'var(--surface-sunken)', width: 'auto' }} onClick={(e) => { e.stopPropagation(); onAction(`Edit Scene ${scene.scene_number}`); }}>✏️ Edit</button>
                </>
              )}
            </div>
            {scene.status && (
              <span style={{
                fontSize: '0.75rem',
                textTransform: 'uppercase',
                color: scene.status === 'final' ? 'var(--status-success)' : 'var(--status-warning)',
                fontWeight: 600
              }}>
                {scene.status === 'final' ? 'FINAL ✓' : scene.status}
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

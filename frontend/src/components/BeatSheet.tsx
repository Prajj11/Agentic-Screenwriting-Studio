import { Beat } from '@/lib/api';

interface BeatSheetProps {
  beats: Beat[];
  onDraftScene: (beatId: number) => void;
  isLoading: boolean;
}

export function BeatSheet({ beats, onDraftScene, isLoading }: BeatSheetProps) {
  if (!beats || beats.length === 0) {
    return (
      <div style={{ padding: 'var(--space-2xl)', textAlign: 'center', color: 'var(--text-tertiary)' }}>
        No beat sheet yet. Ask the Showrunner to generate one!
      </div>
    );
  }

  return (
    <div className="beat-sheet-container" style={{ padding: 'var(--space-xl) var(--space-md)' }}>
      <div style={{ marginBottom: 'var(--space-xl)', textAlign: 'center' }}>
        <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.5rem', fontWeight: 700 }}>Beat Sheet</h2>
        <p style={{ color: 'var(--text-tertiary)', fontSize: '0.9rem' }}>The foundational structure of your story.</p>
      </div>
      
      <div className="beat-timeline" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-md)', maxWidth: '600px', margin: '0 auto' }}>
        {beats.map((beat, index) => (
          <div key={beat.beat_number || index} className="beat-card" style={{
            background: 'var(--glass-panel)',
            border: '1px solid var(--border-default)',
            borderRadius: 'var(--radius-md)',
            padding: 'var(--space-md)',
            boxShadow: 'var(--shadow-sm)',
            borderLeft: `4px solid ${beat.status === 'final' ? 'var(--status-success)' : beat.status === 'drafted' ? 'var(--status-warning)' : 'var(--text-muted)'}`
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 'var(--space-sm)' }}>
              <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                {String(index + 1).padStart(2, '0')} — {beat.title}
              </h3>
              <span style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 600 }}>
                {beat.status}
              </span>
            </div>
            
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', lineHeight: 1.5, marginBottom: 'var(--space-md)' }}>
              {beat.description}
            </p>
            
            {beat.status === 'planned' && (
              <button 
                className="sidebar__btn" 
                style={{ width: 'auto', padding: '0.4rem 0.8rem', fontSize: '0.8rem', background: 'rgba(255,255,255,0.05)' }}
                onClick={() => onDraftScene(beat.beat_number || index)}
                disabled={isLoading}
              >
                ✍️ Draft Scene
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

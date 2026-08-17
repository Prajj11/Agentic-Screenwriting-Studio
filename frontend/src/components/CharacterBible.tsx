interface Character {
  name: string;
  age?: number | string;
  role?: string;
  appearance?: string;
  visual_description?: string;
  reference_portrait?: string | null;
  description?: string;
  traits?: string[];
  personality?: string;
  background?: string;
  backstory?: string;
  voice?: string;
  voice_notes?: string;
  established_facts?: Record<string, string> | string[];
}

interface CharacterBibleProps {
  characters: Record<string, Character>;
}

export function CharacterBible({ characters }: CharacterBibleProps) {
  const chars = Object.values(characters || {});
  
  if (chars.length === 0) {
    return (
      <div style={{ padding: 'var(--space-2xl)', textAlign: 'center' }}>
        <h2 style={{ color: 'var(--text-secondary)', fontSize: '1.5rem', marginBottom: 'var(--space-md)' }}>👥 No characters yet</h2>
        <p style={{ color: 'var(--text-tertiary)' }}>Generate a Beat Sheet to start populating your Character Bible.</p>
      </div>
    );
  }

  return (
    <div style={{ padding: 'var(--space-xl) var(--space-md)' }}>
      <div style={{ marginBottom: 'var(--space-xl)', textAlign: 'center' }}>
        <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '1.5rem', fontWeight: 700 }}>Character Bible</h2>
        <p style={{ color: 'var(--text-tertiary)', fontSize: '0.9rem' }}>Detailed visual profiles and locked-down appearances for AI consistency.</p>
      </div>

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
        gap: 'var(--space-lg)'
      }}>
        {chars.map((char, idx) => {
          const visualDesc = char.visual_description || char.appearance || char.description || '';
          const voice = char.voice_notes || char.voice || '';
          const backstory = char.backstory || char.background || '';
          const traits = Array.isArray(char.traits) ? char.traits : [];

          return (
            <div key={idx} style={{
              background: 'var(--glass-panel)',
              border: '1px solid var(--border-default)',
              borderRadius: 'var(--radius-lg)',
              overflow: 'hidden',
              display: 'flex',
              flexDirection: 'column'
            }}>
              {char.reference_portrait && (
                <div style={{ width: '100%', height: '200px', overflow: 'hidden', position: 'relative', background: '#111' }}>
                  <img
                    src={char.reference_portrait.startsWith('/') ? `http://localhost:8000${char.reference_portrait}` : char.reference_portrait}
                    alt={`${char.name} reference portrait`}
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  />
                  <div style={{
                    position: 'absolute',
                    bottom: '8px',
                    right: '8px',
                    background: 'rgba(0,0,0,0.7)',
                    padding: '2px 8px',
                    borderRadius: '4px',
                    fontSize: '0.7rem',
                    color: '#6ee7b7'
                  }}>
                    ✓ Canonical Portrait
                  </div>
                </div>
              )}

              <div style={{ padding: 'var(--space-md)', borderBottom: '1px solid var(--border-default)', background: 'rgba(255,255,255,0.02)' }}>
                <h3 style={{ fontSize: '1.2rem', fontWeight: 700, color: 'var(--accent-primary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  👤 {char.name}
                </h3>
                <div style={{ display: 'flex', gap: 'var(--space-md)', fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '4px', flexWrap: 'wrap' }}>
                  {char.age && <span>Age: {char.age}</span>}
                  {char.role && <span>Role: {char.role}</span>}
                  {char.visual_description && <span style={{ color: '#6ee7b7' }}>🔒 Appearance Locked</span>}
                </div>
              </div>
              
              <div style={{ padding: 'var(--space-md)', flex: 1, display: 'flex', flexDirection: 'column', gap: 'var(--space-md)' }}>
                {traits.length > 0 && (
                  <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                    {traits.map((t, i) => (
                      <span key={i} style={{
                        fontSize: '0.75rem',
                        padding: '2px 8px',
                        borderRadius: '12px',
                        background: 'rgba(255,255,255,0.05)',
                        border: '1px solid var(--border-default)',
                        color: 'var(--text-secondary)'
                      }}>
                        {t}
                      </span>
                    ))}
                  </div>
                )}

                {visualDesc && (
                  <div>
                    <h4 style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: '#6ee7b7', marginBottom: '4px', fontWeight: 600 }}>
                      🎨 Visual Profile (Image Consistency)
                    </h4>
                    <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>{visualDesc}</p>
                  </div>
                )}

                {voice && (
                  <div>
                    <h4 style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: '4px', fontWeight: 600 }}>Voice & Dialogue</h4>
                    <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>{voice}</p>
                  </div>
                )}

                <details style={{ marginTop: 'auto' }}>
                  <summary style={{ fontSize: '0.8rem', color: 'var(--accent-secondary)', cursor: 'pointer', outline: 'none', fontWeight: 500 }}>
                    View Full Profile & Backstory
                  </summary>
                  <div style={{ marginTop: 'var(--space-sm)', display: 'flex', flexDirection: 'column', gap: 'var(--space-sm)' }}>
                    {backstory && (
                      <div>
                        <h4 style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: '4px', fontWeight: 600 }}>Backstory</h4>
                        <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>{backstory}</p>
                      </div>
                    )}
                    {char.established_facts && (
                      <div>
                        <h4 style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: '4px', fontWeight: 600 }}>Established Facts</h4>
                        <ul style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', paddingLeft: 'var(--space-md)', lineHeight: 1.5 }}>
                          {Array.isArray(char.established_facts)
                            ? char.established_facts.map((fact, i) => <li key={i}>{typeof fact === 'string' ? fact : JSON.stringify(fact)}</li>)
                            : Object.entries(char.established_facts).map(([k, v], i) => <li key={i}><strong>{k}:</strong> {v}</li>)
                          }
                        </ul>
                      </div>
                    )}
                  </div>
                </details>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

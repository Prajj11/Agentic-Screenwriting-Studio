interface Character {
  name: string;
  age: number;
  role: string;
  appearance: string;
  personality: string;
  background: string;
  voice: string;
  established_facts: string[];
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
        <p style={{ color: 'var(--text-tertiary)', fontSize: '0.9rem' }}>Detailed profiles maintained by your AI team.</p>
      </div>

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
        gap: 'var(--space-lg)'
      }}>
        {chars.map((char, idx) => (
          <div key={idx} style={{
            background: 'var(--glass-panel)',
            border: '1px solid var(--border-default)',
            borderRadius: 'var(--radius-lg)',
            overflow: 'hidden',
            display: 'flex',
            flexDirection: 'column'
          }}>
            <div style={{ padding: 'var(--space-md)', borderBottom: '1px solid var(--border-default)', background: 'rgba(255,255,255,0.02)' }}>
              <h3 style={{ fontSize: '1.2rem', fontWeight: 700, color: 'var(--accent-primary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                👤 {char.name}
              </h3>
              <div style={{ display: 'flex', gap: 'var(--space-md)', fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                <span>Age: {char.age}</span>
                <span>Role: {char.role}</span>
              </div>
            </div>
            
            <div style={{ padding: 'var(--space-md)', flex: 1, display: 'flex', flexDirection: 'column', gap: 'var(--space-md)' }}>
              <div>
                <h4 style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: '4px', fontWeight: 600 }}>Personality</h4>
                <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>{char.personality}</p>
              </div>
              <div>
                <h4 style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: '4px', fontWeight: 600 }}>Voice</h4>
                <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>{char.voice}</p>
              </div>
              <details style={{ marginTop: 'auto' }}>
                <summary style={{ fontSize: '0.8rem', color: 'var(--accent-secondary)', cursor: 'pointer', outline: 'none', fontWeight: 500 }}>
                  View Full Profile
                </summary>
                <div style={{ marginTop: 'var(--space-sm)', display: 'flex', flexDirection: 'column', gap: 'var(--space-sm)' }}>
                  <div>
                    <h4 style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: '4px', fontWeight: 600 }}>Appearance</h4>
                    <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>{char.appearance}</p>
                  </div>
                  <div>
                    <h4 style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: '4px', fontWeight: 600 }}>Background</h4>
                    <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>{char.background}</p>
                  </div>
                  {char.established_facts && char.established_facts.length > 0 && (
                    <div>
                      <h4 style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-tertiary)', marginBottom: '4px', fontWeight: 600 }}>Established Facts</h4>
                      <ul style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', paddingLeft: 'var(--space-md)', lineHeight: 1.5 }}>
                        {char.established_facts.map((fact, i) => <li key={i}>{fact}</li>)}
                      </ul>
                    </div>
                  )}
                </div>
              </details>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

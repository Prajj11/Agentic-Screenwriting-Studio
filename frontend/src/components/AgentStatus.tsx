import { AgentStatus as IAgentStatus } from '@/lib/api';

interface AgentStatusProps {
  agents: IAgentStatus[];
}

export function AgentStatusPanel({ agents }: AgentStatusProps) {
  return (
    <div className="panel agent-panel" style={{ background: 'var(--glass-panel)', borderRadius: 'var(--radius-lg)' }}>
      <div className="panel__header">
        <span className="panel__title">AI Team</span>
      </div>
      <div className="panel__content">
        <div className="agent-cards">
          {agents.map((agent) => {
            const isWorking = agent.status === 'working';
            return (
              <div 
                key={agent.name} 
                className={`agent-card ${isWorking ? 'agent-card--working' : ''}`}
              >
                <div className="agent-card__icon">{agent.icon}</div>
                <div className="agent-card__info">
                  <div className="agent-card__name">{agent.display_name.replace(/^[^\s]+\s/, '')}</div>
                  <div className="agent-card__status">
                    <div className={`agent-card__status-dot agent-card__status-dot--${agent.status}`} />
                    {isWorking ? 'Working...' : agent.status === 'done' ? 'Done' : 'Idle'}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

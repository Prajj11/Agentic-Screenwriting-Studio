import { ProjectListItem } from '@/lib/api';

interface DashboardProps {
  projects: ProjectListItem[];
  pinnedProjects: Set<string>;
  deleteConfirm: string | null;
  onNewProject: () => void;
  onOpenProject: (pid: string) => void;
  onPinProject: (pid: string) => void;
  onDeleteProject: (pid: string) => void;
  onSetDeleteConfirm: (pid: string | null) => void;
}

export function Dashboard({
  projects,
  pinnedProjects,
  deleteConfirm,
  onNewProject,
  onOpenProject,
  onPinProject,
  onDeleteProject,
  onSetDeleteConfirm
}: DashboardProps) {

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

  const sortedProjects = [...projects].sort((a, b) => {
    const aPinned = pinnedProjects.has(a.project_id);
    const bPinned = pinnedProjects.has(b.project_id);
    if (aPinned && !bPinned) return -1;
    if (!aPinned && bPinned) return 1;
    return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
  });

  return (
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
          onClick={onNewProject}
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
                onClick={(e) => { e.stopPropagation(); onPinProject(proj.project_id); }}
                title={pinnedProjects.has(proj.project_id) ? 'Unpin' : 'Pin'}
              >
                📌
              </button>
              <button
                className="project-card__delete"
                onClick={(e) => { e.stopPropagation(); onSetDeleteConfirm(proj.project_id); }}
                title="Delete project"
              >
                🗑️
              </button>
            </div>
            <div
              className="project-card__body"
              onClick={() => onOpenProject(proj.project_id)}
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
                    onClick={(e) => { e.stopPropagation(); onDeleteProject(proj.project_id); }}
                  >
                    Delete
                  </button>
                  <button
                    className="project-card__confirm-btn"
                    onClick={(e) => { e.stopPropagation(); onSetDeleteConfirm(null); }}
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
  );
}

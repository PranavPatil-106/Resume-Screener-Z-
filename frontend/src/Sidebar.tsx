import { useAuth } from './auth'
import './Dashboard.css'

export type AppScreen =
  | 'signin'
  | 'accept-invitation'
  | 'dashboard'
  | 'jobs'
  | 'sessions'
  | 'candidates'
  | 'users'
  | 'settings'
  | 'new-screening'

interface SidebarProps {
  activeScreen:
    | 'dashboard'
    | 'jobs'
    | 'sessions'
    | 'candidates'
    | 'users'
    | 'settings'
    | 'new-screening'
  onNavigate: (screen: AppScreen) => void
  sidebarOpen: boolean
  onCloseSidebar: () => void
}

export function Sidebar({
  activeScreen,
  onNavigate,
  sidebarOpen,
  onCloseSidebar,
}: SidebarProps) {
  const { user, isAdmin, isPrivileged, logout } = useAuth()

  const handleLogout = async () => {
    try {
      await logout()
    } finally {
      onNavigate('signin')
      onCloseSidebar()
    }
  }
  return (
    <aside className={`sidebar ${sidebarOpen ? 'sidebar-open' : ''}`}>
      <div className="sidebar-header">
        <div className="sidebar-brand">
          <div className="sidebar-logo-mark" aria-hidden="true">
            <span className="sidebar-logo-ai">AI</span>
          </div>
          <div className="brand-texts">
            <span className="brand-name">Resume Screener</span>
            <span className="brand-badge">HR Suite</span>
          </div>
        </div>
        <button
          type="button"
          className="sidebar-close-btn"
          onClick={onCloseSidebar}
          aria-label="Close navigation sidebar"
        >
          ✕
        </button>
      </div>

      <nav className="sidebar-nav" aria-label="Main Navigation">
        <div className="nav-group-label">Core</div>

        {isPrivileged && (
          <button
            type="button"
            className={`nav-item ${activeScreen === 'dashboard' ? 'nav-item-active' : ''}`}
            onClick={() => {
              onNavigate('dashboard')
              onCloseSidebar()
            }}
            aria-current={activeScreen === 'dashboard' ? 'page' : undefined}
          >
            <svg
              className="nav-icon"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <rect width="7" height="9" x="3" y="3" rx="1" />
              <rect width="7" height="5" x="14" y="3" rx="1" />
              <rect width="7" height="9" x="14" y="12" rx="1" />
              <rect width="7" height="5" x="3" y="16" rx="1" />
            </svg>
            <span>Dashboard</span>
          </button>
        )}

        <button
          type="button"
          className={`nav-item ${activeScreen === 'jobs' ? 'nav-item-active' : ''}`}
          onClick={() => {
            onNavigate('jobs')
            onCloseSidebar()
          }}
          aria-current={activeScreen === 'jobs' ? 'page' : undefined}
        >
          <svg
            className="nav-icon"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="16" x2="8" y1="13" y2="13" />
            <line x1="16" x2="8" y1="17" y2="17" />
            <line x1="10" x2="8" y1="9" y2="9" />
          </svg>
          <span>Job Descriptions</span>
        </button>

        <button
          type="button"
          className={`nav-item ${activeScreen === 'sessions' ? 'nav-item-active' : ''}`}
          onClick={() => {
            onNavigate('sessions')
            onCloseSidebar()
          }}
          aria-current={activeScreen === 'sessions' ? 'page' : undefined}
        >
          <svg
            className="nav-icon"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
            <line x1="12" y1="12" x2="12" y2="17" />
            <line x1="9" x2="15" y1="14" y2="14" />
          </svg>
          <span>Screening Sessions</span>
        </button>

        {isPrivileged && (
          <>
            <button
              type="button"
              className={`nav-item ${activeScreen === 'candidates' ? 'nav-item-active' : ''}`}
              onClick={() => {
                onNavigate('candidates')
                onCloseSidebar()
              }}
              aria-current={activeScreen === 'candidates' ? 'page' : undefined}
            >
              <svg
                className="nav-icon"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
                <circle cx="9" cy="7" r="4" />
                <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
                <path d="M16 3.13a4 4 0 0 1 0 7.75" />
              </svg>
              <span>Candidates</span>
            </button>

            <div className="nav-group-label" style={{ marginTop: '20px' }}>System</div>

            {isAdmin && (
              <button
                type="button"
                className={`nav-item ${activeScreen === 'users' ? 'nav-item-active' : ''}`}
                onClick={() => {
                  onNavigate('users')
                  onCloseSidebar()
                }}
                aria-current={activeScreen === 'users' ? 'page' : undefined}
              >
                <svg
                  className="nav-icon"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                  <circle cx="9" cy="7" r="4" />
                  <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
                  <path d="M16 3.13a4 4 0 0 1 0 7.75" />
                </svg>
                <span>Users</span>
              </button>
            )}

            <button
              type="button"
              className={`nav-item ${activeScreen === 'settings' ? 'nav-item-active' : ''}`}
              onClick={() => {
                onNavigate('settings')
                onCloseSidebar()
              }}
              aria-current={activeScreen === 'settings' ? 'page' : undefined}
            >
              <svg
                className="nav-icon"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
                <circle cx="12" cy="12" r="3" />
              </svg>
              <span>Settings</span>
            </button>
          </>
        )}
      </nav>

      {/* Sidebar Footer with Profile & Logout Action */}
      <div className="sidebar-footer">
        <div className="user-profile-card">
          <div className="user-avatar" aria-hidden="true">
            {user ? user.email.slice(0, 2).toUpperCase() : 'SP'}
          </div>
          <div className="user-info">
            <span className="user-name" title={user?.email || 'Sarah Parker'}>
              {user ? user.email : 'Sarah Parker'}
            </span>
            <span className="user-role" style={{ textTransform: 'capitalize' }}>
              {user ? user.role : 'Lead Recruiter'}
            </span>
          </div>
        </div>

        <button
          type="button"
          className="sidebar-return-btn"
          onClick={handleLogout}
          title="Sign Out"
        >
          <svg
            className="return-icon"
            viewBox="0 0 24 24"
            width="16"
            height="16"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
            <polyline points="16 17 21 12 16 7" />
            <line x1="21" x2="9" y1="12" y2="12" />
          </svg>
          <span>Sign Out</span>
        </button>
      </div>
    </aside>
  )
}

import { useState, useEffect, type ReactNode } from 'react'
import { Sidebar, type AppScreen } from './Sidebar'
import { apiFetch } from './api'
import { useAuth } from './auth'
import './Dashboard.css'
import './ScreeningSessions.css'

interface DashboardProps {
  onNavigate: (screen: AppScreen) => void
  /** Open a session's results / progress in the screening workspace. */
  onOpenSession?: (sessionId: string) => void
}

interface RecentSession {
  id: string
  name: string
  job_title: string
  resumes: number
  status: string
  percent: number | null
  created_by: string | null
  created_at: string | null
}

interface Overview {
  stats: { active_sessions: number; job_descriptions: number; resumes_processed: number; shortlisted: number }
  recent_sessions: RecentSession[]
}

function formatDisplayDate(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

// "amit.sharma@corp.com" -> "Amit"
function firstName(email?: string): string {
  const first = (email ?? '').split('@')[0].split(/[._-]/)[0]
  return first ? first.charAt(0).toUpperCase() + first.slice(1) : ''
}

const METRICS: { key: keyof Overview['stats']; label: string; icon: string; path: ReactNode }[] = [
  { key: 'active_sessions', label: 'Active Sessions', icon: 'icon-purple', path: <><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" /></> },
  { key: 'job_descriptions', label: 'Job Descriptions', icon: 'icon-emerald', path: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /></> },
  { key: 'resumes_processed', label: 'Resumes Processed', icon: 'icon-blue', path: <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="9 15 11 17 15 13" /></> },
  { key: 'shortlisted', label: 'Shortlisted Candidates', icon: 'icon-indigo', path: <><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><polyline points="16 11 18 13 22 9" /></> },
]

export function Dashboard({ onNavigate, onOpenSession }: DashboardProps) {
  const { user, isPrivileged } = useAuth()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [data, setData] = useState<Overview | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [apiError, setApiError] = useState<string | null>(null)

  const load = async () => {
    setIsLoading(true)
    setApiError(null)
    try {
      const res = await apiFetch('/api/dashboard/overview')
      if (!res.ok) {
        throw new Error(res.status === 401 ? 'Authentication session expired. Please sign in again.' : `Failed to load dashboard (HTTP ${res.status}).`)
      }
      setData((await res.json()) as Overview)
    } catch (err: unknown) {
      setApiError(err instanceof Error ? err.message : 'Unable to connect to the backend.')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  const sessions = data?.recent_sessions ?? []
  const pillClass = (s: string) => (s === 'completed' ? 'status-completed' : s === 'draft' ? 'status-draft' : 'status-inprogress')

  return (
    <div className="dashboard-layout">
      <Sidebar activeScreen="dashboard" onNavigate={onNavigate} sidebarOpen={sidebarOpen} onCloseSidebar={() => setSidebarOpen(false)} />

      <main className="dashboard-main">
        <header className="dashboard-topbar">
          <div className="topbar-left">
            <button type="button" className="mobile-nav-toggle" onClick={() => setSidebarOpen(true)} aria-label="Open sidebar navigation">
              ☰
            </button>
            <div className="header-titles">
              <h1 className="welcome-heading">Dashboard</h1>
              <p className="welcome-subtext">
                Welcome back{firstName(user?.email) ? `, ${firstName(user?.email)}` : ''}! Here&apos;s an overview of your screening activity.
              </p>
            </div>
          </div>

          {isPrivileged && (
            <div className="topbar-actions">
              <button type="button" className="btn btn-primary new-session-btn" onClick={() => onNavigate('new-screening')}>
                <span>+ New Screening Session</span>
              </button>
            </div>
          )}
        </header>

        <div className="dashboard-content">
          <section className="metrics-grid" aria-label="Key Performance Metrics">
            {METRICS.map((m) => (
              <div className="metric-card" key={m.key}>
                <div className="metric-header">
                  <div className="metric-value-wrap">
                    <div className="metric-value">{isLoading || !data ? '—' : data.stats[m.key]}</div>
                    <span className="metric-label">{m.label}</span>
                  </div>
                  <span className={`metric-icon-wrap ${m.icon}`} aria-hidden="true">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      {m.path}
                    </svg>
                  </span>
                </div>
              </div>
            ))}
          </section>

          <section className="table-container-card" aria-labelledby="sessions-title">
            <div className="table-header-row">
              <h2 id="sessions-title" className="section-title">
                Recent Screening Sessions
              </h2>
              <button type="button" className="btn-view-all-link" onClick={() => onNavigate('sessions')}>
                <span>View All</span>
              </button>
            </div>

            {isLoading && (
              <div className="sessions-status-card" role="status">
                <div className="sessions-spinner" aria-hidden="true" />
                <p style={{ fontSize: '13px', color: '#64748b', margin: 0 }}>Loading dashboard…</p>
              </div>
            )}

            {!isLoading && apiError && (
              <div className="sessions-error-card" role="alert">
                <h3 className="error-title">Unable to Load Dashboard Data</h3>
                <p className="error-desc">{apiError}</p>
                <button type="button" className="btn-retry-sessions" onClick={load}>
                  Retry Connection
                </button>
              </div>
            )}

            {!isLoading && !apiError && sessions.length === 0 && (
              <div className="sessions-empty-state">
                <h3 className="empty-title">No screening sessions yet</h3>
                {isPrivileged && (
                  <button type="button" className="btn btn-primary" onClick={() => onNavigate('new-screening')}>
                    Start New Screening Session
                  </button>
                )}
              </div>
            )}

            {!isLoading && !apiError && sessions.length > 0 && (
              <div className="table-responsive-wrapper">
                <table className="sessions-table">
                  <thead>
                    <tr>
                      <th scope="col">Session Name</th>
                      <th scope="col">JD</th>
                      <th scope="col">Resumes</th>
                      <th scope="col">Status</th>
                      <th scope="col">Created By</th>
                      <th scope="col">Created On</th>
                      <th scope="col" className="col-action">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {sessions.map((s) => (
                      <tr key={s.id}>
                        <td className="cell-role">
                          <span className="role-title">{s.name}</span>
                        </td>
                        <td className="cell-department">{s.job_title || '—'}</td>
                        <td>{s.resumes}</td>
                        <td className="cell-status">
                          <span className={`status-pill ${pillClass(s.status)}`}>
                            <span className="status-dot" aria-hidden="true" />
                            {s.status.charAt(0).toUpperCase() + s.status.slice(1)}
                            {s.status === 'processing' && s.percent !== null ? ` (${s.percent}%)` : ''}
                          </span>
                        </td>
                        <td>{s.created_by || '—'}</td>
                        <td className="cell-date">{formatDisplayDate(s.created_at)}</td>
                        <td className="col-action">
                          <button
                            type="button"
                            className="table-action-btn"
                            aria-label={`Open ${s.name}`}
                            title={s.status === 'draft' ? 'Open in Sessions' : 'Open results'}
                            onClick={() => (s.status === 'draft' || !onOpenSession ? onNavigate('sessions') : onOpenSession(s.id))}
                          >
                            •••
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      </main>
    </div>
  )
}

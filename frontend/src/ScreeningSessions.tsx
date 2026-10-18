import { useState, useMemo, useEffect } from 'react'
import { Sidebar, type AppScreen } from './Sidebar'
import type { DraftSessionDetail } from './NewScreeningWizard'
import { ScreeningWorkspace } from './ScreeningWorkspace'
import './Dashboard.css'
import './ScreeningSessions.css'

interface ScreeningSessionsProps {
  onNavigate: (screen: AppScreen) => void
  onNewSession: () => void
  onResumeDraft?: (sessionDetail: DraftSessionDetail) => void
}

export interface ApiScreeningSession {
  id: string
  job_description_id: string
  job_description_title: string
  status: string
  created_at: string
  updated_at: string
}

// Centralized API configuration and request helper
import { API_BASE_URL } from './config'
import { apiFetch } from './api'
import { useAuth } from './auth'

function formatDisplayDate(isoString?: string): string {
  if (!isoString) return 'Recently created'
  try {
    const d = new Date(isoString)
    return d.toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    })
  } catch {
    return 'Recently created'
  }
}

export function ScreeningSessions({
  onNavigate,
  onNewSession,
  onResumeDraft,
}: ScreeningSessionsProps) {
  const { isPrivileged, isAdmin } = useAuth()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('All')

  // API State
  const [sessions, setSessions] = useState<ApiScreeningSession[]>([])
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [apiError, setApiError] = useState<string | null>(null)

  // Resume Draft State
  const [loadingDraftId, setLoadingDraftId] = useState<string | null>(null)
  const [resumeDraftError, setResumeDraftError] = useState<{ sessionId: string; message: string } | null>(null)

  // Session Deletion State (Admin Only)
  const [sessionPendingDelete, setSessionPendingDelete] = useState<ApiScreeningSession | null>(null)
  const [isDeletingSession, setIsDeletingSession] = useState<boolean>(false)
  const [deleteError, setDeleteError] = useState<{ sessionId: string; message: string } | null>(null)
  const [deleteSuccessMessage, setDeleteSuccessMessage] = useState<string | null>(null)

  // Read-only Results View State (Admin / Recruiter)
  const [selectedSessionForResults, setSelectedSessionForResults] = useState<ApiScreeningSession | null>(null)


  // Fetch Screening Sessions from API
  const fetchScreeningSessions = async () => {
    setIsLoading(true)
    setApiError(null)
    try {
      const res = await apiFetch('/api/screening-sessions', {
        method: 'GET',
        headers: { Accept: 'application/json' },
      })
      if (!res.ok) {
        throw new Error(
          `API returned status ${res.status}: ${res.statusText || 'Failed to fetch screening sessions'}`
        )
      }
      const data = (await res.json()) as ApiScreeningSession[]
      setSessions(data)
    } catch (err: unknown) {
      const message =
        err instanceof Error
          ? err.message
          : 'Unable to connect to FastAPI backend server.'
      setApiError(
        `Failed to load screening sessions from ${API_BASE_URL}/api/screening-sessions. ${message}`
      )
      setSessions([]) // Do not silently substitute fictional data
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchScreeningSessions()
  }, [])

  const handleResumeDraft = async (sessionId: string) => {
    if (!isPrivileged) return
    setLoadingDraftId(sessionId)
    setResumeDraftError(null)

    try {
      const response = await apiFetch(`/api/screening-sessions/${sessionId}`)
      if (!response.ok) {
        const errorData = await response.json().catch(() => null)
        if (response.status === 409) {
          throw new Error(errorData?.detail || 'This screening session is no longer in draft status and cannot be reopened.')
        } else if (response.status === 404) {
          throw new Error('Screening session not found.')
        } else if (response.status === 403) {
          throw new Error('Access denied. Administrator or Recruiter privileges are required.')
        } else {
          throw new Error(`Failed to load session details (HTTP ${response.status}).`)
        }
      }

      const data: DraftSessionDetail = await response.json()
      if (onResumeDraft) {
        onResumeDraft(data)
      }
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : 'Unable to load draft screening session.'
      setResumeDraftError({ sessionId, message })
    } finally {
      setLoadingDraftId(null)
    }
  }

  // Handle Permanent Session Deletion (Admin Only)
  const handleDeleteSession = async (session: ApiScreeningSession) => {
    if (!isAdmin) return
    setIsDeletingSession(true)
    setDeleteError(null)

    try {
      const res = await apiFetch(`/api/screening-sessions/${session.id}`, {
        method: 'DELETE',
        headers: { Accept: 'application/json' },
      })

      if (!res.ok) {
        const errData = await res.json().catch(() => null)
        if (res.status === 409) {
          throw new Error(
            errData?.detail ||
              'Draft sessions cannot be deleted directly; end or complete the session first.'
          )
        } else if (res.status === 404) {
          throw new Error('Screening session not found or already deleted.')
        } else if (res.status === 403) {
          throw new Error(
            'Access denied. Administrator privileges are required to delete screening sessions.'
          )
        } else {
          throw new Error(
            errData?.detail || `Failed to delete screening session (HTTP ${res.status}).`
          )
        }
      }

      // Update the local list without losing search or filter state
      setSessions((prev) => prev.filter((s) => s.id !== session.id))
      setSessionPendingDelete(null)
      setDeleteSuccessMessage(
        `Screening session for "${session.job_description_title}" and its evaluation records were permanently deleted.`
      )
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : 'Unable to delete screening session.'
      setDeleteError({ sessionId: session.id, message })
    } finally {
      setIsDeletingSession(false)
    }
  }

  // Derive available statuses dynamically
  const availableStatuses = useMemo(() => {
    const set = new Set<string>()
    sessions.forEach((s) => {
      if (s.status) {
        const formatted =
          s.status.charAt(0).toUpperCase() + s.status.slice(1).toLowerCase()
        set.add(formatted)
      }
    })
    return ['All', ...Array.from(set).sort()]
  }, [sessions])

  // Local search and status filtering
  const filteredSessions = useMemo(() => {
    return sessions.filter((sess: ApiScreeningSession) => {
      const matchesStatus =
        statusFilter === 'All' ||
        sess.status.toLowerCase() === statusFilter.toLowerCase()

      const q = searchQuery.toLowerCase().trim()
      const matchesSearch =
        !q ||
        sess.job_description_title.toLowerCase().includes(q) ||
        sess.id.toLowerCase().includes(q) ||
        sess.status.toLowerCase().includes(q)

      return matchesStatus && matchesSearch
    })
  }, [sessions, searchQuery, statusFilter])

  const handleClearFilters = () => {
    setSearchQuery('')
    setStatusFilter('All')
  }

  // Render Read-Only Results View when a session is selected
  if (selectedSessionForResults) {
    return (
      <ScreeningWorkspace
        sessionId={selectedSessionForResults.id}
        initialView="results"
        jobTitle={selectedSessionForResults.job_description_title}
        onNavigate={onNavigate}
        onExit={() => setSelectedSessionForResults(null)}
      />
    )
  }

  return (
    <div className="dashboard-layout">
      {/* Shared Dark Left Sidebar */}
      <Sidebar
        activeScreen="sessions"
        onNavigate={onNavigate}
        sidebarOpen={sidebarOpen}
        onCloseSidebar={() => setSidebarOpen(false)}
      />

      {/* Main Content Area */}
      <main className="dashboard-main">
        {/* Top Header */}
        <header className="dashboard-topbar">
          <div className="topbar-left">
            <button
              type="button"
              className="mobile-nav-toggle"
              onClick={() => setSidebarOpen(true)}
              aria-label="Open sidebar navigation"
            >
              ☰
            </button>
            <div className="header-titles">
              <h1 className="welcome-heading">Screening Sessions</h1>
              <p className="welcome-subtext">
                Manage resume screening pipelines, candidate volumes, and evaluation runs.
              </p>
            </div>
          </div>

          {isPrivileged && (
            <div className="topbar-actions">
              <button
                type="button"
                className="btn btn-primary new-session-btn"
                onClick={onNewSession}
              >
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <line x1="12" y1="5" x2="12" y2="19" />
                  <line x1="5" y1="12" x2="19" y2="12" />
                </svg>
                <span>New Screening Session</span>
              </button>
            </div>
          )}
        </header>


        {/* Deletion Success Toast */}
        {deleteSuccessMessage && (
          <div className="sessions-success-toast" role="status" aria-live="polite">
            <span className="toast-icon" aria-hidden="true">✓</span>
            <span className="toast-text">{deleteSuccessMessage}</span>
            <button
              type="button"
              className="notice-dismiss"
              onClick={() => setDeleteSuccessMessage(null)}
              aria-label="Dismiss success message"
            >
              ✕
            </button>
          </div>
        )}

        {/* Deletion Error Banner (Retryable) */}
        {deleteError && !sessionPendingDelete && (
          <div className="sessions-action-error-banner" role="alert">
            <div className="error-banner-content">
              <span aria-hidden="true">⚠️</span>
              <span>{deleteError.message}</span>
            </div>
            <button
              type="button"
              className="btn-retry-inline"
              onClick={() => {
                const target = sessions.find((s) => s.id === deleteError.sessionId)
                if (target) {
                  setSessionPendingDelete(target)
                }
              }}
            >
              Retry Deletion
            </button>
          </div>
        )}

        <div className="sessions-page-content">
          {/* Persistent Notice Explaining Persisted Metadata & Draft State */}
          <div className="persistent-preview-banner" role="status">
            <span className="preview-icon" aria-hidden="true">ℹ️</span>
            <div className="preview-banner-text">
              <strong>Locally Persisted Session Metadata</strong>
              <span>
                Screening sessions are loaded directly from the backend database. Sessions with status <code>draft</code> represent configured criteria rubrics with no uploaded or processed resumes.
              </span>
            </div>
          </div>

          {/* Quick Metrics Strip (Only factual metadata counts, no fictional candidate metrics) */}
          <div className="sessions-stats-strip">
            <div className="sessions-stat-pill">
              <span className="stat-pill-label">Total Sessions</span>
              <span className="stat-pill-val">{isLoading ? '—' : sessions.length}</span>
            </div>
            <div className="sessions-stat-pill">
              <span className="stat-pill-label">Draft Sessions</span>
              <span className="stat-pill-val stat-val-blue">
                {isLoading
                  ? '—'
                  : sessions.filter((s) => s.status.toLowerCase() === 'draft').length}
              </span>
            </div>
            <div className="sessions-stat-pill">
              <span className="stat-pill-label">Metadata Source</span>
              <span className="stat-pill-val stat-val-green">
                {isLoading ? '—' : 'SQLite DB'}
              </span>
            </div>
          </div>

          {/* Search & Filter Toolbar */}
          <div className="sessions-controls-bar">
            <div className="sessions-search-box">
              <svg
                className="sessions-search-icon"
                viewBox="0 0 24 24"
                width="18"
                height="18"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <circle cx="11" cy="11" r="8" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
              <input
                type="text"
                className="sessions-search-input"
                placeholder="Search by role title, status, or session ID..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                aria-label="Search screening sessions"
              />
              {searchQuery && (
                <button
                  type="button"
                  className="sessions-clear-search"
                  onClick={() => setSearchQuery('')}
                  aria-label="Clear search input"
                >
                  ✕
                </button>
              )}
            </div>

            <div className="sessions-filter-group">
              <label htmlFor="status-filter-select" className="sessions-filter-label">
                Status:
              </label>
              <select
                id="status-filter-select"
                className="sessions-status-select"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
              >
                {availableStatuses.map((st) => (
                  <option key={st} value={st}>
                    {st === 'All' ? 'All Statuses' : st}
                  </option>
                ))}
              </select>
            </div>

            <div className="sessions-count-indicator">
              {isLoading
                ? 'Loading sessions...'
                : `Showing ${filteredSessions.length} of ${sessions.length} sessions`}
            </div>
          </div>

          {/* Sessions Table Card */}
          <section className="table-container-card" aria-labelledby="sessions-table-title">
            <div className="table-header-row">
              <div>
                <h2 id="sessions-table-title" className="section-title">
                  All Screening Sessions
                </h2>
                <p className="section-subtitle">
                  Historical and current screening sessions evaluated with criteria rubrics.
                </p>
              </div>
            </div>

            {/* Loading State */}
            {isLoading && (
              <div className="sessions-status-card" role="status">
                <div className="sessions-spinner" aria-hidden="true" />
                <p className="status-title">Loading screening sessions from API...</p>
                <p className="status-sub">Connecting to {API_BASE_URL}/api/screening-sessions</p>
              </div>
            )}

            {/* API Error State */}
            {!isLoading && apiError && (
              <div className="sessions-error-card" role="alert">
                <div className="error-icon" aria-hidden="true">⚠️</div>
                <h3 className="error-title">Backend API Connection Error</h3>
                <p className="error-desc">{apiError}</p>
                <button
                  type="button"
                  className="btn btn-primary btn-retry-sessions"
                  onClick={fetchScreeningSessions}
                >
                  Retry Connection
                </button>
              </div>
            )}

            {/* Empty DB State */}
            {!isLoading && !apiError && sessions.length === 0 && (
              <div className="sessions-empty-state">
                <div className="empty-icon" aria-hidden="true">📋</div>
                <h3 className="empty-title">No screening sessions found</h3>
                <p className="empty-sub">
                  {isPrivileged
                    ? 'There are no screening sessions saved in the database yet. Launch a new session using the “New Screening Session” button.'
                    : 'There are no screening sessions saved in the database yet.'}
                </p>
                {isPrivileged && (
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={onNewSession}
                  >
                    + Create First Screening Session
                  </button>
                )}
              </div>
            )}

            {/* Empty Filter Matches */}
            {!isLoading && !apiError && sessions.length > 0 && filteredSessions.length === 0 && (
              <div className="sessions-empty-state">
                <div className="empty-icon" aria-hidden="true">🔍</div>
                <h3 className="empty-title">No matching screening sessions found</h3>
                <p className="empty-sub">
                  No sessions match your search &ldquo;{searchQuery}&rdquo; and status filter &ldquo;{statusFilter}&rdquo;.
                </p>
                <button
                  type="button"
                  className="btn btn-secondary btn-clear-filters"
                  onClick={handleClearFilters}
                >
                  Clear Filters
                </button>
              </div>
            )}

            {/* Error banner when reopening a draft session fails */}
            {resumeDraftError && (
              <div
                className="step-error-banner"
                role="alert"
                style={{
                  margin: '16px 24px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '8px',
                  padding: '12px 16px',
                  backgroundColor: '#fef2f2',
                  border: '1px solid #fecaca',
                  borderRadius: '8px',
                  color: '#991b1b',
                  fontSize: '13.5px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span aria-hidden="true">⚠️</span>
                  <span>{resumeDraftError.message}</span>
                </div>
                <button
                  type="button"
                  onClick={() => handleResumeDraft(resumeDraftError.sessionId)}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: '#b91c1c',
                    fontWeight: 700,
                    textDecoration: 'underline',
                    cursor: 'pointer',
                    padding: 0,
                    fontSize: '13px',
                  }}
                >
                  Retry Reopen
                </button>
              </div>
            )}

            {/* Loaded Table */}
            {!isLoading && !apiError && filteredSessions.length > 0 && (
              <div className="table-responsive-wrapper">
                <table className="sessions-table">
                  <thead>
                    <tr>
                      <th scope="col">Job Title / Session</th>
                      <th scope="col">Date Created</th>
                      <th scope="col">Status</th>
                      {isPrivileged && <th scope="col" className="col-action">Action</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {filteredSessions.map((sess) => (
                      <tr key={sess.id}>
                        <td className="cell-role">
                          <span className="role-title">{sess.job_description_title}</span>
                          <span className="session-id">{sess.id}</span>
                        </td>
                        <td className="cell-date">{formatDisplayDate(sess.created_at)}</td>
                        <td className="cell-status">
                          <span
                            className={`status-pill ${
                              sess.status.toLowerCase() === 'completed'
                                ? 'status-completed'
                                : sess.status.toLowerCase() === 'in progress'
                                ? 'status-inprogress'
                                : 'status-draft'
                            }`}
                          >
                            <span className="status-dot" aria-hidden="true" />
                            {sess.status.charAt(0).toUpperCase() + sess.status.slice(1).toLowerCase()}
                          </span>
                        </td>
                        {isPrivileged && (
                          <td className="col-action">
                            <div className="sessions-actions-wrap">
                              {sess.status.toLowerCase() === 'draft' ? (
                                <button
                                  type="button"
                                  className="table-action-btn btn-resume-draft"
                                  onClick={() => handleResumeDraft(sess.id)}
                                  disabled={loadingDraftId === sess.id}
                                  aria-label={`Resume draft session for ${sess.job_description_title}`}
                                >
                                  {loadingDraftId === sess.id ? 'Loading...' : 'Resume Draft'}
                                </button>
                              ) : (
                                <button
                                  type="button"
                                  className="table-action-btn"
                                  onClick={() =>
                                    setSelectedSessionForResults(sess)
                                  }
                                >
                                  View Results
                                </button>
                              )}
                              {isAdmin &&
                                (sess.status.toLowerCase() === 'completed' ||
                                  sess.status.toLowerCase() === 'ended') && (
                                  <button
                                    type="button"
                                    className="table-action-btn table-action-danger-btn btn-delete-session"
                                    onClick={() => {
                                      setDeleteError(null)
                                      setSessionPendingDelete(sess)
                                    }}
                                    title="Permanently delete session and evaluations"
                                    aria-label={`Permanently delete session for ${sess.job_description_title}`}
                                  >
                                    Delete
                                  </button>
                              )}
                            </div>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      </main>

      {/* Permanent Deletion Confirmation Modal (Admin Only) */}
      {sessionPendingDelete && (
        <div
          className="session-delete-modal-overlay"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-session-modal-title"
        >
          <div className="session-delete-modal">
            <div className="modal-header">
              <h3 id="delete-session-modal-title">Delete Screening Session</h3>
            </div>
            <div className="modal-body">
              <p>
                Are you sure you want to permanently delete the screening session for{' '}
                <strong>{sessionPendingDelete.job_description_title}</strong> (ID: <code>{sessionPendingDelete.id.slice(0, 8)}...</code>)?
              </p>
              <ul className="delete-modal-list">
                <li>
                  <strong>Session &amp; Results Deletion:</strong> The session record and all stored rubric scores, criteria explanations, and verbatim evidence quotes will be permanently removed from the local database.
                </li>
                <li>
                  <strong>Temporary Files Cleaned:</strong> Uploaded resume files, extracted text, and Chroma vectors were already cleaned up when this session was finalized or ended.
                </li>
                <li>
                  <strong>Permanent Action:</strong> This operation cannot be undone.
                </li>
              </ul>
              {deleteError && deleteError.sessionId === sessionPendingDelete.id && (
                <div className="delete-inline-error" role="alert">
                  <span>{deleteError.message}</span>
                </div>
              )}
            </div>
            <div className="modal-actions">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => {
                  setSessionPendingDelete(null)
                  setDeleteError(null)
                }}
                disabled={isDeletingSession}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-danger-solid"
                onClick={() => handleDeleteSession(sessionPendingDelete)}
                disabled={isDeletingSession}
              >
                {isDeletingSession ? (
                  <>
                    <div className="btn-inline-spinner" aria-hidden="true" />
                    <span>Deleting Session...</span>
                  </>
                ) : (
                  'Confirm Permanent Deletion'
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}


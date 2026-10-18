import { useState, useEffect } from 'react'
import { Sidebar, type AppScreen } from './Sidebar'
import type { ApiScreeningSession } from './ScreeningSessions'
import { apiFetch } from './api'
import { useAuth } from './auth'
import './Dashboard.css'
import './ScreeningSessions.css'
import './ProcessingResumes.css'
import './SessionResultsView.css'

export interface RubricCriterionItem {
  criterion: string
  criterion_type: string
  score: number
  max_score: number
  evidence_status: 'documented' | 'not_found_in_resume' | 'unknown' | string
  explanation: string
  evidence_quotes: string[]
}

export interface ResumeEvaluationResponse {
  session_id: string
  resume_id: string
  original_filename: string
  job_description_id: string
  job_title: string
  overall_score: number | null
  max_overall_score: number
  rubric: RubricCriterionItem[]
  missing_criteria: string[]
  unverified_criteria: string[]
  evaluation_summary: string
  disclaimer: string
  model_name?: string | null
  evaluated_at?: string | null
}

interface SessionResultsViewProps {
  session: ApiScreeningSession
  onBack: () => void
  onNavigate: (screen: AppScreen) => void
}

function formatDisplayDate(isoString?: string): string {
  if (!isoString) return '—'
  try {
    const d = new Date(isoString)
    return d.toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    })
  } catch {
    return '—'
  }
}

/**
 * Safely escapes a CSV cell and neutralizes spreadsheet formula injection.
 * Prefixing with a single quote (') prevents spreadsheet software (Excel, Calc, Sheets)
 * from interpreting values starting with '=', '+', '-', '@', '\t', '\r', or '%' as commands/formulas.
 */
export function escapeCsvCell(val: unknown): string {
  if (val === null || val === undefined) {
    return '""'
  }
  if (typeof val === 'number' && Number.isFinite(val)) {
    return `"${val}"`
  }
  let str = String(val)
  // Neutralize formula injection
  if (/^[=\+\-@\t\r%]/.test(str)) {
    str = "'" + str
  }
  const escaped = str.replace(/"/g, '""')
  return `"${escaped}"`
}

/**
 * Builds RFC 4180 compliant CSV string from persisted evaluation records.
 * Uses only evaluation records already retrieved from the database.
 * Strictly excludes ranks, hiring recommendations, and fictional candidate data.
 */
export function generateSessionReportCsv(
  session: ApiScreeningSession,
  evaluations: ResumeEvaluationResponse[]
): string {
  const headers = [
    'Session ID',
    'Job Title',
    'Session Status',
    'Session Created Date',
    'Resume Filename',
    'Overall Score',
    'Max Overall Score',
    'Criterion',
    'Criterion Type',
    'Evidence Status',
    'Criterion Score',
    'Criterion Max Score',
    'Explanation',
    'Verified Evidence Quotes',
    'Evaluation Summary',
    'Model Name',
    'Evaluated At',
  ]

  const rows: string[] = []
  rows.push(headers.map(escapeCsvCell).join(','))

  for (const evalData of evaluations) {
    const overallScoreFormatted =
      evalData.overall_score !== null && evalData.overall_score !== undefined
        ? evalData.overall_score.toFixed(1)
        : 'N/A'

    const formatQuotes = (quotes?: string[]) => {
      if (!quotes || quotes.length === 0) return 'None'
      return quotes.join(' | ')
    }

    if (evalData.rubric && evalData.rubric.length > 0) {
      for (const item of evalData.rubric) {
        const row = [
          session.id,
          evalData.job_title || session.job_description_title,
          session.status,
          session.created_at,
          evalData.original_filename,
          overallScoreFormatted,
          evalData.max_overall_score ?? 100,
          item.criterion,
          item.criterion_type,
          item.evidence_status,
          item.score,
          item.max_score,
          item.explanation,
          formatQuotes(item.evidence_quotes),
          evalData.evaluation_summary,
          evalData.model_name || 'N/A',
          evalData.evaluated_at || 'N/A',
        ]
        rows.push(row.map(escapeCsvCell).join(','))
      }
    } else {
      const row = [
        session.id,
        evalData.job_title || session.job_description_title,
        session.status,
        session.created_at,
        evalData.original_filename,
        overallScoreFormatted,
        evalData.max_overall_score ?? 100,
        '',
        '',
        '',
        '',
        '',
        '',
        'None',
        evalData.evaluation_summary,
        evalData.model_name || 'N/A',
        evalData.evaluated_at || 'N/A',
      ]
      rows.push(row.map(escapeCsvCell).join(','))
    }
  }

  return rows.join('\r\n')
}

export function SessionResultsView({
  session,
  onBack,
  onNavigate,
}: SessionResultsViewProps) {
  const { isPrivileged } = useAuth()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [evaluations, setEvaluations] = useState<ResumeEvaluationResponse[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [selectedResumeId, setSelectedResumeId] = useState<string | null>(null)
  const [downloadNotice, setDownloadNotice] = useState<string | null>(null)

  const fetchEvaluations = async () => {
    setIsLoading(true)
    setLoadError(null)
    try {
      const res = await apiFetch(`/api/screening-sessions/${session.id}/evaluations`, {
        method: 'GET',
        headers: { Accept: 'application/json' },
      })
      if (!res.ok) {
        if (res.status === 403) {
          throw new Error('Access denied. Administrator or Recruiter privileges are required to view evaluation results.')
        } else if (res.status === 404) {
          throw new Error('Screening session not found.')
        } else {
          throw new Error(`Failed to load evaluations (HTTP ${res.status}).`)
        }
      }
      const data: ResumeEvaluationResponse[] = await res.json()
      setEvaluations(Array.isArray(data) ? data : [])
      if (Array.isArray(data) && data.length > 0) {
        setSelectedResumeId(data[0].resume_id)
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Unable to connect to backend service.'
      setLoadError(msg)
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchEvaluations()
  }, [session.id])

  const handleDownloadReport = () => {
    if (evaluations.length === 0) return

    const csvContent = generateSessionReportCsv(session, evaluations)
    const blob = new Blob(['\uFEFF' + csvContent], {
      type: 'text/csv;charset=utf-8;',
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    const sanitizedTitle = (session.job_description_title || 'session')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-|-$/g, '')
    link.href = url
    link.download = `session-report-${sanitizedTitle || 'results'}-${session.id.slice(0, 8)}.csv`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)

    setDownloadNotice(
      `Session report CSV downloaded. File contains rubric criteria, evidence status, and verified evidence quotes for ${evaluations.length} ${
        evaluations.length === 1 ? 'resume' : 'resumes'
      }.`
    )
  }

  const selectedEval = evaluations.find((e) => e.resume_id === selectedResumeId) || evaluations[0] || null

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
              <div className="breadcrumb-row">
                <button
                  type="button"
                  className="breadcrumb-back-btn"
                  onClick={onBack}
                  aria-label="Return to Screening Sessions list"
                >
                  ← Back to Screening Sessions
                </button>
              </div>
              <h1 className="welcome-heading">
                Results: {session.job_description_title}
              </h1>
              <p className="welcome-subtext">
                Persisted candidate evaluation rubrics and verified evidence quotes stored in the local database.
              </p>
            </div>
          </div>

          <div className="topbar-actions">
            {isPrivileged && (
              <div className="download-report-btn-wrapper">
                <button
                  type="button"
                  className="btn btn-primary btn-download-report"
                  onClick={handleDownloadReport}
                  disabled={evaluations.length === 0 || isLoading}
                  title={
                    evaluations.length === 0
                      ? 'No evaluation records available to download'
                      : 'Download session report CSV containing evaluation evidence'
                  }
                  aria-label="Download session report CSV"
                >
                  <span className="btn-icon" aria-hidden="true">📥</span>
                  <span>Download Session Report</span>
                </button>
                <span className="btn-caption-note">
                  Exports rubric criteria &amp; verified quotes
                </span>
              </div>
            )}
            <button
              type="button"
              className="btn btn-secondary btn-back-sessions-top"
              onClick={onBack}
            >
              ← Back to Sessions
            </button>
          </div>
        </header>

        <div className="sessions-page-content session-results-content">
          {/* Session Metadata Card */}
          <section className="session-meta-strip" aria-label="Session Metadata">
            <div className="meta-strip-left">
              <div className="meta-item">
                <span className="meta-label">Job Title</span>
                <span className="meta-val meta-val-title">{session.job_description_title}</span>
              </div>
              <div className="meta-item">
                <span className="meta-label">Session ID</span>
                <code className="meta-val-code">{session.id}</code>
              </div>
              <div className="meta-item">
                <span className="meta-label">Date Created</span>
                <span className="meta-val">{formatDisplayDate(session.created_at)}</span>
              </div>
              <div className="meta-item">
                <span className="meta-label">Status</span>
                <span className={`status-pill ${session.status.toLowerCase() === 'completed' ? 'status-completed' : 'status-inprogress'}`}>
                  <span className="status-dot" aria-hidden="true" />
                  {session.status.charAt(0).toUpperCase() + session.status.slice(1).toLowerCase()}
                </span>
              </div>
            </div>

            <div className="meta-strip-right">
              <div className="meta-count-pill">
                <span className="meta-count-num">{evaluations.length}</span>
                <span className="meta-count-label">
                  {evaluations.length === 1 ? 'Evaluated Resume' : 'Evaluated Resumes'}
                </span>
              </div>
            </div>
          </section>

          {/* Download Notification Banner */}
          {downloadNotice && (
            <div className="download-report-success-banner" role="status" aria-live="polite">
              <span className="notice-icon" aria-hidden="true">✓</span>
              <div className="notice-content">
                <strong>Session Report Downloaded:</strong>
                <span>{downloadNotice}</span>
              </div>
              <button
                type="button"
                className="notice-dismiss-btn"
                onClick={() => setDownloadNotice(null)}
                aria-label="Dismiss download notification"
              >
                ✕
              </button>
            </div>
          )}

          {/* Read-Only Disclosure Banner */}
          <div className="eval-overview-privacy-banner" role="status">
            <span className="privacy-banner-icon" aria-hidden="true">ℹ️</span>
            <div className="privacy-banner-text">
              <strong>Persisted Database Records (Read-Only):</strong>
              <span>
                These validated evaluation assessments and verbatim quotes were retrieved from the local database.
                Original resume files, extracted plain text, and Chroma vector stores have been cleaned up from disk.
                Evaluations are strictly advisory for recruiters; no automated hiring decisions or rankings are made.
              </span>
            </div>
          </div>

          {/* Loading State */}
          {isLoading && (
            <div className="sessions-status-card" role="status">
              <div className="sessions-spinner" aria-hidden="true" />
              <p className="status-title">Loading persisted evaluation records...</p>
              <p className="status-sub">Querying local database for session {session.id}</p>
            </div>
          )}

          {/* Error State */}
          {!isLoading && loadError && (
            <div className="sessions-error-card" role="alert">
              <div className="error-icon" aria-hidden="true">⚠️</div>
              <h3 className="error-title">Failed to Load Evaluation Records</h3>
              <p className="error-desc">{loadError}</p>
              <button
                type="button"
                className="btn btn-primary btn-retry-sessions"
                onClick={fetchEvaluations}
              >
                Retry Loading
              </button>
            </div>
          )}

          {/* Empty State */}
          {!isLoading && !loadError && evaluations.length === 0 && (
            <div className="sessions-empty-state">
              <div className="empty-icon" aria-hidden="true">📋</div>
              <h3 className="empty-title">No evaluated resumes found</h3>
              <p className="empty-sub">
                This screening session does not contain any persisted evaluation records in the local database.
              </p>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={onBack}
              >
                ← Return to Screening Sessions
              </button>
            </div>
          )}

          {/* Populated Results View (Split Layout) */}
          {!isLoading && !loadError && evaluations.length > 0 && (
            <div className="proc-split-layout results-view-split">
              {/* Left Column: List of evaluated candidates */}
              <div className="eval-overview-list-col" aria-label="Evaluated Candidate Resumes">
                <div className="eval-overview-list-header">
                  <span className="eval-overview-list-label">
                    Evaluated Resumes ({evaluations.length})
                  </span>
                  <span className="eval-overview-list-hint">
                    Select a resume to inspect rubric details
                  </span>
                </div>

                <div className="eval-overview-cards-list">
                  {evaluations.map((evalData) => {
                    const isSelected = selectedEval?.resume_id === evalData.resume_id
                    const documentedCount = evalData.rubric.filter((r) => r.evidence_status === 'documented').length
                    const notFoundCount = evalData.rubric.filter((r) => r.evidence_status === 'not_found_in_resume').length
                    const unknownCount = evalData.rubric.filter((r) => r.evidence_status === 'unknown').length

                    return (
                      <div
                        key={evalData.resume_id}
                        className={`eval-overview-card-item ${isSelected ? 'selected' : ''}`}
                        onClick={() => setSelectedResumeId(evalData.resume_id)}
                        role="button"
                        tabIndex={0}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault()
                            setSelectedResumeId(evalData.resume_id)
                          }
                        }}
                        aria-selected={isSelected}
                      >
                        <div className="overview-item-header">
                          <div className="overview-item-title-block">
                            <span className="overview-item-file-icon" aria-hidden="true">📄</span>
                            <h5 className="overview-item-filename" title={evalData.original_filename}>
                              {evalData.original_filename}
                            </h5>
                          </div>
                          <div className="overview-score-pill">
                            <span className="overview-score-val">
                              {evalData.overall_score !== null ? evalData.overall_score.toFixed(1) : 'N/A'}
                            </span>
                            <span className="overview-score-max">/ {evalData.max_overall_score || 100}</span>
                          </div>
                        </div>

                        <div className="overview-item-jd-row">
                          <span className="overview-jd-label">Target Role:</span>
                          <span className="overview-jd-title">{evalData.job_title || session.job_description_title}</span>
                        </div>

                        <div className="overview-badges-row">
                          <span className="overview-count-chip chip-documented" title={`${documentedCount} criteria documented in resume`}>
                            ✓ {documentedCount} Documented
                          </span>
                          <span className="overview-count-chip chip-not-found" title={`${notFoundCount} criteria not found in resume`}>
                            ○ {notFoundCount} Not Found
                          </span>
                          <span className="overview-count-chip chip-unknown" title={`${unknownCount} criteria ambiguous or unknown`}>
                            ? {unknownCount} Unknown
                          </span>
                        </div>

                        <div className="overview-item-footer">
                          {evalData.model_name ? (
                            <span className="overview-model-tag">Model: {evalData.model_name} • Persisted</span>
                          ) : (
                            <span className="overview-model-tag">Persisted Rubric</span>
                          )}
                          <span className="overview-inspect-prompt">
                            {isSelected ? '● Currently Selected' : 'Inspect Rubric →'}
                          </span>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* Right Column: Detail Rubric Inspection Panel */}
              <div className="proc-resume-eval-col" aria-label="Resume Evidence Evaluation Detail">
                {selectedEval && (
                  <div className="eval-detail-container" role="region" aria-label="Evaluation Details">
                    {/* Header: Candidate & Score Banner */}
                    <div className="eval-score-card">
                      <div className="eval-score-left">
                        <span className="eval-role-pill">
                          {selectedEval.job_title || session.job_description_title}
                        </span>
                        <h4 className="eval-filename-title">
                          {selectedEval.original_filename}
                        </h4>
                        <div className="eval-meta-row">
                          {selectedEval.model_name && (
                            <span className="eval-model-tag">
                              Evaluated with {selectedEval.model_name}
                            </span>
                          )}
                          {selectedEval.evaluated_at && (
                            <span className="eval-timestamp-tag">
                              {formatDisplayDate(selectedEval.evaluated_at)}
                            </span>
                          )}
                          <span className="eval-persisted-tag">✓ Saved to Database</span>
                        </div>
                      </div>

                      <div className="eval-score-right">
                        <div className="score-dial">
                          <span className="score-val">
                            {selectedEval.overall_score !== null ? selectedEval.overall_score.toFixed(1) : 'N/A'}
                          </span>
                          <span className="score-max">/ {selectedEval.max_overall_score || 100}</span>
                        </div>
                        <span className="score-caption">Overall Rubric Score</span>
                      </div>
                    </div>

                    {/* Executive Summary Card */}
                    <div className="eval-summary-card">
                      <div className="summary-header">
                        <span className="summary-icon" aria-hidden="true">📋</span>
                        <h5 className="eval-card-subtitle">Evaluation Summary</h5>
                      </div>
                      <p className="eval-summary-text">{selectedEval.evaluation_summary}</p>
                    </div>

                    {/* Missing Criteria Alert Box */}
                    {selectedEval.missing_criteria && selectedEval.missing_criteria.length > 0 && (
                      <div className="eval-missing-card">
                        <div className="missing-header">
                          <span className="missing-icon" aria-hidden="true">⚠️</span>
                          <div>
                            <h5 className="eval-card-subtitle">
                              Undocumented Criteria ({selectedEval.missing_criteria.length})
                            </h5>
                            <span className="missing-disclaimer-note">
                              Not documented in resume text. Absence of text is not proof of lack of skill.
                            </span>
                          </div>
                        </div>
                        <div className="missing-chips-list">
                          {selectedEval.missing_criteria.map((c, idx) => (
                            <span key={`missing-${idx}`} className="missing-criterion-chip">
                              {c}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Unverified Criteria Alert Box */}
                    {selectedEval.unverified_criteria && selectedEval.unverified_criteria.length > 0 && (
                      <div className="eval-unverified-card">
                        <div className="unverified-header">
                          <span className="unverified-icon" aria-hidden="true">?</span>
                          <div>
                            <h5 className="eval-card-subtitle">
                              Unverified / Ambiguous Documentation ({selectedEval.unverified_criteria.length})
                            </h5>
                            <span className="unverified-note">
                              Concepts are mentioned ambiguously; documentation is not clearly established.
                            </span>
                          </div>
                        </div>
                        <div className="unverified-chips-list">
                          {selectedEval.unverified_criteria.map((c, idx) => (
                            <span key={`unverified-${idx}`} className="unverified-criterion-chip">
                              {c}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Structured Rubric Criteria List */}
                    <div className="eval-rubric-section">
                      <h5 className="eval-rubric-title">
                        Evaluation Rubric ({selectedEval.rubric.length} {selectedEval.rubric.length === 1 ? 'Criterion' : 'Criteria'})
                      </h5>
                      <div className="eval-rubric-items-list">
                        {selectedEval.rubric.map((item, idx) => {
                          const statusClass =
                            item.evidence_status === 'documented'
                              ? 'status-documented'
                              : item.evidence_status === 'not_found_in_resume'
                              ? 'status-not-found'
                              : 'status-unknown'

                          const statusLabel =
                            item.evidence_status === 'documented'
                              ? '✓ Documented'
                              : item.evidence_status === 'not_found_in_resume'
                              ? '○ Not Found in Resume'
                              : '? Ambiguous / Unknown'

                          return (
                            <div key={`rubric-${idx}`} className={`rubric-item-card ${statusClass}`}>
                              <div className="rubric-item-topbar">
                                <div className="rubric-item-title-group">
                                  <span className="rubric-type-pill">
                                    {item.criterion_type.replace('_', ' ').toUpperCase()}
                                  </span>
                                  <h6 className="rubric-criterion-name">{item.criterion}</h6>
                                </div>
                                <div className="rubric-item-score-group">
                                  <span className={`rubric-status-badge ${statusClass}`}>
                                    {statusLabel}
                                  </span>
                                  <span className="rubric-score-pill">
                                    Score: {item.score} / {item.max_score}
                                  </span>
                                </div>
                              </div>

                              <p className="rubric-explanation">{item.explanation}</p>

                              {/* Supporting Verbatim Quotes */}
                              {item.evidence_quotes && item.evidence_quotes.length > 0 && (
                                <div className="rubric-quotes-block">
                                  <span className="quotes-label">Supporting Verbatim Quotes:</span>
                                  <div className="quotes-list">
                                    {item.evidence_quotes.map((q, qIdx) => (
                                      <blockquote key={`quote-${idx}-${qIdx}`} className="verbatim-quote">
                                        &ldquo;{q}&rdquo;
                                      </blockquote>
                                    ))}
                                  </div>
                                </div>
                              )}

                              {item.evidence_status === 'not_found_in_resume' && (
                                <span className="rubric-missing-disclaimer">
                                  Note: Not documented in resume text. Absence of text is not proof of lack of skill.
                                </span>
                              )}
                            </div>
                          )
                        })}
                      </div>
                    </div>

                    {/* Disclaimer Footer Card */}
                    <div className="eval-disclaimer-box" role="note">
                      <span className="disclaimer-icon" aria-hidden="true">ℹ️</span>
                      <div className="disclaimer-text">
                        <strong>Recruiter Advisory Notice:</strong>
                        <span>{selectedEval.disclaimer}</span>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}

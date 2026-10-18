import { useState, useEffect, useMemo, useCallback } from 'react'
import { Sidebar, type AppScreen } from './Sidebar'
import { apiFetch } from './api'
import { escapeCsvCell } from './SessionResultsView'
import './Dashboard.css'
import './ScreeningResults.css'
import './Candidates.css'

interface CandidatesProps {
  onNavigate: (screen: AppScreen) => void
}

export interface CandidateEvaluationDirectoryItem {
  id: string
  resume_id: string
  original_filename: string
  session_id: string
  job_description_title: string
  evaluated_at: string
  overall_score: number | null
  max_overall_score: number
  evaluation_summary: string
}

export interface RubricCriterionItem {
  criterion: string
  criterion_type: string
  score: number
  max_score: number
  evidence_status: string
  explanation: string
  evidence_quotes: string[]
}

export interface ResumeEvaluationDetail {
  id?: string
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

export function Candidates({ onNavigate }: CandidatesProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [evaluations, setEvaluations] = useState<CandidateEvaluationDirectoryItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Search and Filter State (preserved across detail inspections)
  const [searchQuery, setSearchQuery] = useState('')
  const [roleFilter, setRoleFilter] = useState('All')
  const [scoreFilter, setScoreFilter] = useState<'all' | 'scored' | 'unscored'>('all')

  // Selected Evaluation for Inspection (Read-Only Detail View)
  const [selectedEvaluationId, setSelectedEvaluationId] = useState<string | null>(null)
  const [evalDetail, setEvalDetail] = useState<ResumeEvaluationDetail | null>(null)
  const [isLoadingDetail, setIsLoadingDetail] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)

  // Fetch candidates directory from backend API
  const fetchCandidatesDirectory = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const res = await apiFetch('/api/candidates', {
        headers: { Accept: 'application/json' },
      })
      if (!res.ok) {
        if (res.status === 403) {
          throw new Error('Access denied. Admin or Recruiter authorization is required.')
        }
        if (res.status === 401) {
          throw new Error('Authentication required. Please sign in.')
        }
        const errData = await res.json().catch(() => null)
        throw new Error(errData?.detail || `Failed to load candidates directory (${res.status})`)
      }
      const data = (await res.json()) as CandidateEvaluationDirectoryItem[]
      setEvaluations(data)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Unable to load candidates directory.'
      setError(msg)
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchCandidatesDirectory()
  }, [fetchCandidatesDirectory])

  // Inspect existing persisted evaluation record
  const handleInspect = async (item: CandidateEvaluationDirectoryItem) => {
    setSelectedEvaluationId(item.id)
    setIsLoadingDetail(true)
    setDetailError(null)
    try {
      const res = await apiFetch(`/api/evaluations/${item.id}`, {
        headers: { Accept: 'application/json' },
      })
      if (!res.ok) {
        const errData = await res.json().catch(() => null)
        throw new Error(errData?.detail || `Failed to load evaluation details (${res.status})`)
      }
      const data = (await res.json()) as ResumeEvaluationDetail
      setEvalDetail(data)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load evaluation details.'
      setDetailError(msg)
    } finally {
      setIsLoadingDetail(false)
    }
  }

  const handleReturnToDirectory = () => {
    setSelectedEvaluationId(null)
    setEvalDetail(null)
    setDetailError(null)
  }

  // Derive distinct roles for filter dropdown
  const distinctRoles = useMemo(() => {
    const set = new Set<string>()
    evaluations.forEach((e) => {
      if (e.job_description_title) set.add(e.job_description_title)
    })
    return Array.from(set).sort()
  }, [evaluations])

  // Derive distinct screening sessions count
  const uniqueSessionsCount = useMemo(() => {
    return new Set(evaluations.map((e) => e.session_id)).size
  }, [evaluations])

  // Filter evaluations by search query, role, and score presence
  const filteredEvaluations = useMemo(() => {
    return evaluations.filter((item) => {
      // 1. Role Filter
      if (roleFilter !== 'All' && item.job_description_title !== roleFilter) {
        return false
      }

      // 2. Score Filter
      if (scoreFilter === 'scored' && item.overall_score === null) {
        return false
      }
      if (scoreFilter === 'unscored' && item.overall_score !== null) {
        return false
      }

      // 3. Search Query Filter
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim()
        const matchesFilename = item.original_filename.toLowerCase().includes(q)
        const matchesRole = item.job_description_title.toLowerCase().includes(q)
        const matchesSession = item.session_id.toLowerCase().includes(q)
        const matchesSummary = (item.evaluation_summary || '').toLowerCase().includes(q)

        if (!matchesFilename && !matchesRole && !matchesSession && !matchesSummary) {
          return false
        }
      }

      return true
    })
  }, [evaluations, roleFilter, scoreFilter, searchQuery])

  const handleClearFilters = () => {
    setSearchQuery('')
    setRoleFilter('All')
    setScoreFilter('all')
  }

  // Export currently filtered real evaluation records safely to RFC 4180 CSV
  const handleExportCsv = () => {
    if (filteredEvaluations.length === 0) return

    const headers = [
      'Evaluation ID',
      'Resume Filename',
      'Job Title',
      'Session ID',
      'Overall Score',
      'Max Score',
      'Evaluated At',
      'Evaluation Summary',
    ]

    const rows: string[] = []
    rows.push(headers.map(escapeCsvCell).join(','))

    for (const item of filteredEvaluations) {
      const overallScoreFormatted =
        item.overall_score !== null && item.overall_score !== undefined
          ? item.overall_score.toFixed(1)
          : 'N/A'

      const row = [
        item.id,
        item.original_filename,
        item.job_description_title,
        item.session_id,
        overallScoreFormatted,
        item.max_overall_score ?? 100,
        item.evaluated_at || 'N/A',
        item.evaluation_summary || 'N/A',
      ]
      rows.push(row.map(escapeCsvCell).join(','))
    }

    const csvContent = rows.join('\r\n')
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.setAttribute(
      'download',
      `candidates_directory_${new Date().toISOString().slice(0, 10)}.csv`
    )
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }

  // =========================================================
  // VIEW: INSPECT PERSISTED EVALUATION (Read-Only Detail View)
  // =========================================================
  if (selectedEvaluationId) {
    const selectedItem = evaluations.find((e) => e.id === selectedEvaluationId)

    return (
      <div className="dashboard-layout">
        <Sidebar
          activeScreen="candidates"
          onNavigate={onNavigate}
          sidebarOpen={sidebarOpen}
          onCloseSidebar={() => setSidebarOpen(false)}
        />

        <main className="dashboard-main">
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
                    onClick={handleReturnToDirectory}
                  >
                    ← Back to Candidates Directory
                  </button>
                </div>
                <h1 className="welcome-heading">Persisted Evaluation Inspection</h1>
                <p className="welcome-subtext">
                  Viewing recorded evaluation for <strong>{selectedItem?.original_filename || 'Candidate Resume'}</strong>
                </p>
              </div>
            </div>
          </header>

          <div className="candidates-page-content">
            {isLoadingDetail && (
              <div style={{ padding: '40px 20px', textAlign: 'center' }}>
                <div className="btn-inline-spinner" style={{ width: '32px', height: '32px', margin: '0 auto 12px' }} aria-hidden="true" />
                <p style={{ color: '#64748b', fontSize: '14px' }}>Loading persisted evaluation details...</p>
              </div>
            )}

            {detailError && !isLoadingDetail && (
              <div className="wizard-batch-error-banner" role="alert" style={{ margin: '16px 0' }}>
                <strong>Failed to load evaluation details</strong>
                <p>{detailError}</p>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => selectedItem && handleInspect(selectedItem)}
                  style={{ marginTop: '8px' }}
                >
                  ↻ Retry
                </button>
              </div>
            )}

            {evalDetail && !isLoadingDetail && (
              <>
                {/* Hero Card */}
                <section className="candidate-hero-card" aria-labelledby="eval-detail-title">
                  <div className="candidate-hero-main">
                    <div
                      className="candidate-avatar-large"
                      aria-hidden="true"
                      style={{
                        background: 'linear-gradient(135deg, #1e40af, #2563eb)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: '26px',
                        color: '#ffffff',
                      }}
                    >
                      📄
                    </div>

                    <div className="candidate-hero-info">
                      <h2 id="eval-detail-title" className="candidate-name-lg">
                        {evalDetail.original_filename}
                      </h2>
                      <p className="candidate-headline-lg" style={{ margin: '4px 0 8px', color: '#475569' }}>
                        Target Role: <strong>{evalDetail.job_title}</strong>
                      </p>
                      <div className="candidate-contact-strip" style={{ display: 'flex', gap: '8px', fontSize: '12.5px', color: '#64748b', flexWrap: 'wrap' }}>
                        <span>Session ID: <code>{evalDetail.session_id.slice(0, 8)}...</code></span>
                        <span className="contact-sep">•</span>
                        <span>
                          Evaluated:{' '}
                          <strong>
                            {evalDetail.evaluated_at
                              ? new Date(evalDetail.evaluated_at).toLocaleString()
                              : 'Recorded'}
                          </strong>
                        </span>
                        {evalDetail.model_name && (
                          <>
                            <span className="contact-sep">•</span>
                            <span>Model: <code>{evalDetail.model_name}</code></span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Persisted Rubric Score Block */}
                  <div
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '4px',
                      padding: '14px 20px',
                      backgroundColor: '#f8fafc',
                      border: '1px solid #e2e8f0',
                      borderRadius: '8px',
                      minWidth: '220px',
                      textAlign: 'center',
                    }}
                  >
                    <span style={{ fontSize: '12px', color: '#64748b', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                      Persisted Rubric Score
                    </span>
                    <span style={{ fontSize: '26px', fontWeight: 800, color: '#15803d' }}>
                      {evalDetail.overall_score !== null
                        ? `${evalDetail.overall_score} / ${evalDetail.max_overall_score}`
                        : 'Unscored'}
                    </span>
                    <span style={{ fontSize: '11px', color: '#94a3b8' }}>
                      Recorded from local evaluation
                    </span>
                  </div>
                </section>

                {/* Ground Truth Notice */}
                <div
                  className="panel-box"
                  style={{
                    backgroundColor: '#f8fafc',
                    border: '1px solid #e2e8f0',
                    borderLeft: '4px solid #2563eb',
                    borderRadius: '8px',
                    padding: '14px 18px',
                  }}
                >
                  <strong style={{ fontSize: '13px', color: '#1e293b' }}>
                    Persisted Evaluation Record
                  </strong>
                  <p style={{ fontSize: '12.5px', color: '#475569', margin: '4px 0 0', lineHeight: 1.5 }}>
                    This evaluation is grounded strictly on the text found in <code>{evalDetail.original_filename}</code> against stated criteria.
                    Absence of documented evidence in the resume is not proof of lack of skill. No new evaluation, inference, or external API call was triggered to view this record.
                  </p>
                </div>

                {/* Evaluation Summary */}
                <div className="panel-box" style={{ backgroundColor: '#ffffff', borderRadius: '10px', padding: '20px', border: '1px solid #e2e8f0' }}>
                  <h3 style={{ fontSize: '15px', fontWeight: 700, color: '#0f172a', margin: '0 0 8px' }}>
                    Evaluation Summary
                  </h3>
                  <p style={{ fontSize: '13.5px', color: '#334155', lineHeight: 1.6, margin: 0 }}>
                    {evalDetail.evaluation_summary}
                  </p>
                </div>

                {/* Criteria Rubric Breakdown */}
                <div className="panel-box" style={{ backgroundColor: '#ffffff', borderRadius: '10px', padding: '20px', border: '1px solid #e2e8f0' }}>
                  <h3 style={{ fontSize: '15px', fontWeight: 700, color: '#0f172a', margin: '0 0 16px' }}>
                    Criteria Rubric Breakdown ({evalDetail.rubric?.length || 0})
                  </h3>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                    {evalDetail.rubric?.map((item, idx) => (
                      <div
                        key={`${item.criterion}-${idx}`}
                        style={{
                          padding: '14px 16px',
                          borderRadius: '8px',
                          border: '1px solid #e2e8f0',
                          backgroundColor: '#f8fafc',
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <strong style={{ fontSize: '14px', color: '#0f172a' }}>{item.criterion}</strong>
                            <span className="cand-skill-chip" style={{ fontSize: '11px', textTransform: 'capitalize' }}>
                              {item.criterion_type}
                            </span>
                          </div>

                          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                            {item.evidence_status === 'documented' ? (
                              <span style={{ fontSize: '11.5px', fontWeight: 600, color: '#15803d', backgroundColor: '#dcfce7', padding: '2px 8px', borderRadius: '4px' }}>
                                ✓ Documented
                              </span>
                            ) : (
                              <span style={{ fontSize: '11.5px', fontWeight: 600, color: '#92400e', backgroundColor: '#fef3c7', padding: '2px 8px', borderRadius: '4px' }}>
                                ○ Not Documented
                              </span>
                            )}
                            <span style={{ fontSize: '13px', fontWeight: 700, color: '#1e293b' }}>
                              Score: {item.score} / {item.max_score}
                            </span>
                          </div>
                        </div>

                        <p style={{ fontSize: '13px', color: '#475569', margin: '10px 0 0', lineHeight: 1.5 }}>
                          {item.explanation}
                        </p>

                        {item.evidence_quotes && item.evidence_quotes.length > 0 && (
                          <div style={{ marginTop: '10px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                            <span style={{ fontSize: '11.5px', fontWeight: 600, color: '#64748b' }}>
                              Supporting Evidence Quotes:
                            </span>
                            {item.evidence_quotes.map((quote, qIdx) => (
                              <blockquote
                                key={qIdx}
                                style={{
                                  margin: 0,
                                  padding: '8px 12px',
                                  backgroundColor: '#ffffff',
                                  borderLeft: '3px solid #2563eb',
                                  fontSize: '12.5px',
                                  color: '#334155',
                                  fontStyle: 'italic',
                                  borderRadius: '0 4px 4px 0',
                                }}
                              >
                                &ldquo;{quote}&rdquo;
                              </blockquote>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>

                {/* Missing & Unverified Criteria */}
                {((evalDetail.missing_criteria && evalDetail.missing_criteria.length > 0) ||
                  (evalDetail.unverified_criteria && evalDetail.unverified_criteria.length > 0)) && (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px' }}>
                    {evalDetail.missing_criteria && evalDetail.missing_criteria.length > 0 && (
                      <div className="panel-box" style={{ backgroundColor: '#fffbeb', border: '1px solid #fde68a', borderRadius: '8px', padding: '16px' }}>
                        <strong style={{ fontSize: '13px', color: '#92400e' }}>
                          Missing Criteria (Not Found in Resume):
                        </strong>
                        <ul style={{ margin: '8px 0 0', paddingLeft: '20px', fontSize: '12.5px', color: '#78350f' }}>
                          {evalDetail.missing_criteria.map((c, idx) => (
                            <li key={idx}>{c}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {evalDetail.unverified_criteria && evalDetail.unverified_criteria.length > 0 && (
                      <div className="panel-box" style={{ backgroundColor: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '16px' }}>
                        <strong style={{ fontSize: '13px', color: '#475569' }}>
                          Unverified / Ambiguous Documentation:
                        </strong>
                        <ul style={{ margin: '8px 0 0', paddingLeft: '20px', fontSize: '12.5px', color: '#334155' }}>
                          {evalDetail.unverified_criteria.map((c, idx) => (
                            <li key={idx}>{c}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}

                {/* Disclaimer */}
                {evalDetail.disclaimer && (
                  <div style={{ padding: '12px 16px', backgroundColor: '#f1f5f9', borderRadius: '6px', fontSize: '11.5px', color: '#64748b', lineHeight: 1.4 }}>
                    <strong>Disclaimer:</strong> {evalDetail.disclaimer}
                  </div>
                )}

                {/* Footer Navigation */}
                <div style={{ display: 'flex', justifyContent: 'flex-start', paddingTop: '8px' }}>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={handleReturnToDirectory}
                  >
                    ← Back to Candidates Directory
                  </button>
                </div>
              </>
            )}
          </div>
        </main>
      </div>
    )
  }

  // =========================================================
  // VIEW: CANDIDATES DIRECTORY (Main Table View)
  // =========================================================
  return (
    <div className="dashboard-layout">
      {/* Shared Dark Left Sidebar */}
      <Sidebar
        activeScreen="candidates"
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
              <h1 className="welcome-heading">Candidates Directory</h1>
              <p className="welcome-subtext">
                Persisted candidate evaluations across screening sessions.
              </p>
            </div>
          </div>

          <div className="topbar-actions" style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={handleExportCsv}
              disabled={filteredEvaluations.length === 0}
              title={
                filteredEvaluations.length === 0
                  ? 'No candidate records to export'
                  : `Export ${filteredEvaluations.length} candidate evaluation record${filteredEvaluations.length === 1 ? '' : 's'} as CSV`
              }
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
                style={{ marginRight: '4px' }}
              >
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
              <span>Export CSV</span>
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={fetchCandidatesDirectory}
              disabled={isLoading}
              title="Refresh candidate evaluations directory"
            >
              {isLoading ? 'Refreshing...' : '↻ Refresh Directory'}
            </button>
          </div>
        </header>

        <div className="candidates-page-content">
          {/* Ground Truth Directory Banner */}
          <div
            className="panel-box"
            style={{
              backgroundColor: '#f8fafc',
              border: '1px solid #e2e8f0',
              borderLeft: '4px solid #2563eb',
              borderRadius: '8px',
              padding: '14px 18px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
              <span aria-hidden="true" style={{ fontSize: '15px' }}>📋</span>
              <strong style={{ fontSize: '13px', color: '#1e293b' }}>
                Persisted Evaluation Records
              </strong>
            </div>
            <p style={{ fontSize: '12.5px', color: '#475569', margin: 0, lineHeight: 1.5 }}>
              Each record represents an evaluation performed during a screening session against Job Description criteria.
              Resumes are identified by their actual source filename and screening session.
              No artificial scores, rankings, or automated recommendations are calculated on this page.
            </p>
          </div>

          {/* Quick Metrics Strip */}
          <div className="candidates-stats-strip">
            <div className="cand-stat-pill">
              <span className="cand-stat-label">Total Evaluated Resumes</span>
              <span className="cand-stat-val">{evaluations.length}</span>
            </div>
            <div className="cand-stat-pill">
              <span className="cand-stat-label">Evaluated with Rubric Score</span>
              <span className="cand-stat-val cand-val-green">
                {evaluations.filter((e) => e.overall_score !== null).length}
              </span>
            </div>
            <div className="cand-stat-pill">
              <span className="cand-stat-label">Target Roles</span>
              <span className="cand-stat-val cand-val-blue">{distinctRoles.length}</span>
            </div>
            <div className="cand-stat-pill">
              <span className="cand-stat-label">Screening Sessions</span>
              <span className="cand-stat-val">{uniqueSessionsCount}</span>
            </div>
          </div>

          {/* Search & Filter Toolbar */}
          <div className="candidates-controls-bar">
            {/* Search Input */}
            <div className="candidates-search-box">
              <svg
                className="candidates-search-icon"
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
                className="candidates-search-input"
                placeholder="Search by filename, role, session ID, or summary..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                aria-label="Search candidate evaluations"
              />
              {searchQuery && (
                <button
                  type="button"
                  className="candidates-clear-search"
                  onClick={() => setSearchQuery('')}
                  aria-label="Clear search query"
                >
                  ✕
                </button>
              )}
            </div>

            {/* Role Filter */}
            {distinctRoles.length > 0 && (
              <div className="candidates-filter-group">
                <label htmlFor="role-filter-select" className="candidates-filter-label">
                  Role:
                </label>
                <select
                  id="role-filter-select"
                  className="candidates-category-select"
                  value={roleFilter}
                  onChange={(e) => setRoleFilter(e.target.value)}
                >
                  <option value="All">All Roles</option>
                  {distinctRoles.map((role) => (
                    <option key={role} value={role}>
                      {role}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Score Filter */}
            <div className="candidates-filter-group">
              <label htmlFor="score-filter-select" className="candidates-filter-label">
                Score:
              </label>
              <select
                id="score-filter-select"
                className="candidates-category-select"
                value={scoreFilter}
                onChange={(e) => setScoreFilter(e.target.value as 'all' | 'scored' | 'unscored')}
              >
                <option value="all">All Records</option>
                <option value="scored">With Rubric Score</option>
                <option value="unscored">Unscored</option>
              </select>
            </div>

            {/* Active filters clear */}
            {(searchQuery || roleFilter !== 'All' || scoreFilter !== 'all') && (
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={handleClearFilters}
                style={{ fontSize: '12px' }}
              >
                Clear Filters
              </button>
            )}

            <div className="candidates-count-indicator">
              Showing {filteredEvaluations.length} of {evaluations.length} records
            </div>
          </div>

          {/* Loading State */}
          {isLoading && (
            <div style={{ padding: '60px 20px', textAlign: 'center' }}>
              <div className="btn-inline-spinner" style={{ width: '32px', height: '32px', margin: '0 auto 12px' }} aria-hidden="true" />
              <p style={{ color: '#64748b', fontSize: '14px' }}>Loading candidate evaluations directory...</p>
            </div>
          )}

          {/* Error State with Retry Button */}
          {error && !isLoading && (
            <div className="wizard-batch-error-banner" role="alert" style={{ margin: '16px 0' }}>
              <strong>Failed to load candidate evaluations directory</strong>
              <p>{error}</p>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={fetchCandidatesDirectory}
                style={{ marginTop: '8px' }}
              >
                ↻ Retry
              </button>
            </div>
          )}

          {/* Table Container Card */}
          {!isLoading && !error && (
            <section className="table-container-card" aria-labelledby="candidates-table-title">
              <div className="table-header-row">
                <div>
                  <h2 id="candidates-table-title" className="section-title">
                    Persisted Evaluations
                  </h2>
                  <p className="section-subtitle">
                    Real evaluations recorded from screening sessions with persisted rubric scores.
                  </p>
                </div>
                <span className="sample-indicator-badge">
                  Source: Persisted Resume Evaluations
                </span>
              </div>

              {evaluations.length === 0 ? (
                /* Empty Database State */
                <div className="candidates-empty-state">
                  <div className="empty-icon" aria-hidden="true">📋</div>
                  <h3 className="empty-title">No Candidate Evaluations Recorded</h3>
                  <p className="empty-sub">
                    No resumes have been evaluated yet. Evaluations are recorded when candidate resumes are evaluated against Job Description criteria in a screening session.
                  </p>
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() => onNavigate('sessions')}
                  >
                    Go to Screening Sessions →
                  </button>
                </div>
              ) : filteredEvaluations.length === 0 ? (
                /* Filter Empty State */
                <div className="candidates-empty-state">
                  <div className="empty-icon" aria-hidden="true">🔍</div>
                  <h3 className="empty-title">No matching evaluations found</h3>
                  <p className="empty-sub">
                    No evaluations match your search query &ldquo;{searchQuery}&rdquo; and active filters.
                  </p>
                  <button
                    type="button"
                    className="btn btn-secondary btn-clear-filters"
                    onClick={handleClearFilters}
                  >
                    Clear Filters
                  </button>
                </div>
              ) : (
                /* Data Table */
                <div className="table-responsive-wrapper">
                  <table className="results-table">
                    <thead>
                      <tr>
                        <th scope="col" style={{ width: '44px', textAlign: 'center' }}>#</th>
                        <th scope="col">Resume File</th>
                        <th scope="col">Job Description / Role</th>
                        <th scope="col">Session</th>
                        <th scope="col">Persisted Rubric Score</th>
                        <th scope="col">Evaluated Date</th>
                        <th scope="col">Evaluation Summary</th>
                        <th scope="col" style={{ textAlign: 'right' }}>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredEvaluations.map((item, idx) => (
                        <tr key={item.id}>
                          {/* Sequential Index */}
                          <td style={{ textAlign: 'center', color: '#94a3b8', fontWeight: 600 }}>
                            {idx + 1}
                          </td>

                          {/* Resume File */}
                          <td className="cell-cand-name">
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                              <span aria-hidden="true" style={{ fontSize: '16px' }}>📄</span>
                              <div>
                                <strong style={{ fontSize: '13.5px', color: '#0f172a' }}>
                                  {item.original_filename}
                                </strong>
                              </div>
                            </div>
                          </td>

                          {/* Role / Job Description */}
                          <td>
                            <span style={{ fontSize: '13px', color: '#334155', fontWeight: 500 }}>
                              {item.job_description_title || 'Untitled Role'}
                            </span>
                          </td>

                          {/* Screening Session */}
                          <td>
                            <code style={{ fontSize: '11.5px', color: '#475569' }}>
                              {item.session_id.slice(0, 8)}...
                            </code>
                          </td>

                          {/* Persisted Rubric Score */}
                          <td>
                            {item.overall_score !== null ? (
                              <span
                                className="badge"
                                title="Persisted rubric overall score from local evaluation"
                                style={{
                                  backgroundColor: '#eff6ff',
                                  color: '#1d4ed8',
                                  border: '1px solid #bfdbfe',
                                  fontSize: '12px',
                                  fontWeight: 700,
                                  padding: '3px 8px',
                                  borderRadius: '6px',
                                }}
                              >
                                {item.overall_score} / {item.max_overall_score}
                              </span>
                            ) : (
                              <span style={{ fontSize: '12px', color: '#94a3b8' }}>Unscored</span>
                            )}
                          </td>

                          {/* Evaluated Date */}
                          <td>
                            <span style={{ fontSize: '12px', color: '#64748b', whiteSpace: 'nowrap' }}>
                              {item.evaluated_at
                                ? new Date(item.evaluated_at).toLocaleDateString()
                                : '—'}
                            </span>
                          </td>

                          {/* Summary snippet */}
                          <td style={{ maxWidth: '280px' }}>
                            <p
                              style={{
                                fontSize: '12px',
                                color: '#475569',
                                margin: 0,
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                whiteSpace: 'nowrap',
                              }}
                              title={item.evaluation_summary}
                            >
                              {item.evaluation_summary || 'No summary recorded.'}
                            </p>
                          </td>

                          {/* Action Button */}
                          <td style={{ textAlign: 'right' }}>
                            <button
                              type="button"
                              className="table-action-btn"
                              onClick={() => handleInspect(item)}
                              aria-label={`View evaluation for ${item.original_filename}`}
                            >
                              View Evaluation
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          )}
        </div>
      </main>
    </div>
  )
}

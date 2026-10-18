import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { Sidebar, type AppScreen } from './Sidebar'
import { apiFetch } from './api'
import { useAuth } from './auth'
import './Dashboard.css'
import './Screening.css'

/* ----------------------------------------------------------------------------
   Types (mirror backend/screening_api.py)
---------------------------------------------------------------------------- */
type Tier = 'strong' | 'good' | 'partial' | 'low'
type View = 'loading' | 'processing' | 'results' | 'candidate' | 'chat'

interface Requirement {
  name: string
  type: 'required' | 'preferred' | 'experience'
}

interface CandidateSummary {
  id: string
  resume_id: string
  name: string
  email: string | null
  filename: string
  experience_years: number | null
  match_percent: number
  tier: Tier
  skills: string[]
  shortlisted: boolean
  matched_count: number
  total_requirements: number
  scoring_mode: string | null
}

interface ResultsPayload {
  session: {
    id: string
    status: string
    job_description_id: string
    job_title: string
    created_at: string | null
    chat_available: boolean
  }
  counts: Record<string, number>
  shortlisted_count: number
  requirements: Requirement[]
  candidates: CandidateSummary[]
  failed: { filename: string; error: string }[]
  scoring_mode: string | null
  warning: string | null
}

interface RequirementResult {
  name: string
  type: string
  status: 'met' | 'partial' | 'missing'
  evidence: string
  note: string
}

interface CandidateDetailPayload extends CandidateSummary {
  session_id: string
  session_status: string
  job_title: string
  requirement_results: RequirementResult[]
  matched: string[]
  partial: string[]
  missing: string[]
  highlights: string[]
  projects: string[]
  experience: { title: string; company: string; period: string }[]
  assessment: string
}

interface ProgressStep {
  key: string
  label: string
  status: 'pending' | 'running' | 'done'
  at: string | null
}

interface ProgressPayload {
  status: 'idle' | 'running' | 'completed' | 'failed'
  stage: string | null
  percent: number
  total: number
  processed: number
  remaining: number
  eta_seconds: number | null
  steps: ProgressStep[]
  error: string | null
  scoring_mode: string | null
}

interface ChatCandidate {
  id: string
  resume_id: string
  name: string
  match_percent: number
  tier: Tier
  years: number | null
  snippet: string
}

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  text: string
  time: string
  candidates?: ChatCandidate[]
  allIds?: string[]
  total?: number
}

const PAGE_SIZE = 10

const TIER_LABEL: Record<Tier, string> = {
  strong: 'Strong Match',
  good: 'Good Match',
  partial: 'Partial Match',
  low: 'Low Match',
}

/* ----------------------------------------------------------------------------
   Helpers
---------------------------------------------------------------------------- */
async function readError(res: Response, fallback: string): Promise<string> {
  try {
    const data = await res.json()
    if (typeof data?.detail === 'string') return data.detail
  } catch {
    /* ignore */
  }
  return `${fallback} (HTTP ${res.status})`
}

function nowTime(): string {
  return new Date().toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}

function fmtTime(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}

function fmtEta(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return '—'
  if (seconds < 45) return '< 1 min'
  return `~ ${Math.ceil(seconds / 60)} min`
}

function fmtYears(y: number | null): string {
  if (y === null || y === undefined) return '—'
  return `${Number.isInteger(y) ? y : y.toFixed(1)} yrs`
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase()
}

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function Highlight({ text, term }: { text: string; term: string }) {
  if (!term || term.toLowerCase().startsWith('experience:')) return <>{text}</>
  const parts = text.split(new RegExp(`(${escapeRegExp(term)})`, 'ig'))
  return (
    <>
      {parts.map((p, i) =>
        p.toLowerCase() === term.toLowerCase() ? (
          <span key={i} className="rs-hl">
            {p}
          </span>
        ) : (
          <span key={i}>{p}</span>
        ),
      )}
    </>
  )
}

function CheckIcon({ size = 11 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  )
}

function XIcon({ size = 10 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  )
}

function Shell({
  title,
  subtitle,
  onNavigate,
  children,
}: {
  title: string
  subtitle: string
  onNavigate: (screen: AppScreen) => void
  children: ReactNode
}) {
  const [open, setOpen] = useState(false)
  return (
    <div className="dashboard-layout">
      <Sidebar activeScreen="new-screening" onNavigate={onNavigate} sidebarOpen={open} onCloseSidebar={() => setOpen(false)} />
      <main className="dashboard-main">
        <header className="dashboard-topbar">
          <div className="topbar-left">
            <button type="button" className="mobile-nav-toggle" onClick={() => setOpen(true)} aria-label="Open sidebar navigation">
              ☰
            </button>
            <div className="header-titles">
              <h1 className="welcome-heading">{title}</h1>
              <p className="welcome-subtext">{subtitle}</p>
            </div>
          </div>
        </header>
        <div className="dashboard-content">
          <div className="rs-wrap">{children}</div>
        </div>
      </main>
    </div>
  )
}

/* ----------------------------------------------------------------------------
   Workspace
---------------------------------------------------------------------------- */
export interface ScreeningWorkspaceProps {
  sessionId: string
  /** 'processing' starts the pipeline; 'results' just opens existing results. */
  initialView: 'processing' | 'results'
  jobTitle?: string
  onNavigate: (screen: AppScreen) => void
  onExit: () => void
  /** Return to the upload step to add more resumes (only while the session is active). */
  onAddResumes?: () => void
}

export function ScreeningWorkspace({ sessionId, initialView, jobTitle, onNavigate, onExit, onAddResumes }: ScreeningWorkspaceProps) {
  const { isPrivileged } = useAuth()
  const [view, setView] = useState<View>('loading')
  const [progress, setProgress] = useState<ProgressPayload | null>(null)
  const [results, setResults] = useState<ResultsPayload | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [filterIds, setFilterIds] = useState<string[] | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [suggestions, setSuggestions] = useState<string[]>([])
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  const loadResults = useCallback(async (): Promise<ResultsPayload | null> => {
    const res = await apiFetch(`/api/screening-sessions/${sessionId}/results`)
    if (!res.ok) throw new Error(await readError(res, 'Failed to load results'))
    const data = (await res.json()) as ResultsPayload
    if (mounted.current) setResults(data)
    return data
  }, [sessionId])

  const fetchProgress = useCallback(async (): Promise<ProgressPayload> => {
    const res = await apiFetch(`/api/screening-sessions/${sessionId}/progress`)
    if (!res.ok) throw new Error(await readError(res, 'Failed to read progress'))
    const data = (await res.json()) as ProgressPayload
    if (mounted.current) setProgress(data)
    return data
  }, [sessionId])

  const startRun = useCallback(async () => {
    setError(null)
    try {
      const res = await apiFetch(`/api/screening-sessions/${sessionId}/start`, { method: 'POST' })
      if (!res.ok) throw new Error(await readError(res, 'Could not start screening'))
      const data = (await res.json()) as ProgressPayload
      if (mounted.current) {
        setProgress(data)
        setView('processing')
      }
    } catch (e) {
      if (mounted.current) {
        setError(e instanceof Error ? e.message : 'Could not start screening')
        setView('processing')
      }
    }
  }, [sessionId])

  // Initial load
  useEffect(() => {
    let cancelled = false
    async function init() {
      try {
        if (initialView === 'processing') {
          await startRun()
          return
        }
        const p = await fetchProgress()
        if (cancelled) return
        if (p.status === 'running') {
          setView('processing')
          return
        }
        await loadResults()
        if (!cancelled) setView('results')
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'Failed to load session')
          setView('results')
        }
      }
    }
    init()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId])

  // Poll progress while processing
  useEffect(() => {
    if (view !== 'processing') return
    const timer = window.setInterval(async () => {
      try {
        const p = await fetchProgress()
        if (p.status === 'completed') {
          window.clearInterval(timer)
          await loadResults()
          if (mounted.current) setView('results')
        } else if (p.status === 'failed') {
          window.clearInterval(timer)
        }
      } catch {
        /* transient network errors: keep polling */
      }
    }, 1500)
    return () => window.clearInterval(timer)
  }, [view, fetchProgress, loadResults])

  const openCandidate = (id: string) => {
    setSelectedId(id)
    setView('candidate')
  }

  const chatEnabled = isPrivileged && !!results?.session.chat_available

  /* ----------------------------- Processing ----------------------------- */
  if (view === 'loading') {
    return (
      <Shell title="Screening" subtitle="Loading session…" onNavigate={onNavigate}>
        <div className="rs-card rs-empty">Loading…</div>
      </Shell>
    )
  }

  if (view === 'processing') {
    const pct = Math.round(progress?.percent ?? 0)
    const failed = progress?.status === 'failed' || !!error
    return (
      <Shell title="Processing Resumes" subtitle="Your resumes are being processed. This may take a few minutes." onNavigate={onNavigate}>
        {failed && (
          <div className="rs-banner rs-banner-err" role="alert">
            <div style={{ flex: 1 }}>
              <strong>Processing stopped.</strong> {error || progress?.error}
            </div>
            <div className="rs-btn-row">
              <button type="button" className="rs-btn rs-btn-sm" onClick={startRun}>
                Retry
              </button>
              <button type="button" className="rs-btn rs-btn-sm" onClick={onExit}>
                Back
              </button>
            </div>
          </div>
        )}
        <div className="rs-card">
          <div className="rs-progress-top">
            <span className="rs-progress-label">Overall Progress</span>
            <span className="rs-progress-pct">{pct}%</span>
          </div>
          <div className="rs-bar" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
            <div className="rs-bar-fill" style={{ width: `${pct}%` }} />
          </div>
          <div className="rs-stats">
            <div className="rs-stat">
              <div className="rs-stat-val">{progress?.processed ?? 0}</div>
              <div className="rs-stat-lbl">Processed</div>
            </div>
            <div className="rs-stat">
              <div className="rs-stat-val">{progress?.remaining ?? 0}</div>
              <div className="rs-stat-lbl">Remaining</div>
            </div>
            <div className="rs-stat">
              <div className="rs-stat-val">{progress?.total ?? 0}</div>
              <div className="rs-stat-lbl">Total</div>
            </div>
            <div className="rs-stat">
              <div className="rs-stat-val">{progress?.status === 'running' ? fmtEta(progress.eta_seconds) : '—'}</div>
              <div className="rs-stat-lbl">Estimated time</div>
            </div>
          </div>
        </div>

        <div className="rs-card">
          <h3 className="rs-card-title">Current Activity</h3>
          <ul className="rs-activity">
            {(progress?.steps?.length ? progress.steps : []).map((s) => (
              <li key={s.key}>
                <span className={`rs-act-icon ${s.status === 'done' ? 'rs-act-done' : s.status === 'running' ? 'rs-act-run' : 'rs-act-pend'}`}>
                  {s.status === 'done' && <CheckIcon />}
                </span>
                <span className={s.status === 'pending' ? 'rs-pending-text' : ''}>{s.label}</span>
                <span className="rs-activity-time">{s.status === 'pending' ? 'Pending' : fmtTime(s.at)}</span>
              </li>
            ))}
            {(!progress || progress.steps.length === 0) && (
              <li>
                <span className="rs-act-icon rs-act-run" />
                <span>Starting…</span>
              </li>
            )}
          </ul>
        </div>
      </Shell>
    )
  }

  /* ----------------------------- Candidate ----------------------------- */
  if (view === 'candidate' && selectedId) {
    return (
      <CandidateScreen
        resultId={selectedId}
        canEdit={isPrivileged}
        chatEnabled={chatEnabled}
        onNavigate={onNavigate}
        onBack={() => setView('results')}
        onOpenChat={() => setView('chat')}
        onShortlistChange={(id, value) =>
          setResults((prev) =>
            prev
              ? {
                  ...prev,
                  shortlisted_count: prev.shortlisted_count + (value ? 1 : -1),
                  candidates: prev.candidates.map((c) => (c.id === id ? { ...c, shortlisted: value } : c)),
                }
              : prev,
          )
        }
      />
    )
  }

  /* ----------------------------- Chat ----------------------------- */
  if (view === 'chat') {
    return (
      <ChatScreen
        sessionId={sessionId}
        results={results}
        messages={messages}
        setMessages={setMessages}
        suggestions={suggestions}
        setSuggestions={setSuggestions}
        onNavigate={onNavigate}
        onBack={() => setView('results')}
        onOpenCandidate={openCandidate}
        onViewAll={(ids) => {
          setFilterIds(ids)
          setView('results')
        }}
      />
    )
  }

  /* ----------------------------- Results ----------------------------- */
  return (
    <ResultsScreen
      sessionId={sessionId}
      results={results}
      error={error}
      jobTitle={jobTitle}
      canEdit={isPrivileged}
      chatEnabled={chatEnabled}
      filterIds={filterIds}
      onClearFilterIds={() => setFilterIds(null)}
      onNavigate={onNavigate}
      onExit={onExit}
      onAddResumes={onAddResumes}
      onOpenCandidate={openCandidate}
      onOpenChat={() => setView('chat')}
      onReload={async () => {
        try {
          await loadResults()
        } catch (e) {
          setError(e instanceof Error ? e.message : 'Failed to reload')
        }
      }}
    />
  )
}

/* ----------------------------------------------------------------------------
   Results screen
---------------------------------------------------------------------------- */
function ResultsScreen({
  sessionId,
  results,
  error,
  jobTitle,
  canEdit,
  chatEnabled,
  filterIds,
  onClearFilterIds,
  onNavigate,
  onExit,
  onAddResumes,
  onOpenCandidate,
  onOpenChat,
  onReload,
}: {
  sessionId: string
  results: ResultsPayload | null
  error: string | null
  jobTitle?: string
  canEdit: boolean
  chatEnabled: boolean
  filterIds: string[] | null
  onClearFilterIds: () => void
  onNavigate: (screen: AppScreen) => void
  onExit: () => void
  onAddResumes?: () => void
  onOpenCandidate: (id: string) => void
  onOpenChat: () => void
  onReload: () => Promise<void>
}) {
  const [tier, setTier] = useState<'all' | Tier>('all')
  const [page, setPage] = useState(1)
  const [showFilters, setShowFilters] = useState(false)
  const [query, setQuery] = useState('')
  const [minMatch, setMinMatch] = useState(0)
  const [shortlistedOnly, setShortlistedOnly] = useState(false)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const candidates = useMemo(() => results?.candidates ?? [], [results])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    const idSet = filterIds ? new Set(filterIds) : null
    return candidates.filter((c) => {
      if (tier !== 'all' && c.tier !== tier) return false
      if (idSet && !idSet.has(c.resume_id)) return false
      if (c.match_percent < minMatch) return false
      if (shortlistedOnly && !c.shortlisted) return false
      if (q && !(c.name.toLowerCase().includes(q) || c.skills.some((s) => s.toLowerCase().includes(q)))) return false
      return true
    })
  }, [candidates, tier, filterIds, minMatch, shortlistedOnly, query])

  useEffect(() => {
    setPage(1)
  }, [tier, filterIds, minMatch, shortlistedOnly, query])

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const safePage = Math.min(page, pageCount)
  const rows = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE)
  const counts = results?.counts ?? {}

  const pageNumbers = useMemo(() => {
    const out: (number | '…')[] = []
    for (let p = 1; p <= pageCount; p++) {
      if (p === 1 || p === pageCount || Math.abs(p - safePage) <= 1) out.push(p)
      else if (out[out.length - 1] !== '…') out.push('…')
    }
    return out
  }, [pageCount, safePage])

  const exportCsv = async () => {
    setActionError(null)
    try {
      const res = await apiFetch(`/api/screening-sessions/${sessionId}/export.csv`)
      if (!res.ok) throw new Error(await readError(res, 'Export failed'))
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `screening-results-${sessionId.slice(0, 8)}.csv`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Export failed')
    }
  }

  const endSession = async () => {
    if (
      !window.confirm(
        'End this session? Uploaded resumes and their extracted text/embeddings will be permanently deleted. ' +
          'The candidate analysis stays saved, but chat and adding resumes will no longer be available.',
      )
    )
      return
    setBusy(true)
    setActionError(null)
    try {
      const res = await apiFetch(`/api/screening-sessions/${sessionId}/finish`, { method: 'POST' })
      if (!res.ok) throw new Error(await readError(res, 'Could not end session'))
      await onReload()
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Could not end session')
    } finally {
      setBusy(false)
    }
  }

  const title = results?.session.job_title || jobTitle || 'Job Description'
  const active = results?.session.status === 'draft'
  const tierCards: { key: 'all' | Tier; label: string }[] = [
    { key: 'all', label: 'All Candidates' },
    { key: 'strong', label: 'Strong Match' },
    { key: 'good', label: 'Good Match' },
    { key: 'partial', label: 'Partial Match' },
    { key: 'low', label: 'Low Match' },
  ]

  return (
    <Shell title="Screening Results" subtitle="AI-powered candidate analysis based on job requirements." onNavigate={onNavigate}>
      <div className="rs-head">
        <div>
          <p className="rs-sub" style={{ marginTop: 0 }}>
            Role: <strong style={{ color: '#0f172a' }}>{title}</strong>
            {results?.shortlisted_count ? <> • {results.shortlisted_count} shortlisted</> : null}
            {results && !active ? <> • Session ended</> : null}
          </p>
        </div>
        <div className="rs-head-actions">
          <div className="rs-btn-row">
            {canEdit && (
              <button
                type="button"
                className="rs-btn rs-btn-primary"
                onClick={onOpenChat}
                disabled={!chatEnabled}
                title={chatEnabled ? 'Ask a question about these candidates' : 'Chat is available while the session is active'}
              >
                Ask a Question
              </button>
            )}
            <button type="button" className="rs-btn" onClick={() => setShowFilters((v) => !v)} aria-expanded={showFilters}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
              </svg>
              Filters
            </button>
          </div>
          <div className="rs-btn-row">
            <button type="button" className="rs-link-btn" onClick={exportCsv}>
              Export CSV
            </button>
            {canEdit && active && onAddResumes && (
              <button type="button" className="rs-link-btn" onClick={onAddResumes}>
                + Add resumes
              </button>
            )}
            {canEdit && active && (
              <button type="button" className="rs-link-btn" onClick={endSession} disabled={busy}>
                {busy ? 'Ending…' : 'End session'}
              </button>
            )}
            <button type="button" className="rs-link-btn" onClick={onExit}>
              Exit
            </button>
          </div>
        </div>
      </div>

      {(error || actionError) && (
        <div className="rs-banner rs-banner-err" role="alert">
          {error || actionError}
        </div>
      )}
      {results?.warning && <div className="rs-banner rs-banner-warn">{results.warning}</div>}
      {results?.scoring_mode === 'heuristic' && (
        <div className="rs-banner rs-banner-info">
          The AI model was not reachable, so candidates were scored with keyword + semantic matching. Check Settings → LLM status, then re-run for AI analysis.
        </div>
      )}
      {results && results.failed.length > 0 && (
        <div className="rs-banner rs-banner-warn">
          <div>
            <strong>
              {results.failed.length} file{results.failed.length === 1 ? '' : 's'} could not be processed
            </strong>
            <ul>
              {results.failed.slice(0, 5).map((f) => (
                <li key={f.filename}>
                  {f.filename}: {f.error}
                </li>
              ))}
              {results.failed.length > 5 && <li>…and {results.failed.length - 5} more</li>}
            </ul>
          </div>
        </div>
      )}
      {filterIds && (
        <div className="rs-banner rs-banner-info">
          <span style={{ flex: 1 }}>Showing {filterIds.length} candidate(s) from your chat search.</span>
          <button type="button" className="rs-link-btn" onClick={onClearFilterIds}>
            Clear
          </button>
        </div>
      )}

      <div className="rs-tiers">
        {tierCards.map((t) => (
          <button
            key={t.key}
            type="button"
            className={`rs-tier rs-tier-${t.key} ${tier === t.key ? 'rs-tier-active' : ''}`}
            onClick={() => setTier(t.key)}
            aria-pressed={tier === t.key}
          >
            <span className="rs-tier-lbl">{t.label}</span>
            <span className="rs-tier-num">{counts[t.key] ?? 0}</span>
          </button>
        ))}
      </div>

      {showFilters && (
        <div className="rs-filters">
          <input className="rs-input" placeholder="Search name or skill" value={query} onChange={(e) => setQuery(e.target.value)} aria-label="Search candidates" />
          <label>
            Min match{' '}
            <select className="rs-input" value={minMatch} onChange={(e) => setMinMatch(Number(e.target.value))}>
              {[0, 45, 65, 80].map((v) => (
                <option key={v} value={v}>
                  {v === 0 ? 'Any' : `${v}%+`}
                </option>
              ))}
            </select>
          </label>
          <label style={{ display: 'inline-flex', gap: 6, alignItems: 'center' }}>
            <input type="checkbox" checked={shortlistedOnly} onChange={(e) => setShortlistedOnly(e.target.checked)} /> Shortlisted only
          </label>
          <button
            type="button"
            className="rs-link-btn"
            onClick={() => {
              setQuery('')
              setMinMatch(0)
              setShortlistedOnly(false)
              setTier('all')
            }}
          >
            Reset
          </button>
        </div>
      )}

      <div className="rs-card" style={{ padding: '8px 10px 18px' }}>
        {rows.length === 0 ? (
          <div className="rs-empty">{candidates.length === 0 ? 'No candidates were scored in this session.' : 'No candidates match the current filters.'}</div>
        ) : (
          <div className="rs-table-wrap">
            <table className="rs-table">
              <thead>
                <tr>
                  <th style={{ width: 44 }}>#</th>
                  <th>Candidate Name</th>
                  <th>Match</th>
                  <th>Key Skills</th>
                  <th>Experience</th>
                  <th style={{ width: 90 }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((c, i) => (
                  <tr key={c.id}>
                    <td>{(safePage - 1) * PAGE_SIZE + i + 1}</td>
                    <td>
                      <span className="rs-name">{c.name}</span>
                      {c.shortlisted && (
                        <span className="rs-star" title="Shortlisted">
                          ★
                        </span>
                      )}
                      <span className="rs-name-sub">{c.matched_count}/{c.total_requirements} requirements met</span>
                    </td>
                    <td>
                      <span className={`rs-pill rs-pill-${c.tier}`} title={TIER_LABEL[c.tier]}>
                        {Math.round(c.match_percent)}%
                      </span>
                    </td>
                    <td>
                      <div className="rs-chips">
                        {c.skills.slice(0, 3).map((s) => (
                          <span key={s} className="rs-chip">
                            {s}
                          </span>
                        ))}
                        {c.skills.length > 3 && <span className="rs-chip rs-chip-more">+{c.skills.length - 3}</span>}
                      </div>
                    </td>
                    <td>{fmtYears(c.experience_years)}</td>
                    <td>
                      <button type="button" className="rs-btn rs-btn-sm" onClick={() => onOpenCandidate(c.id)}>
                        View
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {pageCount > 1 && (
          <div className="rs-pager" aria-label="Pagination">
            <button type="button" className="rs-page" disabled={safePage === 1} onClick={() => setPage(safePage - 1)} aria-label="Previous page">
              ‹
            </button>
            {pageNumbers.map((p, i) =>
              p === '…' ? (
                <span key={`e${i}`} style={{ color: '#94a3b8' }}>
                  …
                </span>
              ) : (
                <button key={p} type="button" className={`rs-page ${p === safePage ? 'rs-page-active' : ''}`} onClick={() => setPage(p)}>
                  {p}
                </button>
              ),
            )}
            <button type="button" className="rs-page" disabled={safePage === pageCount} onClick={() => setPage(safePage + 1)} aria-label="Next page">
              ›
            </button>
          </div>
        )}
      </div>
    </Shell>
  )
}

/* ----------------------------------------------------------------------------
   Candidate detail screen
---------------------------------------------------------------------------- */
type CandTab = 'analysis' | 'highlights' | 'skills' | 'experience' | 'projects'

function CandidateScreen({
  resultId,
  canEdit,
  chatEnabled,
  onNavigate,
  onBack,
  onOpenChat,
  onShortlistChange,
}: {
  resultId: string
  canEdit: boolean
  chatEnabled: boolean
  onNavigate: (screen: AppScreen) => void
  onBack: () => void
  onOpenChat: () => void
  onShortlistChange: (id: string, value: boolean) => void
}) {
  const [detail, setDetail] = useState<CandidateDetailPayload | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<CandTab>('analysis')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let cancelled = false
    setDetail(null)
    setError(null)
    apiFetch(`/api/candidate-results/${resultId}`)
      .then(async (res) => {
        if (!res.ok) throw new Error(await readError(res, 'Failed to load candidate'))
        return (await res.json()) as CandidateDetailPayload
      })
      .then((d) => {
        if (!cancelled) setDetail(d)
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load candidate')
      })
    return () => {
      cancelled = true
    }
  }, [resultId])

  const toggleShortlist = async () => {
    if (!detail || busy) return
    setBusy(true)
    try {
      const next = !detail.shortlisted
      const res = await apiFetch(`/api/candidate-results/${detail.id}/shortlist`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ shortlisted: next }),
      })
      if (!res.ok) throw new Error(await readError(res, 'Could not update shortlist'))
      setDetail({ ...detail, shortlisted: next })
      onShortlistChange(detail.id, next)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not update shortlist')
    } finally {
      setBusy(false)
    }
  }

  const download = async () => {
    if (!detail) return
    try {
      const res = await apiFetch(`/api/candidate-results/${detail.id}/summary`)
      if (!res.ok) throw new Error(await readError(res, 'Download failed'))
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${detail.name.replace(/[^A-Za-z0-9_-]+/g, '_') || 'candidate'}-summary.md`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Download failed')
    }
  }

  const tabs: { key: CandTab; label: string }[] = [
    { key: 'analysis', label: 'Match Analysis' },
    { key: 'highlights', label: 'Resume Highlights' },
    { key: 'skills', label: 'Skills' },
    { key: 'experience', label: 'Experience' },
    { key: 'projects', label: 'Projects' },
  ]

  return (
    <Shell title="Candidate Details" subtitle="Evidence-based analysis against the job requirements." onNavigate={onNavigate}>
      <div className="rs-head" style={{ marginBottom: 6 }}>
        <button type="button" className="rs-back" onClick={onBack}>
          ← Back to Results
        </button>
        <div className="rs-btn-row">
          {canEdit && chatEnabled && (
            <button type="button" className="rs-btn" onClick={onOpenChat}>
              Ask a Question
            </button>
          )}
          {canEdit && detail && (
            <button type="button" className="rs-btn rs-btn-primary" onClick={toggleShortlist} disabled={busy}>
              {detail.shortlisted ? '★ Shortlisted' : '☆ Shortlist'}
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="rs-banner rs-banner-err" role="alert">
          {error}
        </div>
      )}
      {!detail && !error && <div className="rs-card rs-empty">Loading candidate…</div>}

      {detail && (
        <div className="rs-card">
          <div className="rs-cand-head">
            <div className="rs-cand-id">
              <div className="rs-avatar" aria-hidden="true">
                {initials(detail.name)}
              </div>
              <div>
                <h2 className="rs-cand-name">
                  {detail.name}
                  <span className={`rs-pill rs-pill-${detail.tier}`}>{Math.round(detail.match_percent)}% Match</span>
                </h2>
                <div className="rs-cand-meta">
                  {detail.email && <span>✉ {detail.email}</span>}
                  <span>🕒 {detail.experience_years !== null ? `${detail.experience_years} years experience` : 'Experience not stated'}</span>
                  <span>📄 {detail.filename}</span>
                </div>
              </div>
            </div>
            <button type="button" className="rs-btn" onClick={download}>
              ⬇ Download Summary
            </button>
          </div>

          <div className="rs-tabs" role="tablist">
            {tabs.map((t) => (
              <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} className={`rs-tab ${tab === t.key ? 'rs-tab-active' : ''}`} onClick={() => setTab(t.key)}>
                {t.label}
              </button>
            ))}
          </div>

          {tab === 'analysis' && <AnalysisTab d={detail} />}

          {tab === 'highlights' && (
            <>
              <h3 className="rs-sec-title">Resume Highlights</h3>
              {detail.highlights.length ? (
                <ul className="rs-list">
                  {detail.highlights.map((h, i) => (
                    <li key={i}>{h}</li>
                  ))}
                </ul>
              ) : (
                <p className="rs-empty">No highlights were extracted for this resume.</p>
              )}
            </>
          )}

          {tab === 'skills' && (
            <>
              <h3 className="rs-sec-title">Skills</h3>
              {detail.skills.length ? (
                <div className="rs-chips">
                  {detail.skills.map((s) => (
                    <span key={s} className="rs-chip">
                      {s}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="rs-empty">No skills were extracted for this resume.</p>
              )}
            </>
          )}

          {tab === 'experience' && (
            <>
              <h3 className="rs-sec-title">Experience</h3>
              {detail.experience.length ? (
                detail.experience.map((e, i) => (
                  <div key={i} className="rs-role">
                    <strong>{e.title || 'Role'}</strong> <span>{e.company && `· ${e.company}`}</span>
                    {e.period && <div style={{ color: '#94a3b8', fontSize: 12.5 }}>{e.period}</div>}
                  </div>
                ))
              ) : (
                <p className="rs-empty">No role history was extracted for this resume.</p>
              )}
            </>
          )}

          {tab === 'projects' && (
            <>
              <h3 className="rs-sec-title">Projects</h3>
              {detail.projects.length ? (
                <ul className="rs-list">
                  {detail.projects.map((p, i) => (
                    <li key={i}>{p}</li>
                  ))}
                </ul>
              ) : (
                <p className="rs-empty">No projects were extracted for this resume.</p>
              )}
            </>
          )}
        </div>
      )}
    </Shell>
  )
}

function AnalysisTab({ d }: { d: CandidateDetailPayload }) {
  const byStatus = (s: RequirementResult['status']) => d.requirement_results.filter((r) => r.status === s)
  const met = byStatus('met')
  const partial = byStatus('partial')
  const missing = byStatus('missing')
  const withEvidence = d.requirement_results.filter((r) => r.status !== 'missing' && r.evidence)

  const missingText = (r: RequirementResult) =>
    r.type === 'experience' ? r.note || r.name : `No ${r.name} experience found`

  return (
    <div className="rs-two-col">
      <div>
        <h3 className="rs-sec-title">Matched Requirements</h3>
        {met.length ? (
          <ul className="rs-req-list">
            {met.map((r) => (
              <li key={r.name}>
                <span className="rs-dot rs-dot-met">
                  <CheckIcon size={10} />
                </span>
                {r.name}
                {r.type === 'preferred' && <span style={{ color: '#94a3b8', fontSize: 12 }}> (preferred)</span>}
              </li>
            ))}
          </ul>
        ) : (
          <p style={{ color: '#94a3b8', fontSize: 13.5, margin: '0 0 20px' }}>No requirements were clearly matched.</p>
        )}

        {partial.length > 0 && (
          <>
            <h3 className="rs-sec-title">Partially Matched</h3>
            <ul className="rs-req-list">
              {partial.map((r) => (
                <li key={r.name}>
                  <span className="rs-dot rs-dot-partial">
                    <span style={{ fontSize: 10, fontWeight: 700, lineHeight: 1 }}>~</span>
                  </span>
                  <span>
                    {r.name}
                    {r.note && <span style={{ display: 'block', fontSize: 12, color: '#94a3b8' }}>{r.note}</span>}
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}

        <h3 className="rs-sec-title">Missing Requirements</h3>
        {missing.length ? (
          <ul className="rs-req-list">
            {missing.map((r) => (
              <li key={r.name}>
                <span className="rs-dot rs-dot-missing">
                  <XIcon />
                </span>
                {missingText(r)}
              </li>
            ))}
          </ul>
        ) : (
          <p style={{ color: '#94a3b8', fontSize: 13.5, margin: 0 }}>No missing requirements.</p>
        )}
      </div>

      <div>
        <h3 className="rs-sec-title">Evidence from Resume</h3>
        {withEvidence.length ? (
          withEvidence.map((r) => (
            <div key={r.name} className="rs-ev">
              <span className="rs-ev-q" aria-hidden="true">
                “
              </span>
              <div>
                <Highlight text={r.evidence} term={r.name} />
                <span className="rs-ev-note">Supports: {r.name}</span>
              </div>
            </div>
          ))
        ) : (
          <p style={{ color: '#94a3b8', fontSize: 13.5 }}>No direct resume evidence was found for the requirements.</p>
        )}

        <div className="rs-assess">
          <h3 className="rs-sec-title">Assessment</h3>
          <div className="rs-assess-box">{d.assessment || 'No assessment available.'}</div>
          <p style={{ fontSize: 11.5, color: '#94a3b8', marginTop: 8 }}>
            AI-assisted analysis based only on the resume text. The recruiter makes the final decision.
          </p>
        </div>
      </div>
    </div>
  )
}

/* ----------------------------------------------------------------------------
   Chat screen
---------------------------------------------------------------------------- */
function ChatScreen({
  sessionId,
  results,
  messages,
  setMessages,
  suggestions,
  setSuggestions,
  onNavigate,
  onBack,
  onOpenCandidate,
  onViewAll,
}: {
  sessionId: string
  results: ResultsPayload | null
  messages: ChatMessage[]
  setMessages: (updater: (prev: ChatMessage[]) => ChatMessage[]) => void
  suggestions: string[]
  setSuggestions: (s: string[]) => void
  onNavigate: (screen: AppScreen) => void
  onBack: () => void
  onOpenCandidate: (id: string) => void
  onViewAll: (ids: string[]) => void
}) {
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)

  const defaults = useMemo(() => {
    const skills = (results?.requirements ?? []).filter((r) => r.type !== 'experience').map((r) => r.name)
    const a = skills[0] ?? 'Python'
    const b = skills[1] ?? 'AWS'
    return [
      `Find candidates with ${a} experience`,
      `Which of these have ${b}?`,
      `Show candidates without ${b}`,
      'Find candidates with 5+ years',
      'Compare top 3 candidates',
      skills[2] ? `Show candidates with ${skills[2]}` : 'Who are the top 5 candidates?',
      'Find other candidates like these',
    ]
  }, [results])

  const list = suggestions.length ? suggestions : defaults

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, loading])

  const send = async (text: string) => {
    const msg = text.trim()
    if (!msg || loading) return
    setInput('')
    setMessages((prev) => [...prev, { id: `u${Date.now()}`, role: 'user', text: msg, time: nowTime() }])
    setLoading(true)
    try {
      const res = await apiFetch(`/api/screening-sessions/${sessionId}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg }),
      })
      if (!res.ok) throw new Error(await readError(res, 'Chat request failed'))
      const data = await res.json()
      setMessages((prev) => [
        ...prev,
        {
          id: `a${Date.now()}`,
          role: 'assistant',
          text: String(data.answer ?? ''),
          time: nowTime(),
          candidates: data.candidates ?? [],
          allIds: data.all_ids ?? [],
          total: data.total ?? 0,
        },
      ])
      if (Array.isArray(data.suggestions) && data.suggestions.length) setSuggestions(data.suggestions)
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        { id: `e${Date.now()}`, role: 'assistant', text: e instanceof Error ? e.message : 'Something went wrong.', time: nowTime() },
      ])
    } finally {
      setLoading(false)
    }
  }

  const clearChat = async () => {
    setMessages(() => [])
    setSuggestions([])
    try {
      await apiFetch(`/api/screening-sessions/${sessionId}/chat/reset`, { method: 'POST' })
    } catch {
      /* non-fatal */
    }
  }

  const renderAnswer = (m: ChatMessage): ReactNode => {
    const byName = new Map((m.candidates ?? []).map((c) => [c.name, c]))
    return m.text.split('\n').map((line, i) => {
      const match = line.match(/^(\d+)\.\s+(.*?)\s+(\(.*)$/)
      const cand = match ? byName.get(match[2]) : undefined
      if (match && cand) {
        return (
          <div key={i}>
            {match[1]}.{' '}
            <button type="button" className="rs-cand-link" onClick={() => onOpenCandidate(cand.id)}>
              {cand.name}
            </button>{' '}
            {match[3]}
          </div>
        )
      }
      return <div key={i}>{line || '\u00A0'}</div>
    })
  }

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    void send(input)
  }

  return (
    <Shell title="Chat with Results" subtitle="Ask follow-up questions and refine your candidate search." onNavigate={onNavigate}>
      <div className="rs-head" style={{ marginBottom: 8 }}>
        <button type="button" className="rs-back" onClick={onBack}>
          ← Back to Results
        </button>
        <div className="rs-btn-row">
          <button type="button" className="rs-btn rs-btn-sm" onClick={clearChat}>
            Clear Chat
          </button>
          <button type="button" className="rs-btn rs-btn-sm" onClick={() => setExpanded((v) => !v)} aria-label="Toggle chat height" title="Expand / collapse">
            ⤢
          </button>
        </div>
      </div>

      <div className="rs-chat-grid">
        <div>
          <h3 className="rs-sec-title">Suggested Questions</h3>
          <div className="rs-suggest">
            {list.map((s) => (
              <button key={s} type="button" onClick={() => void send(s)} disabled={loading}>
                {s}
              </button>
            ))}
          </div>
        </div>

        <div className="rs-chatbox" style={expanded ? { maxHeight: 'none', minHeight: '70vh' } : undefined}>
          <div className="rs-msgs" aria-live="polite">
            {messages.length === 0 && (
              <div className="rs-empty">
                Ask about the screened candidates, for example “Find candidates with RAG experience”, then narrow down with “Which of these have AWS?”.
              </div>
            )}
            {messages.map((m) =>
              m.role === 'user' ? (
                <div key={m.id} className="rs-msg rs-msg-user">
                  <div className="rs-bubble-user">{m.text}</div>
                  <div className="rs-msg-time">{m.time}</div>
                </div>
              ) : (
                <div key={m.id} className="rs-msg rs-msg-ai">
                  <div className="rs-ai-av">AI</div>
                  <div>
                    <div className="rs-bubble-ai">
                      {renderAnswer(m)}
                      {m.allIds && m.allIds.length > (m.candidates?.length ?? 0) && (
                        <div style={{ marginTop: 8 }}>
                          <button type="button" className="rs-link-btn" onClick={() => onViewAll(m.allIds as string[])}>
                            View all {m.total ?? m.allIds.length} candidates →
                          </button>
                        </div>
                      )}
                    </div>
                    <div className="rs-msg-time">{m.time}</div>
                  </div>
                </div>
              ),
            )}
            {loading && (
              <div className="rs-msg rs-msg-ai">
                <div className="rs-ai-av">AI</div>
                <div className="rs-bubble-ai">
                  <span className="rs-typing" aria-label="Thinking">
                    <i />
                    <i />
                    <i />
                  </span>
                </div>
              </div>
            )}
            <div ref={endRef} />
          </div>

          <form className="rs-inputbar" onSubmit={onSubmit}>
            <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask a follow-up question..." aria-label="Ask a follow-up question" maxLength={2000} />
            <button type="submit" className="rs-send" disabled={loading || !input.trim()} aria-label="Send">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            </button>
          </form>
        </div>
      </div>
    </Shell>
  )
}

import { useState, useRef, useEffect, useCallback, type DragEvent, type ChangeEvent } from 'react'
import { Sidebar, type AppScreen } from './Sidebar'
import { ScreeningWorkspace } from './ScreeningWorkspace'
import type { ApiJobDescription } from './JobDescriptions'
import { apiFetch } from './api'
import './Dashboard.css'
import './NewScreeningWizard.css'
import './Screening.css'

export interface DraftSessionDetail {
  id: string
  job_description_id: string
  job_description_title: string
  status: string
  created_at: string
  updated_at: string
  job_description: ApiJobDescription
  resumes: ApiStagedResume[]
  evaluations?: unknown[]
}

export interface WizardFileItem {
  id: string
  name: string
  size: number
  extension: string
  rawFile?: File
  stagedBackendId?: string
  status: 'pending' | 'staged'
  extractionStatus?: string
  extractionError?: string | null
}

export interface ApiStagedResume {
  id: string
  screening_session_id: string
  original_filename: string
  file_type: string
  file_size: number
  extraction_status: 'pending' | 'extracted' | 'empty' | 'failed' | 'unsupported' | string
  extraction_error: string | null
  indexing_status: 'pending' | 'indexed' | 'skipped' | 'failed' | 'needs_reindex' | string
  chunk_count: number
  indexing_error: string | null
  index_model?: string | null
  created_at: string
  updated_at: string
}

interface NewScreeningWizardProps {
  initialJdId?: string | null
  initialSessionData?: DraftSessionDetail | null
  onNavigate: (screen: AppScreen) => void
  onBack: () => void
}

interface JdDraft {
  title: string
  category: string
  experience: string
  employment_type: string
  skills: string
  description: string
}

const EMPTY_DRAFT: JdDraft = {
  title: '',
  category: 'General',
  experience: 'Not specified',
  employment_type: 'Full-time',
  skills: '',
  description: '',
}

const ALLOWED_EXTENSIONS = ['.pdf', '.doc', '.docx', '.zip']

function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
}

function getFileExtension(filename: string): string {
  const lastDot = filename.lastIndexOf('.')
  return lastDot !== -1 ? filename.slice(lastDot).toLowerCase() : ''
}

function fileIconColor(ext: string): string {
  if (ext === '.pdf') return '#ef4444'
  if (ext === '.zip') return '#f59e0b'
  return '#2563eb'
}

async function errorDetail(res: Response, fallback: string): Promise<string> {
  try {
    const data = await res.json()
    if (typeof data?.detail === 'string') return data.detail
  } catch {
    /* ignore */
  }
  return `${fallback} (HTTP ${res.status})`
}

function toWizardFile(r: ApiStagedResume): WizardFileItem {
  return {
    id: r.id,
    stagedBackendId: r.id,
    name: r.original_filename,
    size: r.file_size,
    extension: getFileExtension(r.original_filename),
    status: 'staged',
    extractionStatus: r.extraction_status,
    extractionError: r.extraction_error,
  }
}

export function NewScreeningWizard({ initialJdId, initialSessionData, onNavigate, onBack }: NewScreeningWizardProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false)

  const isMountedRef = useRef(true)
  useEffect(() => {
    isMountedRef.current = true
    return () => {
      isMountedRef.current = false
    }
  }, [])

  const [currentStep, setCurrentStep] = useState<1 | 2 | 3>(initialSessionData ? 2 : 1)
  const [wizardView, setWizardView] = useState<'wizard-steps' | 'workspace'>('wizard-steps')
  const [workspaceInitial, setWorkspaceInitial] = useState<'processing' | 'results'>('processing')

  const [sessionId, setSessionId] = useState<string | null>(initialSessionData?.id || null)
  const [sessionJdId, setSessionJdId] = useState<string | null>(initialSessionData?.job_description_id || null)
  const [isCreatingSession, setIsCreatingSession] = useState(false)
  const [sessionCreateError, setSessionCreateError] = useState<string | null>(null)

  const [jobDescriptions, setJobDescriptions] = useState<ApiJobDescription[]>(() =>
    initialSessionData?.job_description ? [initialSessionData.job_description] : [],
  )
  const [isLoadingJds, setIsLoadingJds] = useState<boolean>(true)
  const [jdsError, setJdsError] = useState<string | null>(null)
  const [selectedJdId, setSelectedJdId] = useState<string>(initialSessionData?.job_description_id || initialJdId || '')
  const [modeType, setModeType] = useState<'existing' | 'new'>('existing')

  // "Create New JD" draft
  const [draft, setDraft] = useState<JdDraft>(EMPTY_DRAFT)
  const [isParsingJd, setIsParsingJd] = useState(false)
  const [jdParseError, setJdParseError] = useState<string | null>(null)
  const jdFileInputRef = useRef<HTMLInputElement>(null)

  const [uploadedFiles, setUploadedFiles] = useState<WizardFileItem[]>(() =>
    initialSessionData?.resumes?.length ? initialSessionData.resumes.map(toWizardFile) : [],
  )
  const [isDragging, setIsDragging] = useState(false)
  const [fileError, setFileError] = useState<string | null>(null)
  const [isStagingFiles, setIsStagingFiles] = useState(false)
  const [isDeletingFileId, setIsDeletingFileId] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [llmInfo, setLlmInfo] = useState<{ can_chat: boolean; model_name: string | null } | null>(null)

  // Reopening an existing session: jump straight to its results / progress when it already ran.
  useEffect(() => {
    if (!initialSessionData) return
    let cancelled = false
    apiFetch(`/api/screening-sessions/${initialSessionData.id}/progress`)
      .then(async (res) => (res.ok ? await res.json() : null))
      .then((p) => {
        if (cancelled || !p) return
        if (p.status === 'completed' || p.status === 'running') {
          setWorkspaceInitial('results')
          setWizardView('workspace')
        }
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [initialSessionData])

  const fetchJobDescriptions = useCallback(async () => {
    setIsLoadingJds(true)
    setJdsError(null)
    try {
      const res = await apiFetch('/api/job-descriptions')
      if (!res.ok) throw new Error(await errorDetail(res, 'Failed to load job descriptions'))
      const data = (await res.json()) as ApiJobDescription[]
      if (!isMountedRef.current) return
      const selectable = data.filter(
        (d) => !d.is_archived || (initialSessionData?.job_description_id && d.id === initialSessionData.job_description_id),
      )
      if (initialSessionData?.job_description && !selectable.some((d) => d.id === initialSessionData.job_description.id)) {
        selectable.unshift(initialSessionData.job_description)
      }
      setJobDescriptions(selectable)
      const target = initialSessionData?.job_description_id || initialJdId || selectedJdId
      if (target && selectable.some((d) => d.id === target)) setSelectedJdId(target)
      else if (selectable.length > 0) {
        if (!selectedJdId || !selectable.some((d) => d.id === selectedJdId)) setSelectedJdId(selectable[0].id)
      } else setSelectedJdId('')
    } catch (err: unknown) {
      if (isMountedRef.current) setJdsError(err instanceof Error ? err.message : 'Failed to load job descriptions')
    } finally {
      if (isMountedRef.current) setIsLoadingJds(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialJdId, initialSessionData])

  useEffect(() => {
    void fetchJobDescriptions()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (currentStep !== 3) return
    apiFetch('/api/llm/status')
      .then(async (res) => (res.ok ? await res.json() : null))
      .then((d) => {
        if (d && isMountedRef.current) setLlmInfo({ can_chat: !!d.can_chat, model_name: d.model_name ?? null })
      })
      .catch(() => undefined)
  }, [currentStep])

  const selectedJd = jobDescriptions.find((jd) => jd.id === selectedJdId) || initialSessionData?.job_description

  /* ----------------------------- Step 1: JD ----------------------------- */
  const applyParsedDraft = (d: {
    title?: string
    category?: string
    experience?: string
    employment_type?: string
    skills?: string[]
    description?: string
  }) => {
    setDraft((prev) => ({
      title: d.title || prev.title,
      category: d.category || prev.category,
      experience: d.experience || prev.experience,
      employment_type: d.employment_type || prev.employment_type,
      skills: Array.isArray(d.skills) ? d.skills.join(', ') : prev.skills,
      description: d.description || prev.description,
    }))
  }

  const handleJdFile = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setJdParseError(null)
    setIsParsingJd(true)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await apiFetch('/api/job-descriptions/parse-file', { method: 'POST', body: fd })
      if (!res.ok) throw new Error(await errorDetail(res, 'Could not read that file'))
      applyParsedDraft(await res.json())
    } catch (err: unknown) {
      setJdParseError(err instanceof Error ? err.message : 'Could not read that file')
    } finally {
      if (isMountedRef.current) setIsParsingJd(false)
    }
  }

  const handleAutoFill = async () => {
    if (draft.description.trim().length < 20) {
      setJdParseError('Paste at least a few lines of the job description first.')
      return
    }
    setJdParseError(null)
    setIsParsingJd(true)
    try {
      const res = await apiFetch('/api/job-descriptions/parse-text', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: draft.description }),
      })
      if (!res.ok) throw new Error(await errorDetail(res, 'Could not analyze the text'))
      applyParsedDraft(await res.json())
    } catch (err: unknown) {
      setJdParseError(err instanceof Error ? err.message : 'Could not analyze the text')
    } finally {
      if (isMountedRef.current) setIsParsingJd(false)
    }
  }

  const createSessionFor = async (jdId: string) => {
    if (sessionId && sessionJdId === jdId) {
      setCurrentStep(2)
      return
    }
    const res = await apiFetch('/api/screening-sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ job_description_id: jdId }),
    })
    if (!res.ok) throw new Error(await errorDetail(res, 'Failed to create draft session'))
    const created = await res.json()
    if (!isMountedRef.current) return
    setSessionId(created.id)
    setSessionJdId(jdId)
    setCurrentStep(2)
  }

  const handleProceedToStep2 = async () => {
    if (isCreatingSession) return
    setSessionCreateError(null)
    setIsCreatingSession(true)
    try {
      let jdId = selectedJdId
      if (modeType === 'new') {
        if (!draft.title.trim() || !draft.description.trim()) {
          throw new Error('Enter a title and the job description text (or upload a PDF).')
        }
        const res = await apiFetch('/api/job-descriptions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: draft.title.trim(),
            category: draft.category.trim() || 'General',
            description: draft.description.trim(),
            skills: draft.skills
              .split(',')
              .map((s) => s.trim())
              .filter(Boolean),
            experience: draft.experience.trim() || 'Not specified',
            employment_type: draft.employment_type.trim() || 'Full-time',
          }),
        })
        if (!res.ok) throw new Error(await errorDetail(res, 'Could not save the job description'))
        const jd = (await res.json()) as ApiJobDescription
        if (isMountedRef.current) {
          setJobDescriptions((prev) => [jd, ...prev])
          setSelectedJdId(jd.id)
          setModeType('existing')
          setDraft(EMPTY_DRAFT)
        }
        jdId = jd.id
      }
      if (!jdId) throw new Error('Select a job description first.')
      await createSessionFor(jdId)
    } catch (err: unknown) {
      if (isMountedRef.current) setSessionCreateError(err instanceof Error ? err.message : 'Could not create draft screening session')
    } finally {
      if (isMountedRef.current) setIsCreatingSession(false)
    }
  }

  /* ----------------------------- Step 2: files ----------------------------- */
  const handleAddFiles = (files: FileList | File[]) => {
    setFileError(null)
    const newItems: WizardFileItem[] = []
    const rejected: string[] = []
    Array.from(files).forEach((file) => {
      const ext = getFileExtension(file.name)
      if (ALLOWED_EXTENSIONS.includes(ext)) {
        newItems.push({
          id: `${file.name}-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`,
          name: file.name,
          size: file.size,
          extension: ext,
          rawFile: file,
          status: 'pending',
        })
      } else rejected.push(file.name)
    })
    if (rejected.length > 0) {
      setFileError(`Unsupported format for: ${rejected.join(', ')}. Please upload PDF, DOC, DOCX, or ZIP files.`)
    }
    if (newItems.length > 0) setUploadedFiles((prev) => [...prev, ...newItems])
  }

  const handleFileInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      handleAddFiles(e.target.files)
      e.target.value = ''
    }
  }

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(true)
  }
  const handleDragLeave = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(false)
  }
  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDragging(false)
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) handleAddFiles(e.dataTransfer.files)
  }

  const handleRemoveFile = async (fileItem: WizardFileItem) => {
    if (fileItem.status === 'staged' && sessionId) {
      const backendId = fileItem.stagedBackendId || fileItem.id
      setIsDeletingFileId(fileItem.id)
      setFileError(null)
      try {
        const res = await apiFetch(`/api/screening-sessions/${sessionId}/resumes/${backendId}`, { method: 'DELETE' })
        if (!res.ok) throw new Error(await errorDetail(res, 'Failed to delete file'))
        if (isMountedRef.current) setUploadedFiles((prev) => prev.filter((f) => f.id !== fileItem.id))
      } catch (err: unknown) {
        if (isMountedRef.current) setFileError(err instanceof Error ? err.message : 'Failed to delete file from session')
      } finally {
        if (isMountedRef.current) setIsDeletingFileId(null)
      }
    } else {
      setUploadedFiles((prev) => prev.filter((f) => f.id !== fileItem.id))
    }
  }

  // Stage any local files on the server, then go to the Review & Start step.
  const handleProceedToReview = async () => {
    if (!sessionId) {
      setFileError('Draft screening session is missing. Please go back to Step 1.')
      return
    }
    if (isStagingFiles) return
    const pending = uploadedFiles.filter((f) => f.status === 'pending' && f.rawFile)
    if (pending.length === 0) {
      if (uploadedFiles.length > 0) setCurrentStep(3)
      return
    }
    setIsStagingFiles(true)
    setFileError(null)
    try {
      const formData = new FormData()
      pending.forEach((f) => f.rawFile && formData.append('files', f.rawFile))
      const res = await apiFetch(`/api/screening-sessions/${sessionId}/resumes`, { method: 'POST', body: formData })
      if (!res.ok) throw new Error(await errorDetail(res, 'Failed to stage resumes'))
      const staged = (await res.json()) as ApiStagedResume[]
      if (!isMountedRef.current) return
      setUploadedFiles((prev) => [...prev.filter((f) => f.status === 'staged'), ...staged.map(toWizardFile)])
      setCurrentStep(3)
    } catch (err: unknown) {
      if (isMountedRef.current) setFileError(err instanceof Error ? err.message : 'Failed to upload and stage resumes')
    } finally {
      if (isMountedRef.current) setIsStagingFiles(false)
    }
  }

  const startScreening = () => {
    if (!sessionId) return
    setWorkspaceInitial('processing')
    setWizardView('workspace')
  }

  /* ----------------------------- Workspace ----------------------------- */
  if (wizardView === 'workspace' && sessionId) {
    return (
      <ScreeningWorkspace
        sessionId={sessionId}
        initialView={workspaceInitial}
        jobTitle={selectedJd?.title}
        onNavigate={onNavigate}
        onExit={onBack}
        onAddResumes={() => {
          setWizardView('wizard-steps')
          setCurrentStep(2)
        }}
      />
    )
  }

  const step1Ready =
    modeType === 'new'
      ? draft.title.trim().length > 0 && draft.description.trim().length > 0
      : !isLoadingJds && !jdsError && !!selectedJdId && jobDescriptions.some((jd) => jd.id === selectedJdId)

  return (
    <div className="dashboard-layout">
      <Sidebar activeScreen="new-screening" onNavigate={onNavigate} sidebarOpen={sidebarOpen} onCloseSidebar={() => setSidebarOpen(false)} />

      <main className="dashboard-main">
        <header className="dashboard-topbar">
          <div className="topbar-left">
            <button type="button" className="mobile-nav-toggle" onClick={() => setSidebarOpen(true)} aria-label="Open sidebar navigation">
              ☰
            </button>
            <div className="header-titles">
              <h1 className="welcome-heading">New Screening Session</h1>
              <p className="welcome-subtext">Choose a job description, upload resumes, and let the AI rank the candidates.</p>
            </div>
          </div>
        </header>

        <div className="wizard-page-content" style={{ maxWidth: '980px' }}>
          <nav className="wizard-stepper" aria-label="Screening progress">
            <div
              className={`step-item ${currentStep === 1 ? 'step-item-active' : 'step-item-completed'}`}
              onClick={() => setCurrentStep(1)}
              role="button"
            >
              <div className="step-circle" aria-hidden="true">
                {currentStep > 1 ? '✓' : '1'}
              </div>
              <div className="step-label-group">
                <span className="step-title">Job Description</span>
              </div>
            </div>

            <div className={`step-connector ${currentStep >= 2 ? 'step-connector-completed' : ''}`} />

            <div
              className={`step-item ${currentStep === 2 ? 'step-item-active' : currentStep > 2 ? 'step-item-completed' : 'step-item-inactive'}`}
              onClick={() => {
                if (sessionId) setCurrentStep(2)
              }}
              role="button"
            >
              <div className="step-circle" aria-hidden="true">
                {currentStep > 2 ? '✓' : '2'}
              </div>
              <div className="step-label-group">
                <span className="step-title">Upload Resumes</span>
              </div>
            </div>

            <div className={`step-connector ${currentStep >= 3 ? 'step-connector-completed' : ''}`} />

            <div className={`step-item ${currentStep === 3 ? 'step-item-active' : 'step-item-inactive'}`}>
              <div className="step-circle" aria-hidden="true">
                3
              </div>
              <div className="step-label-group">
                <span className="step-title">Review &amp; Start</span>
              </div>
            </div>
          </nav>

          {/* ===================== STEP 1 ===================== */}
          {currentStep === 1 && (
            <section className="wizard-card" aria-labelledby="step1-heading">
              <div className="wizard-card-header">
                <h2 id="step1-heading" className="wizard-panel-title">
                  Select Job Description
                </h2>
                <p className="wizard-panel-subtitle">Choose an existing job description or create a new one.</p>
              </div>

              {isLoadingJds && (
                <div style={{ padding: '2.5rem 1rem', textAlign: 'center' }}>
                  <div className="btn-inline-spinner" style={{ width: '28px', height: '28px', margin: '0 auto 12px' }} aria-hidden="true" />
                  <p style={{ color: '#64748b', fontSize: '0.95rem' }}>Loading saved job descriptions...</p>
                </div>
              )}

              {jdsError && !isLoadingJds && (
                <div className="wizard-batch-error-banner" role="alert" style={{ margin: '1rem 0' }}>
                  <strong>Failed to load job descriptions</strong>
                  <p>{jdsError}</p>
                  <button type="button" className="btn btn-secondary btn-sm" onClick={fetchJobDescriptions} style={{ marginTop: '0.5rem' }}>
                    ↻ Retry
                  </button>
                </div>
              )}

              {!isLoadingJds && !jdsError && (
                <div className="step1-radio-selection-block">
                  <label className="radio-selection-label">
                    <input
                      type="radio"
                      name="jd-mode"
                      checked={modeType === 'existing'}
                      onChange={() => setModeType('existing')}
                      className="radio-input-custom"
                      disabled={jobDescriptions.length === 0}
                    />
                    <span className="radio-text-bold">Use Existing JD</span>
                  </label>

                  {modeType === 'existing' && jobDescriptions.length > 0 && (
                    <div className="existing-jd-content-box">
                      <select
                        id="jd-select-dropdown"
                        className="jd-select-dropdown"
                        value={selectedJdId}
                        onChange={(e) => {
                          const newId = e.target.value
                          setSelectedJdId(newId)
                          if (sessionJdId && sessionJdId !== newId) {
                            setSessionId(null)
                            setSessionJdId(null)
                            setUploadedFiles([])
                          }
                        }}
                      >
                        {jobDescriptions.map((jd) => (
                          <option key={jd.id} value={jd.id}>
                            {jd.title}
                          </option>
                        ))}
                      </select>

                      {selectedJd && (
                        <div className="jd-preview-card-screen4">
                          <h4 className="jd-card-role-title">{selectedJd.title}</h4>
                          <p className="jd-card-role-desc">{selectedJd.description}</p>
                          <button type="button" className="btn-view-details-link" onClick={() => onNavigate('jobs')}>
                            View Details
                          </button>
                        </div>
                      )}
                    </div>
                  )}

                  {modeType === 'existing' && jobDescriptions.length === 0 && (
                    <p style={{ color: '#64748b', fontSize: 13.5, margin: '8px 0 0 28px' }}>No saved job descriptions yet. Create one below.</p>
                  )}

                  <label className="radio-selection-label" style={{ marginTop: 18 }}>
                    <input type="radio" name="jd-mode" checked={modeType === 'new'} onChange={() => setModeType('new')} className="radio-input-custom" />
                    <span className="radio-text-bold">Create New JD</span>
                  </label>
                  <p style={{ color: '#64748b', fontSize: 13, margin: '2px 0 0 28px' }}>Enter or paste a new job description, or upload a PDF.</p>

                  {modeType === 'new' && (
                    <div className="rs-new-jd" style={{ marginLeft: 28 }}>
                      <textarea
                        className="rs-textarea"
                        placeholder="Paste the job description here…"
                        value={draft.description}
                        onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                        aria-label="Job description text"
                      />
                      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                        <input ref={jdFileInputRef} type="file" accept=".pdf,.docx,.doc,.txt" style={{ display: 'none' }} onChange={handleJdFile} />
                        <button type="button" className="btn btn-secondary btn-sm" onClick={() => jdFileInputRef.current?.click()} disabled={isParsingJd}>
                          ⬆ Upload JD (PDF / DOCX)
                        </button>
                        <button type="button" className="btn btn-secondary btn-sm" onClick={handleAutoFill} disabled={isParsingJd}>
                          {isParsingJd ? 'Analyzing…' : '✨ Auto-fill title & skills'}
                        </button>
                      </div>
                      {jdParseError && (
                        <div className="wizard-batch-error-banner" role="alert">
                          <p style={{ margin: 0 }}>{jdParseError}</p>
                        </div>
                      )}
                      <div className="rs-jd-draft">
                        <div className="rs-field">
                          <label htmlFor="jd-title">Job title *</label>
                          <input id="jd-title" className="rs-input" value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} maxLength={255} />
                        </div>
                        <div className="rs-field">
                          <label htmlFor="jd-cat">Category</label>
                          <input id="jd-cat" className="rs-input" value={draft.category} onChange={(e) => setDraft({ ...draft, category: e.target.value })} maxLength={100} />
                        </div>
                        <div className="rs-field">
                          <label htmlFor="jd-skills">Key skills (comma separated)</label>
                          <input id="jd-skills" className="rs-input" value={draft.skills} onChange={(e) => setDraft({ ...draft, skills: e.target.value })} placeholder="Python, RAG, LangChain, AWS" />
                        </div>
                        <div className="rs-field">
                          <label htmlFor="jd-exp">Experience</label>
                          <input id="jd-exp" className="rs-input" value={draft.experience} onChange={(e) => setDraft({ ...draft, experience: e.target.value })} maxLength={100} />
                        </div>
                      </div>
                    </div>
                  )}

                  {sessionCreateError && (
                    <div className="wizard-batch-error-banner" role="alert" style={{ marginTop: '1rem' }}>
                      <strong>Could not continue</strong>
                      <p>{sessionCreateError}</p>
                    </div>
                  )}
                </div>
              )}

              <div className="wizard-card-footer">
                <button type="button" className="btn btn-secondary" onClick={onBack}>
                  Cancel
                </button>
                <button type="button" className="btn btn-primary" onClick={handleProceedToStep2} disabled={!step1Ready || isCreatingSession}>
                  {isCreatingSession ? 'Preparing session...' : 'Next: Upload Resumes →'}
                </button>
              </div>
            </section>
          )}

          {/* ===================== STEP 2 ===================== */}
          {currentStep === 2 && (
            <section className="wizard-card" aria-labelledby="step2-heading">
              <div className="wizard-card-header">
                <h2 id="step2-heading" className="wizard-panel-title">
                  Upload Resumes
                </h2>
                <p className="wizard-panel-subtitle">
                  Upload candidate resumes to evaluate against <strong>{selectedJd?.title}</strong>.
                </p>
              </div>

              <div
                className={`upload-dropzone-screen5 ${isDragging ? 'dropzone-active' : ''}`}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') fileInputRef.current?.click()
                }}
              >
                <input ref={fileInputRef} type="file" multiple accept=".pdf,.doc,.docx,.zip" style={{ display: 'none' }} onChange={handleFileInputChange} />
                <div className="upload-cloud-icon" aria-hidden="true">
                  <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="#2563eb" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M4 14.899A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.242" />
                    <path d="M12 12v9" />
                    <path d="m16 16-4-4-4 4" />
                  </svg>
                </div>
                <h3 className="upload-zone-title">Upload Resumes</h3>
                <p className="upload-zone-sub">
                  Drag and drop files here, or <span className="upload-zone-link">click to browse</span>
                </p>
                <span className="upload-zone-hint">Supports PDF, DOC, DOCX, ZIP (multiple files)</span>
              </div>

              {fileError && (
                <div className="wizard-batch-error-banner" role="alert" style={{ marginTop: '1rem' }}>
                  <strong>Upload / File Notice</strong>
                  <p>{fileError}</p>
                </div>
              )}

              {uploadedFiles.length > 0 && (
                <div className="staged-files-list-screen5">
                  {uploadedFiles.map((f) => (
                    <div key={f.id} className="staged-file-row-screen5">
                      <div className="file-icon-and-name">
                        <span className="file-type-icon" aria-hidden="true" style={{ color: fileIconColor(f.extension) }}>
                          ▤
                        </span>
                        <span className="file-name-text">{f.name}</span>
                        {f.extractionStatus === 'failed' && (
                          <span className="badge" title={f.extractionError || 'Extraction failed'} style={{ fontSize: '11px', marginLeft: '6px', backgroundColor: '#fee2e2', color: '#991b1b' }}>
                            Unreadable
                          </span>
                        )}
                      </div>
                      <div className="file-size-and-status">
                        <span className="file-size-label">{formatFileSize(f.size)}</span>
                        {f.status === 'staged' ? (
                          <span className="green-checkmark-icon" title="Uploaded">
                            ✓
                          </span>
                        ) : (
                          <span title="Ready to upload" style={{ color: '#2563eb', fontWeight: 600 }}>
                            ●
                          </span>
                        )}
                        <button
                          type="button"
                          className="btn-remove-file-sm"
                          onClick={(e) => {
                            e.stopPropagation()
                            void handleRemoveFile(f)
                          }}
                          disabled={isDeletingFileId === f.id}
                          aria-label={`Remove ${f.name}`}
                          title="Remove file"
                        >
                          {isDeletingFileId === f.id ? '...' : '✕'}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              <div className="wizard-card-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setCurrentStep(1)} disabled={isStagingFiles}>
                  ← Back
                </button>
                <button type="button" className="btn btn-primary" onClick={handleProceedToReview} disabled={uploadedFiles.length === 0 || isStagingFiles}>
                  {isStagingFiles ? 'Uploading...' : 'Next: Review & Start →'}
                </button>
              </div>
            </section>
          )}

          {/* ===================== STEP 3 ===================== */}
          {currentStep === 3 && (
            <section className="wizard-card" aria-labelledby="step3-heading">
              <div className="wizard-card-header">
                <h2 id="step3-heading" className="wizard-panel-title">
                  Review &amp; Start
                </h2>
                <p className="wizard-panel-subtitle">Confirm the details, then start the screening.</p>
              </div>

              <div>
                <div className="rs-review-row">
                  <span>Job description</span>
                  <span>{selectedJd?.title ?? '—'}</span>
                </div>
                <div className="rs-review-row">
                  <span>Key skills</span>
                  <span>{selectedJd?.skills?.length ? selectedJd.skills.slice(0, 6).join(', ') : 'Derived from the description'}</span>
                </div>
                <div className="rs-review-row">
                  <span>Experience</span>
                  <span>{selectedJd?.experience || 'Not specified'}</span>
                </div>
                <div className="rs-review-row">
                  <span>Files uploaded</span>
                  <span>
                    {uploadedFiles.length}
                    {uploadedFiles.some((f) => f.extension === '.zip') ? ' (ZIP archives are split into individual resumes)' : ''}
                  </span>
                </div>
                <div className="rs-review-row">
                  <span>AI model</span>
                  <span>
                    {llmInfo === null ? 'Checking…' : llmInfo.can_chat ? `${llmInfo.model_name ?? 'Ready'} (ready)` : 'Unavailable: keyword scoring will be used'}
                  </span>
                </div>
              </div>

              {llmInfo && !llmInfo.can_chat && (
                <div className="rs-banner rs-banner-warn" style={{ marginTop: 14 }}>
                  The AI model is not available. Screening will still run using keyword and semantic matching. Check Settings to enable the AI model for deeper analysis.
                </div>
              )}

              <div className="wizard-card-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setCurrentStep(2)}>
                  ← Back
                </button>
                <button type="button" className="btn btn-primary" onClick={startScreening} disabled={uploadedFiles.length === 0 || !sessionId}>
                  Start Screening
                </button>
              </div>
            </section>
          )}
        </div>
      </main>
    </div>
  )
}

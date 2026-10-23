import { useState, useMemo, useEffect, type ChangeEvent, type FormEvent } from 'react'
import { Sidebar, type AppScreen } from './Sidebar'
import './Dashboard.css'
import './JobDescriptions.css'

interface JobDescriptionsProps {
  onNavigate: (screen: AppScreen) => void
  onUseJd: (jdId: string) => void
}

export interface ApiJobDescription {
  id: string
  title: string
  category: string
  description: string
  skills: string[]
  tags?: string[]
  experience: string
  employment_type: string
  is_archived?: boolean
  archived_at?: string | null
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
    return `Created ${d.toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    })}`
  } catch {
    return 'Recently created'
  }
}

export function JobDescriptions({ onNavigate, onUseJd }: JobDescriptionsProps) {
  const { isPrivileged, isAdmin } = useAuth()
  const [successNotice, setSuccessNotice] = useState<string | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCategory, setSelectedCategory] = useState('All Categories')
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'archived'>('all')
  const [activeMenuId, setActiveMenuId] = useState<string | null>(null)

  // API State
  const [jobDescriptions, setJobDescriptions] = useState<ApiJobDescription[]>([])
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [apiError, setApiError] = useState<string | null>(null)

  // Create JD Form State
  const [isCreateOpen, setIsCreateOpen] = useState<boolean>(false)
  const [formTitle, setFormTitle] = useState('')
  const [formCategory, setFormCategory] = useState('Engineering')
  const [formDescription, setFormDescription] = useState('')
  const [formSkills, setFormSkills] = useState('')
  const [formExperience, setFormExperience] = useState('3+ years')
  const [formEmploymentType, setFormEmploymentType] = useState('Full-time')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  // Edit JD Form State
  const [editingJd, setEditingJd] = useState<ApiJobDescription | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const [editCategory, setEditCategory] = useState('Engineering')
  const [editDescription, setEditDescription] = useState('')
  const [editSkills, setEditSkills] = useState('')
  const [editExperience, setEditExperience] = useState('3+ years')
  const [editEmploymentType, setEditEmploymentType] = useState('Full-time')
  const [isEditSubmitting, setIsEditSubmitting] = useState(false)
  const [editError, setEditError] = useState<string | null>(null)

  // Archive / Restore Confirmation State
  const [archiveConfirmJd, setArchiveConfirmJd] = useState<ApiJobDescription | null>(null)
  const [isArchiveSubmitting, setIsArchiveSubmitting] = useState(false)
  const [archiveError, setArchiveError] = useState<string | null>(null)

  // Permanent delete (admin only). deleteSessionCount is set once the server reports linked sessions.
  const [deleteConfirmJd, setDeleteConfirmJd] = useState<ApiJobDescription | null>(null)
  const [deleteSessionCount, setDeleteSessionCount] = useState<number | null>(null)
  const [isDeleteSubmitting, setIsDeleteSubmitting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  // Uploading a PDF/DOCX job description into the description field
  const [isReadingFile, setIsReadingFile] = useState(false)


  // Fetch Job Descriptions from API
  const fetchJobDescriptions = async () => {
    setIsLoading(true)
    setApiError(null)
    try {
      const res = await apiFetch('/api/job-descriptions', {
        method: 'GET',
        headers: {
          Accept: 'application/json',
        },
      })

      if (!res.ok) {
        throw new Error(
          `API returned status ${res.status}: ${res.statusText || 'Failed to fetch job descriptions'}`
        )
      }

      const data = (await res.json()) as ApiJobDescription[]
      setJobDescriptions(data)
    } catch (err: unknown) {
      const message =
        err instanceof Error
          ? err.message
          : 'Unable to connect to FastAPI backend server.'
      setApiError(
        `Failed to load job descriptions from ${API_BASE_URL}/api/job-descriptions. ${message}`
      )
      setJobDescriptions([]) // Strictly do not substitute fictional records
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchJobDescriptions()
  }, [])

  // Derive unique categories from loaded records
  const categories = useMemo(() => {
    const cats = new Set<string>()
    jobDescriptions.forEach((jd) => {
      if (jd.category) cats.add(jd.category)
    })
    return ['All Categories', ...Array.from(cats).sort()]
  }, [jobDescriptions])

  // Local search and category filter (preserves state on update/archive)
  const filteredJDs = useMemo(() => {
    return jobDescriptions.filter((jd) => {
      const matchesCategory =
        selectedCategory === 'All Categories' || jd.category === selectedCategory

      const matchesStatus =
        statusFilter === 'all' ||
        (statusFilter === 'active' && !jd.is_archived) ||
        (statusFilter === 'archived' && !!jd.is_archived)

      const query = searchQuery.trim().toLowerCase()
      if (!query) return matchesCategory && matchesStatus

      const skillsList = jd.skills || jd.tags || []
      const matchesSearch =
        jd.title.toLowerCase().includes(query) ||
        jd.description.toLowerCase().includes(query) ||
        jd.category.toLowerCase().includes(query) ||
        skillsList.some((s) => s.toLowerCase().includes(query))

      return matchesCategory && matchesStatus && matchesSearch
    })
  }, [jobDescriptions, searchQuery, selectedCategory, statusFilter])

  // Submit new Job Description
  const handleCreateSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setFormError(null)

    const trimmedTitle = formTitle.trim()
    const trimmedDesc = formDescription.trim()

    if (!trimmedTitle) {
      setFormError('Job title is required.')
      return
    }

    if (!trimmedDesc) {
      setFormError('Job description is required.')
      return
    }

    // Parse comma-separated skills
    const parsedSkills = formSkills
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)

    const payload = {
      title: trimmedTitle,
      category: formCategory.trim() || 'General',
      description: trimmedDesc,
      skills: parsedSkills,
      experience: formExperience.trim() || 'Not specified',
      employment_type: formEmploymentType.trim() || 'Full-time',
    }

    setIsSubmitting(true)

    try {
      const res = await apiFetch('/api/job-descriptions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
        },
        body: JSON.stringify(payload),
      })

      if (!res.ok) {
        const errorText = await res.text()
        throw new Error(
          `Failed to save (${res.status}): ${errorText || res.statusText}`
        )
      }

      const createdJd = (await res.json()) as ApiJobDescription

      // Prepend newly created JD to list
      setJobDescriptions((prev) => [createdJd, ...prev])
      setSuccessNotice(`Job description "${createdJd.title}" successfully created and saved.`)

      // Reset form & close
      setFormTitle('')
      setFormCategory('Engineering')
      setFormDescription('')
      setFormSkills('')
      setFormExperience('3+ years')
      setFormEmploymentType('Full-time')
      setIsCreateOpen(false)
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : 'Error submitting to API.'
      setFormError(message)
    } finally {
      setIsSubmitting(false)
    }
  }

  // Duplicate prefill handler
  const handleStartDuplicate = (jd: ApiJobDescription) => {
    setFormTitle(`${jd.title} (Copy)`)
    setFormCategory(jd.category || 'General')
    setFormDescription(jd.description || '')
    setFormSkills((jd.skills || jd.tags || []).join(', '))
    setFormExperience(jd.experience || '3+ years')
    setFormEmploymentType(jd.employment_type || 'Full-time')
    setFormError(null)
    setIsCreateOpen(true)
  }

  // Edit open handler
  const handleStartEdit = (jd: ApiJobDescription) => {
    setEditingJd(jd)
    setEditTitle(jd.title)
    setEditCategory(jd.category || 'General')
    setEditDescription(jd.description || '')
    setEditSkills((jd.skills || jd.tags || []).join(', '))
    setEditExperience(jd.experience || 'Not specified')
    setEditEmploymentType(jd.employment_type || 'Full-time')
    setEditError(null)
  }

  // Edit submit handler
  const handleEditSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!editingJd) return
    setEditError(null)

    const trimmedTitle = editTitle.trim()
    const trimmedDesc = editDescription.trim()

    if (!trimmedTitle) {
      setEditError('Job title is required.')
      return
    }

    if (!trimmedDesc) {
      setEditError('Job description is required.')
      return
    }

    const parsedSkills = editSkills
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)

    const payload = {
      title: trimmedTitle,
      category: editCategory.trim() || 'General',
      description: trimmedDesc,
      skills: parsedSkills,
      experience: editExperience.trim() || 'Not specified',
      employment_type: editEmploymentType.trim() || 'Full-time',
    }

    setIsEditSubmitting(true)

    try {
      const res = await apiFetch(`/api/job-descriptions/${editingJd.id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
        },
        body: JSON.stringify(payload),
      })

      if (!res.ok) {
        const errorText = await res.text()
        throw new Error(
          `Failed to update (${res.status}): ${errorText || res.statusText}`
        )
      }

      const updatedJd = (await res.json()) as ApiJobDescription

      // Update row in-place without resetting user's search or filter state
      setJobDescriptions((prev) =>
        prev.map((item) => (item.id === updatedJd.id ? updatedJd : item))
      )
      setSuccessNotice(`Job description "${updatedJd.title}" successfully updated.`)
      setEditingJd(null)
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : 'Error updating job description.'
      setEditError(message)
    } finally {
      setIsEditSubmitting(false)
    }
  }

  const closeDeleteConfirm = () => {
    setDeleteConfirmJd(null)
    setDeleteSessionCount(null)
    setDeleteError(null)
  }

  const handleConfirmDelete = async () => {
    if (!deleteConfirmJd) return
    setIsDeleteSubmitting(true)
    setDeleteError(null)
    try {
      const query = deleteSessionCount !== null ? '?delete_sessions=true' : ''
      const res = await apiFetch(`/api/job-descriptions/${deleteConfirmJd.id}${query}`, {
        method: 'DELETE',
        headers: { Accept: 'application/json' },
      })
      if (res.status === 409) {
        const body = await res.json().catch(() => null)
        if (typeof body?.detail?.session_count === 'number') {
          setDeleteSessionCount(body.detail.session_count) // ask again, now with explicit wording
          return
        }
        throw new Error(typeof body?.detail === 'string' ? body.detail : 'This job description cannot be deleted right now.')
      }
      if (!res.ok) {
        const body = await res.json().catch(() => null)
        throw new Error(typeof body?.detail === 'string' ? body.detail : `Failed to delete (${res.status})`)
      }
      setJobDescriptions((prev) => prev.filter((item) => item.id !== deleteConfirmJd.id))
      setSuccessNotice(`Job description "${deleteConfirmJd.title}" was permanently deleted.`)
      closeDeleteConfirm()
    } catch (err: unknown) {
      setDeleteError(err instanceof Error ? err.message : 'Error deleting job description.')
    } finally {
      setIsDeleteSubmitting(false)
    }
  }

  // Read a PDF/DOCX job description on the server and paste its whole text into the description field.
  const handleJdFileUpload = async (e: ChangeEvent<HTMLInputElement>, target: 'create' | 'edit') => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    const setErr = target === 'create' ? setFormError : setEditError
    setErr(null)
    setIsReadingFile(true)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await apiFetch('/api/job-descriptions/parse-file', { method: 'POST', body: fd })
      if (!res.ok) {
        const body = await res.json().catch(() => null)
        throw new Error(typeof body?.detail === 'string' ? body.detail : `Could not read the file (${res.status})`)
      }
      const parsed = await res.json()
      if (target === 'create') {
        setFormDescription(parsed.description)
        if (!formTitle.trim()) setFormTitle(parsed.title)
        if (!formSkills.trim()) setFormSkills((parsed.skills ?? []).join(', '))
      } else {
        setEditDescription(parsed.description)
      }
    } catch (err: unknown) {
      setErr(err instanceof Error ? err.message : 'Could not read the file.')
    } finally {
      setIsReadingFile(false)
    }
  }

  // Archive / Restore initiate handler
  const handleStartArchiveConfirm = (jd: ApiJobDescription) => {
    setArchiveConfirmJd(jd)
    setArchiveError(null)
  }

  // Archive / Restore execution handler
  const handleConfirmArchiveOrRestore = async () => {
    if (!archiveConfirmJd) return
    setIsArchiveSubmitting(true)
    setArchiveError(null)

    const action = archiveConfirmJd.is_archived ? 'restore' : 'archive'

    try {
      const res = await apiFetch(`/api/job-descriptions/${archiveConfirmJd.id}/${action}`, {
        method: 'POST',
        headers: {
          Accept: 'application/json',
        },
      })

      if (!res.ok) {
        const errorText = await res.text()
        throw new Error(
          `Failed to ${action} (${res.status}): ${errorText || res.statusText}`
        )
      }

      const updatedJd = (await res.json()) as ApiJobDescription

      // Update row in-place without losing filters
      setJobDescriptions((prev) =>
        prev.map((item) => (item.id === updatedJd.id ? updatedJd : item))
      )
      setSuccessNotice(
        `Job description "${updatedJd.title}" successfully ${updatedJd.is_archived ? 'archived' : 'restored'}.`
      )
      setArchiveConfirmJd(null)
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : `Error during ${action}.`
      setArchiveError(message)
    } finally {
      setIsArchiveSubmitting(false)
    }
  }

  return (
    <div className="dashboard-layout">
      {/* Shared Dark Left Sidebar */}
      <Sidebar
        activeScreen="jobs"
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
              <h1 className="welcome-heading">Job Descriptions</h1>
              <p className="welcome-subtext">
                Manage evaluation criteria, role rubrics, and benchmark requirements for resume screening.
              </p>
            </div>
          </div>

          {isPrivileged && (
            <div className="topbar-actions">
              <button
                type="button"
                className="btn btn-primary new-session-btn"
                onClick={() => {
                  setFormError(null)
                  setIsCreateOpen(true)
                }}
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
                <span>Create JD</span>
              </button>
            </div>
          )}
        </header>


        {/* Success Alert Toast */}
        {successNotice && (
          <div className="dashboard-notice notice-success" role="status" aria-live="polite">
            <span className="notice-icon" aria-hidden="true">✓</span>
            <span className="notice-text">{successNotice}</span>
            <button
              type="button"
              className="notice-dismiss"
              onClick={() => setSuccessNotice(null)}
              aria-label="Dismiss notice"
            >
              ✕
            </button>
          </div>
        )}

        {/* Create JD Modal / Form Overlay */}
        {isPrivileged && isCreateOpen && (
          <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="create-jd-modal-title">
            <div className="create-jd-modal-card">
              <div className="modal-header">
                <div>
                  <h2 id="create-jd-modal-title" className="modal-title">
                    Create New Job Description
                  </h2>
                  <p className="modal-subtitle">
                    Add role specifications and required skills to the persistent database.
                  </p>
                </div>
                <button
                  type="button"
                  className="modal-close-btn"
                  onClick={() => setIsCreateOpen(false)}
                  aria-label="Close form"
                >
                  ✕
                </button>
              </div>

              {formError && (
                <div className="form-error-banner" role="alert">
                  <span aria-hidden="true">⚠️</span>
                  <span>{formError}</span>
                </div>
              )}

              <form className="create-jd-form" onSubmit={handleCreateSubmit}>
                <div className="form-group">
                  <label htmlFor="jd-form-title" className="form-label">
                    Job Title <span className="text-req">*</span>
                  </label>
                  <input
                    id="jd-form-title"
                    type="text"
                    className="form-input"
                    placeholder="e.g. Senior Machine Learning Engineer"
                    value={formTitle}
                    onChange={(e) => setFormTitle(e.target.value)}
                    required
                  />
                </div>

                <div className="form-row">
                  <div className="form-group form-col">
                    <label htmlFor="jd-form-category" className="form-label">
                      Category
                    </label>
                    <select
                      id="jd-form-category"
                      className="form-select"
                      value={formCategory}
                      onChange={(e) => setFormCategory(e.target.value)}
                    >
                      <option value="Engineering">Engineering</option>
                      <option value="AI & Data">AI & Data</option>
                      <option value="Design & UX">Design & UX</option>
                      <option value="Product Management">Product Management</option>
                      <option value="Operations">Operations</option>
                      <option value="General">General</option>
                    </select>
                  </div>

                  <div className="form-group form-col">
                    <label htmlFor="jd-form-experience" className="form-label">
                      Required Experience
                    </label>
                    <input
                      id="jd-form-experience"
                      type="text"
                      className="form-input"
                      placeholder="e.g. 3+ years"
                      value={formExperience}
                      onChange={(e) => setFormExperience(e.target.value)}
                    />
                  </div>
                </div>

                <div className="form-row">
                  <div className="form-group form-col">
                    <label htmlFor="jd-form-employment" className="form-label">
                      Employment Type
                    </label>
                    <select
                      id="jd-form-employment"
                      className="form-select"
                      value={formEmploymentType}
                      onChange={(e) => setFormEmploymentType(e.target.value)}
                    >
                      <option value="Full-time">Full-time</option>
                      <option value="Part-time">Part-time</option>
                      <option value="Contract">Contract</option>
                      <option value="Remote">Remote</option>
                    </select>
                  </div>

                  <div className="form-group form-col">
                    <label htmlFor="jd-form-skills" className="form-label">
                      Skills &amp; Tags (comma-separated)
                    </label>
                    <input
                      id="jd-form-skills"
                      type="text"
                      className="form-input"
                      placeholder="e.g. Python, PyTorch, Docker, FastAPI"
                      value={formSkills}
                      onChange={(e) => setFormSkills(e.target.value)}
                    />
                  </div>
                </div>

                <div className="form-group">
                  <label htmlFor="jd-form-desc" className="form-label">
                    Role Description &amp; Responsibilities <span className="text-req">*</span>
                  </label>
                  <div className="jd-upload-row">
                    <label className="btn btn-secondary btn-sm">
                      {isReadingFile ? 'Reading file…' : '⬆ Upload PDF / DOCX'}
                      <input type="file" accept=".pdf,.docx,.doc,.txt" hidden disabled={isReadingFile} onChange={(e) => handleJdFileUpload(e, 'create')} />
                    </label>
                    <span className="jd-upload-hint">The extracted text is pasted into the box below.</span>
                  </div>
                  <textarea
                    id="jd-form-desc"
                    className="form-textarea"
                    rows={5}
                    placeholder="Provide a concise description of responsibilities and benchmark qualification criteria..."
                    value={formDescription}
                    onChange={(e) => setFormDescription(e.target.value)}
                    required
                  />
                </div>

                <div className="modal-actions-bar">
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => setIsCreateOpen(false)}
                    disabled={isSubmitting}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={isSubmitting}
                  >
                    {isSubmitting ? 'Saving to Database...' : 'Save Job Description'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* Edit JD Modal / Form Overlay */}
        {isPrivileged && editingJd && (
          <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="edit-jd-modal-title">
            <div className="create-jd-modal-card">
              <div className="modal-header">
                <div>
                  <h2 id="edit-jd-modal-title" className="modal-title">
                    Edit Job Description
                  </h2>
                  <p className="modal-subtitle">
                    Update role specifications and required skills for &quot;{editingJd.title}&quot;.
                  </p>
                </div>
                <button
                  type="button"
                  className="modal-close-btn"
                  onClick={() => setEditingJd(null)}
                  aria-label="Close edit form"
                >
                  ✕
                </button>
              </div>

              {editError && (
                <div className="form-error-banner" role="alert">
                  <span aria-hidden="true">⚠️</span>
                  <span>{editError}</span>
                </div>
              )}

              <form className="create-jd-form" onSubmit={handleEditSubmit}>
                <div className="form-group">
                  <label htmlFor="jd-edit-title" className="form-label">
                    Job Title <span className="text-req">*</span>
                  </label>
                  <input
                    id="jd-edit-title"
                    type="text"
                    className="form-input"
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    required
                  />
                </div>

                <div className="form-row">
                  <div className="form-group form-col">
                    <label htmlFor="jd-edit-category" className="form-label">
                      Category
                    </label>
                    <select
                      id="jd-edit-category"
                      className="form-select"
                      value={editCategory}
                      onChange={(e) => setEditCategory(e.target.value)}
                    >
                      <option value="Engineering">Engineering</option>
                      <option value="AI & Data">AI & Data</option>
                      <option value="Design & UX">Design & UX</option>
                      <option value="Product Management">Product Management</option>
                      <option value="Operations">Operations</option>
                      <option value="General">General</option>
                    </select>
                  </div>

                  <div className="form-group form-col">
                    <label htmlFor="jd-edit-experience" className="form-label">
                      Required Experience
                    </label>
                    <input
                      id="jd-edit-experience"
                      type="text"
                      className="form-input"
                      value={editExperience}
                      onChange={(e) => setEditExperience(e.target.value)}
                    />
                  </div>
                </div>

                <div className="form-row">
                  <div className="form-group form-col">
                    <label htmlFor="jd-edit-employment" className="form-label">
                      Employment Type
                    </label>
                    <select
                      id="jd-edit-employment"
                      className="form-select"
                      value={editEmploymentType}
                      onChange={(e) => setEditEmploymentType(e.target.value)}
                    >
                      <option value="Full-time">Full-time</option>
                      <option value="Part-time">Part-time</option>
                      <option value="Contract">Contract</option>
                      <option value="Remote">Remote</option>
                    </select>
                  </div>

                  <div className="form-group form-col">
                    <label htmlFor="jd-edit-skills" className="form-label">
                      Skills &amp; Tags (comma-separated)
                    </label>
                    <input
                      id="jd-edit-skills"
                      type="text"
                      className="form-input"
                      value={editSkills}
                      onChange={(e) => setEditSkills(e.target.value)}
                    />
                  </div>
                </div>

                <div className="form-group">
                  <label htmlFor="jd-edit-desc" className="form-label">
                    Role Description &amp; Responsibilities <span className="text-req">*</span>
                  </label>
                  <div className="jd-upload-row">
                    <label className="btn btn-secondary btn-sm">
                      {isReadingFile ? 'Reading file…' : '⬆ Upload PDF / DOCX'}
                      <input type="file" accept=".pdf,.docx,.doc,.txt" hidden disabled={isReadingFile} onChange={(e) => handleJdFileUpload(e, 'edit')} />
                    </label>
                    <span className="jd-upload-hint">Replaces the description below with the extracted text.</span>
                  </div>
                  <textarea
                    id="jd-edit-desc"
                    className="form-textarea"
                    rows={5}
                    value={editDescription}
                    onChange={(e) => setEditDescription(e.target.value)}
                    required
                  />
                </div>

                <div className="modal-actions-bar">
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => setEditingJd(null)}
                    disabled={isEditSubmitting}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={isEditSubmitting}
                  >
                    {isEditSubmitting ? 'Saving Changes...' : 'Save Changes'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* Archive / Restore Confirmation Modal */}
        {isPrivileged && archiveConfirmJd && (
          <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="archive-modal-title">
            <div className="confirm-modal-box">
              <div
                className={archiveConfirmJd.is_archived ? 'confirm-modal-icon-restore' : 'confirm-modal-icon-danger'}
                aria-hidden="true"
              >
                {archiveConfirmJd.is_archived ? '↺' : '📦'}
              </div>
              <h2 id="archive-modal-title" className="confirm-modal-title">
                {archiveConfirmJd.is_archived ? 'Restore Job Description?' : 'Archive Job Description?'}
              </h2>
              <p className="confirm-modal-desc">
                {archiveConfirmJd.is_archived
                  ? `Restoring "${archiveConfirmJd.title}" will make this role selectable again when creating new screening sessions.`
                  : `Are you sure you want to archive "${archiveConfirmJd.title}"? It will no longer appear as a selectable role for new screening sessions.`}
              </p>

              <div className="confirm-modal-warning-box">
                {archiveConfirmJd.is_archived
                  ? 'Historical screening sessions and candidate evaluations previously linked to this role remain unaffected.'
                  : 'Soft archive is reversible. Historical screening sessions and candidate evaluations linked to this role are permanently preserved.'}
              </div>

              {archiveError && (
                <div className="form-error-banner" role="alert">
                  <span aria-hidden="true">⚠️</span>
                  <span>{archiveError}</span>
                </div>
              )}

              <div className="modal-actions-bar">
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setArchiveConfirmJd(null)}
                  disabled={isArchiveSubmitting}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className={archiveConfirmJd.is_archived ? 'btn btn-primary' : 'btn-danger-solid'}
                  onClick={handleConfirmArchiveOrRestore}
                  disabled={isArchiveSubmitting}
                >
                  {isArchiveSubmitting
                    ? archiveConfirmJd.is_archived
                      ? 'Restoring...'
                      : 'Archiving...'
                    : archiveConfirmJd.is_archived
                    ? 'Restore Role'
                    : 'Archive Role'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Permanent Delete Confirmation Modal (admin only) */}
        {isAdmin && deleteConfirmJd && (
          <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="delete-modal-title">
            <div className="confirm-modal-box">
              <div className="confirm-modal-icon-danger" aria-hidden="true">
                🗑️
              </div>
              <h2 id="delete-modal-title" className="confirm-modal-title">
                Delete Job Description permanently?
              </h2>
              <p className="confirm-modal-desc">
                &quot;{deleteConfirmJd.title}&quot; will be removed for good. This cannot be undone. Use Archive instead if you may need this role again.
              </p>

              {deleteSessionCount !== null && (
                <div className="confirm-modal-warning-box">
                  This role is used by {deleteSessionCount} screening session{deleteSessionCount === 1 ? '' : 's'}. Deleting it will also permanently delete
                  {deleteSessionCount === 1 ? ' that session' : ' those sessions'} with their uploaded resumes, evaluations and candidate results.
                </div>
              )}

              {deleteError && (
                <div className="form-error-banner" role="alert">
                  <span aria-hidden="true">⚠️</span>
                  <span>{deleteError}</span>
                </div>
              )}

              <div className="modal-actions-bar">
                <button type="button" className="btn btn-secondary" onClick={closeDeleteConfirm} disabled={isDeleteSubmitting}>
                  Cancel
                </button>
                <button type="button" className="btn-danger-solid" onClick={handleConfirmDelete} disabled={isDeleteSubmitting}>
                  {isDeleteSubmitting
                    ? 'Deleting...'
                    : deleteSessionCount !== null
                    ? `Delete role and ${deleteSessionCount} session${deleteSessionCount === 1 ? '' : 's'}`
                    : 'Delete Role'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Filter and Search Bar */}
        <div className="jd-controls-bar">
          <div className="jd-search-box">
            <svg
              className="jd-search-icon"
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
              className="jd-search-input"
              placeholder="Search by title, skills, or keywords..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              aria-label="Search job descriptions"
            />
            {searchQuery && (
              <button
                type="button"
                className="jd-clear-search"
                onClick={() => setSearchQuery('')}
                aria-label="Clear search query"
              >
                ✕
              </button>
            )}
          </div>

          <div className="jd-filter-group">
            <label htmlFor="category-filter" className="jd-filter-label">
              Category:
            </label>
            <select
              id="category-filter"
              className="jd-category-select"
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
            >
              {categories.map((cat) => (
                <option key={cat} value={cat}>
                  {cat}
                </option>
              ))}
            </select>
          </div>

          <div className="jd-filter-group">
            <label htmlFor="status-filter" className="jd-filter-label">
              Status:
            </label>
            <select
              id="status-filter"
              className="jd-status-select"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as 'all' | 'active' | 'archived')}
            >
              <option value="all">All Roles</option>
              <option value="active">Active Only</option>
              <option value="archived">Archived Only</option>
            </select>
          </div>

          <div className="jd-count-indicator">
            {isLoading
              ? 'Loading roles...'
              : `Showing ${filteredJDs.length} of ${jobDescriptions.length} roles`}
          </div>
        </div>

        {/* Content Area */}
        <div className="jd-content-area">
          {/* Loading State */}
          {isLoading && (
            <div className="jd-status-card" role="status">
              <div className="jd-spinner" aria-hidden="true" />
              <p className="status-title">Loading job descriptions from API...</p>
              <p className="status-sub">Connecting to {API_BASE_URL}/api/job-descriptions</p>
            </div>
          )}

          {/* Error State */}
          {!isLoading && apiError && (
            <div className="jd-error-card" role="alert">
              <div className="error-icon" aria-hidden="true">⚠️</div>
              <h3 className="error-title">Backend API Connection Error</h3>
              <p className="error-desc">{apiError}</p>
              <button
                type="button"
                className="btn btn-primary btn-retry"
                onClick={fetchJobDescriptions}
              >
                Retry Connection
              </button>
            </div>
          )}

          {/* Empty State (when API returns zero records) */}
          {!isLoading && !apiError && jobDescriptions.length === 0 && (
            <div className="jd-empty-state">
              <div className="empty-icon" aria-hidden="true">📋</div>
              <h3 className="empty-title">No job descriptions found</h3>
              <p className="empty-desc">
                {isPrivileged
                  ? 'Your database is empty. Create your first job description using the “Create JD” action above.'
                  : 'There are currently no job descriptions available in the database.'}
              </p>
              {isPrivileged && (
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => setIsCreateOpen(true)}
                >
                  + Create First Job Description
                </button>
              )}
            </div>
          )}

          {/* Filtered Empty State (records exist in DB, but filter matched 0) */}
          {!isLoading &&
            !apiError &&
            jobDescriptions.length > 0 &&
            filteredJDs.length === 0 && (
              <div className="jd-empty-state">
                <div className="empty-icon" aria-hidden="true">🔍</div>
                <h3 className="empty-title">No matching job descriptions</h3>
                <p className="empty-desc">
                  No roles match current filters.
                </p>
                <button
                  type="button"
                  className="btn-outline-sm"
                  onClick={() => {
                    setSearchQuery('')
                    setSelectedCategory('All Categories')
                    setStatusFilter('all')
                  }}
                >
                  Reset Filters
                </button>
              </div>
            )}

          {/* Cards Grid */}
          {!isLoading && !apiError && filteredJDs.length > 0 && (
            <div className="jd-cards-grid">
              {filteredJDs.map((jd) => {
                const skillsList = jd.skills || jd.tags || []
                return (
                  <article
                    key={jd.id}
                    className={`jd-card ${jd.is_archived ? 'jd-card-archived' : ''}`}
                    aria-labelledby={`jd-title-${jd.id}`}
                  >
                    {/* Card Header */}
                    <div className="jd-card-header">
                      <div className="jd-card-title-group">
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <div className="jd-category-badge">{jd.category}</div>
                          {jd.is_archived && (
                            <span className="jd-archived-badge">Archived</span>
                          )}
                        </div>
                        <h2 id={`jd-title-${jd.id}`} className="jd-card-title">
                          {jd.title}
                        </h2>
                      </div>

                      {/* Overflow menu - Role-gated: Viewers cannot see mutation actions */}
                      {isPrivileged && (
                        <div className="jd-overflow-container">
                          <button
                            type="button"
                            className="jd-overflow-btn"
                            onClick={() =>
                              setActiveMenuId(
                                activeMenuId === jd.id ? null : jd.id
                              )
                            }
                            aria-label={`More options for ${jd.title}`}
                            aria-expanded={activeMenuId === jd.id}
                          >
                            <svg
                              width="16"
                              height="16"
                              viewBox="0 0 24 24"
                              fill="currentColor"
                              aria-hidden="true"
                            >
                              <circle cx="12" cy="5" r="2" />
                              <circle cx="12" cy="12" r="2" />
                              <circle cx="12" cy="19" r="2" />
                            </svg>
                          </button>

                          {activeMenuId === jd.id && (
                            <div className="jd-dropdown-menu" role="menu">
                              <button
                                type="button"
                                className="jd-menu-item"
                                role="menuitem"
                                onClick={() => {
                                  setActiveMenuId(null)
                                  handleStartEdit(jd)
                                }}
                              >
                                Edit Criteria
                              </button>
                              <button
                                type="button"
                                className="jd-menu-item"
                                role="menuitem"
                                onClick={() => {
                                  setActiveMenuId(null)
                                  handleStartDuplicate(jd)
                                }}
                              >
                                Duplicate
                              </button>
                              <button
                                type="button"
                                className={`jd-menu-item ${jd.is_archived ? 'text-primary' : 'text-danger'}`}
                                role="menuitem"
                                onClick={() => {
                                  setActiveMenuId(null)
                                  handleStartArchiveConfirm(jd)
                                }}
                              >
                                {jd.is_archived ? 'Restore Role' : 'Archive'}
                              </button>
                              {isAdmin && (
                                <button
                                  type="button"
                                  className="jd-menu-item text-danger"
                                  role="menuitem"
                                  onClick={() => {
                                    setActiveMenuId(null)
                                    setDeleteConfirmJd(jd)
                                    setDeleteSessionCount(null)
                                    setDeleteError(null)
                                  }}
                                >
                                  Delete
                                </button>
                              )}
                            </div>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Description */}
                    <p className="jd-card-description">{jd.description}</p>

                    {/* Skills/Tags */}
                    {skillsList.length > 0 && (
                      <div
                        className="jd-tags-list"
                        aria-label="Key skill requirements"
                      >
                        {skillsList.map((tag) => (
                          <span key={tag} className="jd-tag">
                            {tag}
                          </span>
                        ))}
                      </div>
                    )}

                    {/* Metadata Row */}
                    <div className="jd-metadata-row">
                      <span className="jd-meta-item">
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
                        >
                          <rect
                            width="20"
                            height="14"
                            x="2"
                            y="7"
                            rx="2"
                            ry="2"
                          />
                          <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
                        </svg>
                        {jd.experience}
                      </span>
                      <span className="jd-meta-dot">•</span>
                      <span className="jd-meta-item">
                        {jd.employment_type || 'Full-time'}
                      </span>
                    </div>

                    {/* Card Footer */}
                    <div className="jd-card-footer">
                      <span className="jd-updated-text">
                        {formatDisplayDate(jd.created_at)}
                      </span>
                      {isPrivileged && (
                        jd.is_archived ? (
                          <span className="jd-archived-pill" title="Archived roles cannot be used for new screening sessions">
                            Archived
                          </span>
                        ) : (
                          <button
                            type="button"
                            className="btn-use-jd"
                            onClick={() => onUseJd(jd.id)}
                          >
                            <span>Use</span>
                            <svg
                              width="14"
                              height="14"
                              viewBox="0 0 24 24"
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="2.5"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              aria-hidden="true"
                            >
                              <polyline points="9 18 15 12 9 6" />
                            </svg>
                          </button>
                        )
                      )}
                    </div>
                  </article>
                )
              })}
            </div>
          )}
        </div>
      </main>
    </div>
  )
}

import { useState, useMemo, useEffect, type FormEvent } from 'react'
import { Sidebar, type AppScreen } from './Sidebar'
import { API_BASE_URL } from './config'
import { apiFetch } from './api'
import { useAuth } from './auth'
import './Dashboard.css'
import './JobDescriptions.css'
import './Users.css'

interface UsersProps {
  onNavigate: (screen: AppScreen) => void
}

export interface ApiUser {
  id: string
  email: string
  role: 'admin' | 'recruiter' | 'viewer'
  status: 'active' | 'invited' | 'disabled'
  created_at: string
  updated_at: string
}

type RoleFilter = 'All' | 'admin' | 'recruiter' | 'viewer'

interface OneTimeInvitation {
  email: string
  role: string
  token: string
  expiresAt: string
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

export function Users({ onNavigate }: UsersProps) {
  const { isAdmin } = useAuth()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [roleFilter, setRoleFilter] = useState<RoleFilter>('All')

  // API State
  const [users, setUsers] = useState<ApiUser[]>([])
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [apiError, setApiError] = useState<string | null>(null)

  // Invite Modal State
  const [isInviteModalOpen, setIsInviteModalOpen] = useState<boolean>(false)
  const [inviteEmail, setInviteEmail] = useState<string>('')
  const [inviteRole, setInviteRole] = useState<'admin' | 'recruiter' | 'viewer'>('recruiter')
  const [isInviting, setIsInviting] = useState<boolean>(false)
  const [inviteError, setInviteError] = useState<string | null>(null)

  // One-time Token Dialog State (held strictly in memory until dismissed)
  const [invitationResult, setInvitationResult] = useState<OneTimeInvitation | null>(null)
  const [copiedNotice, setCopiedNotice] = useState<boolean>(false)

  // Role Edit Modal State
  const [editingUser, setEditingUser] = useState<ApiUser | null>(null)
  const [targetRole, setTargetRole] = useState<'admin' | 'recruiter' | 'viewer'>('recruiter')
  const [isUpdatingRole, setIsUpdatingRole] = useState<boolean>(false)
  const [roleUpdateError, setRoleUpdateError] = useState<string | null>(null)
  const [roleUpdateSuccess, setRoleUpdateSuccess] = useState<string | null>(null)

  // Status Action / Confirmation State
  const [confirmDisableUser, setConfirmDisableUser] = useState<ApiUser | null>(null)
  const [isDisabling, setIsDisabling] = useState<boolean>(false)
  const [disableError, setDisableError] = useState<string | null>(null)

  const [statusActionUser, setStatusActionUser] = useState<ApiUser | null>(null)
  const [isReactivating, setIsReactivating] = useState<boolean>(false)
  const [reactivateError, setReactivateError] = useState<{ user: ApiUser; message: string } | null>(null)
  const [statusNotice, setStatusNotice] = useState<string | null>(null)

  const fetchUsers = async () => {
    setIsLoading(true)
    setApiError(null)
    try {
      const response = await apiFetch('/api/users')
      if (!response.ok) {
        if (response.status === 401) {
          throw new Error('Authentication session expired. Please sign in again.')
        } else if (response.status === 403) {
          throw new Error('Access denied. Administrator privileges are required to view the user directory.')
        } else {
          throw new Error(`Failed to load users (HTTP ${response.status}).`)
        }
      }
      const data: ApiUser[] = await response.json()
      setUsers(data)
    } catch (err: unknown) {
      if (err instanceof Error) {
        setApiError(err.message)
      } else {
        setApiError('Unable to connect to the backend user directory.')
      }
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchUsers()
  }, [])

  const handleOpenInviteModal = () => {
    setInviteEmail('')
    setInviteRole('recruiter')
    setInviteError(null)
    setIsInviteModalOpen(true)
  }

  const handleCloseInviteModal = () => {
    setIsInviteModalOpen(false)
    setInviteError(null)
  }

  const handleInviteSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setInviteError(null)

    const normalizedEmail = inviteEmail.trim().toLowerCase()
    if (!normalizedEmail || !normalizedEmail.includes('@')) {
      setInviteError('Please provide a valid email address.')
      return
    }

    setIsInviting(true)
    try {
      const response = await apiFetch('/api/users/invite', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          email: normalizedEmail,
          role: inviteRole,
        }),
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => null)
        if (response.status === 400 && errorData?.detail) {
          throw new Error(errorData.detail)
        } else if (response.status === 403) {
          throw new Error('Access denied. Administrator privileges are required to invite users.')
        } else {
          throw new Error(`Failed to create invitation (HTTP ${response.status}).`)
        }
      }

      const data = await response.json()

      // Close invite modal and clear form inputs
      setIsInviteModalOpen(false)
      setInviteEmail('')
      setInviteRole('recruiter')

      // Set one-time invitation token strictly in temporary state for the modal
      setInvitationResult({
        email: normalizedEmail,
        role: inviteRole,
        token: data.invitation_token,
        expiresAt: data.expires_at,
      })

      // Refresh the live user directory without losing search/filter state
      fetchUsers()
    } catch (err: unknown) {
      if (err instanceof Error) {
        setInviteError(err.message)
      } else {
        setInviteError('Unable to process user invitation.')
      }
    } finally {
      setIsInviting(false)
    }
  }

  const handleCloseTokenDialog = () => {
    // Clear the one-time token immediately from memory when dismissed
    setInvitationResult(null)
    setCopiedNotice(false)
  }

  const handleCopyToken = async () => {
    if (!invitationResult?.token) return
    try {
      await navigator.clipboard.writeText(invitationResult.token)
      setCopiedNotice(true)
      setTimeout(() => setCopiedNotice(false), 3000)
    } catch {
      // Fallback if clipboard API is restricted
      setCopiedNotice(false)
    }
  }

  // Role Edit Handlers
  const handleOpenRoleEdit = (user: ApiUser) => {
    setEditingUser(user)
    setTargetRole(user.role)
    setRoleUpdateError(null)
  }

  const handleCloseRoleEdit = () => {
    if (isUpdatingRole) return
    setEditingUser(null)
    setRoleUpdateError(null)
  }

  const handleSaveRole = async (e?: FormEvent) => {
    if (e) e.preventDefault()
    if (!editingUser) return

    setIsUpdatingRole(true)
    setRoleUpdateError(null)

    try {
      const response = await apiFetch(`/api/users/${editingUser.id}/role`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          role: targetRole,
        }),
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => null)
        if (response.status === 400 && errorData?.detail) {
          throw new Error(errorData.detail)
        } else if (response.status === 404) {
          throw new Error('User not found.')
        } else if (response.status === 403) {
          throw new Error('Forbidden: Only administrators can modify roles.')
        } else {
          throw new Error(`Failed to update role (HTTP ${response.status}).`)
        }
      }

      const updatedUser: ApiUser = await response.json()

      // Update local state without resetting search or filter state
      setUsers((prevUsers) =>
        prevUsers.map((u) => (u.id === updatedUser.id ? updatedUser : u))
      )
      setRoleUpdateSuccess(`Role updated to "${updatedUser.role}" for ${updatedUser.email}.`)
      setEditingUser(null)
    } catch (err: unknown) {
      if (err instanceof Error) {
        setRoleUpdateError(err.message)
      } else {
        setRoleUpdateError('An unexpected error occurred while updating the role.')
      }
    } finally {
      setIsUpdatingRole(false)
    }
  }

  // Status Change Handlers
  const handleOpenDisableConfirm = (user: ApiUser) => {
    setConfirmDisableUser(user)
    setDisableError(null)
  }

  const handleCloseDisableConfirm = () => {
    if (isDisabling) return
    setConfirmDisableUser(null)
    setDisableError(null)
  }

  const handleConfirmDisable = async () => {
    if (!confirmDisableUser) return
    setIsDisabling(true)
    setDisableError(null)

    try {
      const response = await apiFetch(`/api/users/${confirmDisableUser.id}/status`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          status: 'disabled',
        }),
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => null)
        if (response.status === 400 && errorData?.detail) {
          throw new Error(errorData.detail)
        } else if (response.status === 404) {
          throw new Error('User not found.')
        } else if (response.status === 403) {
          throw new Error('Forbidden: Only administrators can modify account status.')
        } else {
          throw new Error(`Failed to disable account (HTTP ${response.status}).`)
        }
      }

      const updatedUser: ApiUser = await response.json()

      // Update local state without resetting search or filter state
      setUsers((prevUsers) =>
        prevUsers.map((u) => (u.id === updatedUser.id ? updatedUser : u))
      )
      setStatusNotice(`Account for "${updatedUser.email}" has been disabled.`)
      setConfirmDisableUser(null)
    } catch (err: unknown) {
      if (err instanceof Error) {
        setDisableError(err.message)
      } else {
        setDisableError('An unexpected error occurred while disabling the account.')
      }
    } finally {
      setIsDisabling(false)
    }
  }

  const handleReactivateUser = async (user: ApiUser) => {
    setStatusActionUser(user)
    setIsReactivating(true)
    setReactivateError(null)

    try {
      const response = await apiFetch(`/api/users/${user.id}/status`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          status: 'active',
        }),
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => null)
        if (response.status === 400 && errorData?.detail) {
          throw new Error(errorData.detail)
        } else if (response.status === 404) {
          throw new Error('User not found.')
        } else if (response.status === 403) {
          throw new Error('Forbidden: Only administrators can modify account status.')
        } else {
          throw new Error(`Failed to reactivate account (HTTP ${response.status}).`)
        }
      }

      const updatedUser: ApiUser = await response.json()

      // Update local state without resetting search or filter state
      setUsers((prevUsers) =>
        prevUsers.map((u) => (u.id === updatedUser.id ? updatedUser : u))
      )
      setStatusNotice(`Account for "${updatedUser.email}" has been reactivated.`)
      setReactivateError(null)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'An unexpected error occurred while reactivating the account.'
      setReactivateError({ user, message: msg })
    } finally {
      setIsReactivating(false)
      setStatusActionUser(null)
    }
  }

  // Local search and role filtering
  const filteredUsers = useMemo(() => {
    return users.filter((user: ApiUser) => {
      const matchesRole = roleFilter === 'All' || user.role === roleFilter

      const q = searchQuery.toLowerCase().trim()
      const matchesSearch =
        !q ||
        user.email.toLowerCase().includes(q) ||
        user.id.toLowerCase().includes(q)

      return matchesRole && matchesSearch
    })
  }, [users, searchQuery, roleFilter])

  const handleClearFilters = () => {
    setSearchQuery('')
    setRoleFilter('All')
  }

  return (
    <div className="dashboard-layout">
      {/* Shared Dark Left Sidebar */}
      <Sidebar
        activeScreen="users"
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
              <h1 className="welcome-heading">Users &amp; Permissions</h1>
              <p className="welcome-subtext">
                Administrator directory of registered user accounts and workspace access roles.
              </p>
            </div>
          </div>

          {isAdmin && (
            <div className="topbar-actions">
              <button
                type="button"
                className="btn btn-primary btn-invite-user"
                onClick={handleOpenInviteModal}
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
                <span>Invite User</span>
              </button>
            </div>
          )}
        </header>

        {/* Invite User Modal Dialog */}
        {isInviteModalOpen && (
          <div
            className="modal-backdrop"
            role="dialog"
            aria-modal="true"
            aria-labelledby="invite-modal-title"
          >
            <div className="invite-modal-card">
              <div className="modal-header">
                <div>
                  <h2 id="invite-modal-title" className="modal-title">
                    Invite Workspace User
                  </h2>
                  <p className="modal-subtitle">
                    Register a new user account with assigned role access permissions.
                  </p>
                </div>
                <button
                  type="button"
                  className="modal-close-btn"
                  onClick={handleCloseInviteModal}
                  aria-label="Close form"
                >
                  ✕
                </button>
              </div>

              <div
                style={{
                  backgroundColor: '#f8fafc',
                  border: '1px solid #e2e8f0',
                  borderRadius: '8px',
                  padding: '10px 14px',
                  marginBottom: '16px',
                  fontSize: '12.5px',
                  color: '#475569',
                  lineHeight: '1.45',
                }}
              >
                ℹ️ <strong>Email delivery is not configured.</strong> A one-time activation token will be generated for you to share manually with the invitee through a secure channel.
              </div>

              {inviteError && (
                <div className="form-error-banner" role="alert" style={{ marginBottom: '16px' }}>
                  <span aria-hidden="true">⚠️</span>
                  <span>{inviteError}</span>
                </div>
              )}

              <form onSubmit={handleInviteSubmit} className="create-jd-form">
                <div className="form-group">
                  <label htmlFor="invite-email-input" className="form-label">
                    Corporate Email Address <span className="text-req">*</span>
                  </label>
                  <input
                    id="invite-email-input"
                    type="email"
                    className="form-input"
                    placeholder="colleague@company.com"
                    value={inviteEmail}
                    onChange={(e) => setInviteEmail(e.target.value)}
                    autoComplete="off"
                    required
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="invite-role-select" className="form-label">
                    Assigned Workspace Role <span className="text-req">*</span>
                  </label>
                  <select
                    id="invite-role-select"
                    className="form-select"
                    value={inviteRole}
                    onChange={(e) =>
                      setInviteRole(e.target.value as 'admin' | 'recruiter' | 'viewer')
                    }
                  >
                    <option value="recruiter">Recruiter (Pipeline Access)</option>
                    <option value="viewer">Viewer (Read-Only)</option>
                    <option value="admin">Admin (Full Workspace Access)</option>
                  </select>
                </div>

                <div className="modal-actions-bar" style={{ marginTop: '20px' }}>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={handleCloseInviteModal}
                    disabled={isInviting}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={isInviting}
                  >
                    {isInviting ? 'Generating Invitation...' : 'Create Invitation'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* One-Time Invitation Token Display Dialog */}
        {invitationResult && (
          <div
            className="modal-backdrop"
            role="dialog"
            aria-modal="true"
            aria-labelledby="token-dialog-title"
          >
            <div className="token-dialog-card">
              <div className="modal-header">
                <div>
                  <h2 id="token-dialog-title" className="modal-title">
                    One-Time Invitation Token
                  </h2>
                  <p className="modal-subtitle">
                    Account invited for <strong>{invitationResult.email}</strong> as{' '}
                    <span style={{ textTransform: 'capitalize' }}>{invitationResult.role}</span>.
                  </p>
                </div>
                <button
                  type="button"
                  className="modal-close-btn"
                  onClick={handleCloseTokenDialog}
                  aria-label="Dismiss token dialog"
                >
                  ✕
                </button>
              </div>

              <div className="token-warning-callout" role="alert">
                <span className="warning-icon" aria-hidden="true">⚠️</span>
                <div className="warning-text">
                  <strong>Copy this token now.</strong> It will not be shown again and cannot be retrieved once this dialog is closed. Email delivery is not configured, so you must communicate this token manually through a secure, encrypted channel.
                </div>
              </div>

              <div className="token-box-wrapper">
                <input
                  type="text"
                  readOnly
                  className="token-display-input"
                  value={invitationResult.token}
                  aria-label="One-time invitation token"
                  onFocus={(e) => e.target.select()}
                />
                <button
                  type="button"
                  className="btn-copy-token"
                  onClick={handleCopyToken}
                  aria-label="Copy invitation token"
                >
                  {copiedNotice ? (
                    <>
                      <span aria-hidden="true">✓</span>
                      <span>Copied!</span>
                    </>
                  ) : (
                    <>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                        <rect width="14" height="14" x="8" y="8" rx="2" ry="2" />
                        <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" />
                      </svg>
                      <span>Copy Token</span>
                    </>
                  )}
                </button>
              </div>

              <div className="token-metadata-row">
                <span>
                  <strong>Instructions for invitee:</strong> Direct the user to the Sign In screen, click &ldquo;Accept Invitation&rdquo;, and enter this token along with their chosen password.
                </span>
                {invitationResult.expiresAt && (
                  <span style={{ marginTop: '4px' }}>
                    <strong>Token Expiration:</strong> Valid until {new Date(invitationResult.expiresAt).toLocaleString()}.
                  </span>
                )}
              </div>

              <div className="modal-actions-bar">
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={handleCloseTokenDialog}
                  style={{ width: '100%' }}
                >
                  Done (Dismiss &amp; Clear Token)
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Change User Role Modal Dialog */}
        {isAdmin && editingUser && (
          <div
            className="modal-backdrop"
            role="dialog"
            aria-modal="true"
            aria-labelledby="edit-role-modal-title"
          >
            <div className="invite-modal-card">
              <div className="modal-header">
                <div>
                  <h2 id="edit-role-modal-title" className="modal-title">
                    Change User Role
                  </h2>
                  <p className="modal-subtitle">
                    Update assigned workspace permissions for <strong>{editingUser.email}</strong>.
                  </p>
                </div>
                <button
                  type="button"
                  className="modal-close-btn"
                  onClick={handleCloseRoleEdit}
                  disabled={isUpdatingRole}
                  aria-label="Close dialog"
                >
                  ✕
                </button>
              </div>

              {roleUpdateError && (
                <div className="form-error-banner" role="alert" style={{ marginBottom: '16px' }}>
                  <span aria-hidden="true">⚠️</span>
                  <div style={{ flex: 1 }}>
                    <div>{roleUpdateError}</div>
                    <button
                      type="button"
                      className="btn-retry-inline"
                      onClick={() => handleSaveRole()}
                      style={{
                        marginTop: '6px',
                        background: 'none',
                        border: 'none',
                        color: '#b91c1c',
                        fontWeight: 700,
                        textDecoration: 'underline',
                        cursor: 'pointer',
                        padding: 0,
                        fontSize: '12px',
                        fontFamily: 'inherit',
                      }}
                    >
                      Retry Update
                    </button>
                  </div>
                </div>
              )}

              <form onSubmit={handleSaveRole} className="create-jd-form">
                <div className="form-group">
                  <label className="form-label">User Email</label>
                  <input
                    type="text"
                    readOnly
                    className="form-input"
                    value={editingUser.email}
                    disabled
                    style={{ backgroundColor: '#f1f5f9', cursor: 'not-allowed' }}
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="edit-role-select" className="form-label">
                    Assigned Role <span className="text-req">*</span>
                  </label>
                  <select
                    id="edit-role-select"
                    className="form-select"
                    value={targetRole}
                    onChange={(e) =>
                      setTargetRole(e.target.value as 'admin' | 'recruiter' | 'viewer')
                    }
                    disabled={isUpdatingRole}
                  >
                    <option value="admin">Admin (Full Workspace Access)</option>
                    <option value="recruiter">Recruiter (Screening &amp; Candidate Access)</option>
                    <option value="viewer">Viewer (Read-Only Access)</option>
                  </select>
                </div>

                <div className="modal-actions-bar" style={{ marginTop: '20px' }}>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={handleCloseRoleEdit}
                    disabled={isUpdatingRole}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={isUpdatingRole}
                  >
                    {isUpdatingRole ? 'Updating Role...' : 'Save Role'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* Disable User Confirmation Modal Dialog */}
        {confirmDisableUser && (
          <div
            className="modal-backdrop"
            role="dialog"
            aria-modal="true"
            aria-labelledby="disable-modal-title"
          >
            <div className="invite-modal-card">
              <div className="modal-header">
                <div>
                  <h2 id="disable-modal-title" className="modal-title" style={{ color: '#b91c1c' }}>
                    Disable User Account
                  </h2>
                  <p className="modal-subtitle">
                    Deactivate access for <strong>{confirmDisableUser.email}</strong>.
                  </p>
                </div>
                <button
                  type="button"
                  className="modal-close-btn"
                  onClick={handleCloseDisableConfirm}
                  disabled={isDisabling}
                  aria-label="Close dialog"
                >
                  ✕
                </button>
              </div>

              <div
                style={{
                  backgroundColor: '#fef2f2',
                  border: '1px solid #fecaca',
                  borderRadius: '8px',
                  padding: '12px 14px',
                  marginBottom: '16px',
                  fontSize: '13px',
                  color: '#991b1b',
                  lineHeight: '1.5',
                }}
              >
                ⚠️ <strong>Warning:</strong> Disabling this account will immediately revoke all active login sessions and any pending invitations. The user will be barred from signing in until reactivated.
              </div>

              {disableError && (
                <div className="form-error-banner" role="alert" style={{ marginBottom: '16px' }}>
                  <span aria-hidden="true">⚠️</span>
                  <div style={{ flex: 1 }}>
                    <div>{disableError}</div>
                    <button
                      type="button"
                      className="btn-retry-inline"
                      onClick={() => handleConfirmDisable()}
                      style={{
                        marginTop: '6px',
                        background: 'none',
                        border: 'none',
                        color: '#b91c1c',
                        fontWeight: 700,
                        textDecoration: 'underline',
                        cursor: 'pointer',
                        padding: 0,
                        fontSize: '12px',
                        fontFamily: 'inherit',
                      }}
                    >
                      Retry Disable
                    </button>
                  </div>
                </div>
              )}

              <div className="modal-actions-bar" style={{ marginTop: '20px' }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={handleCloseDisableConfirm}
                  disabled={isDisabling}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="btn btn-danger-action"
                  onClick={handleConfirmDisable}
                  disabled={isDisabling}
                >
                  {isDisabling ? 'Disabling Account...' : 'Confirm Disable'}
                </button>
              </div>
            </div>
          </div>
        )}

        <div className="users-page-content">
          {/* Success Alert Toast for Role Changes */}
          {roleUpdateSuccess && (
            <div className="dashboard-notice notice-success" role="status" aria-live="polite">
              <span className="notice-icon" aria-hidden="true">✓</span>
              <span className="notice-text">{roleUpdateSuccess}</span>
              <button
                type="button"
                className="notice-dismiss"
                onClick={() => setRoleUpdateSuccess(null)}
                aria-label="Dismiss notice"
              >
                ✕
              </button>
            </div>
          )}

          {/* Success Alert Toast for Status Changes */}
          {statusNotice && (
            <div className="dashboard-notice notice-success" role="status" aria-live="polite">
              <span className="notice-icon" aria-hidden="true">✓</span>
              <span className="notice-text">{statusNotice}</span>
              <button
                type="button"
                className="notice-dismiss"
                onClick={() => setStatusNotice(null)}
                aria-label="Dismiss notice"
              >
                ✕
              </button>
            </div>
          )}

          {/* Retryable Error Banner for Reactivation */}
          {reactivateError && (
            <div className="form-error-banner" role="alert" style={{ marginBottom: '16px' }}>
              <span aria-hidden="true">⚠️</span>
              <div
                style={{
                  flex: 1,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  flexWrap: 'wrap',
                  gap: '8px',
                }}
              >
                <span>
                  Failed to reactivate <strong>{reactivateError.user.email}</strong>: {reactivateError.message}
                </span>
                <button
                  type="button"
                  className="btn-retry-inline"
                  onClick={() => handleReactivateUser(reactivateError.user)}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: '#b91c1c',
                    fontWeight: 700,
                    textDecoration: 'underline',
                    cursor: 'pointer',
                    padding: 0,
                    fontSize: '13px',
                    fontFamily: 'inherit',
                  }}
                >
                  Retry Reactivate
                </button>
              </div>
            </div>
          )}

          {/* Informational Policy Reference Banner */}
          <div className="persistent-preview-banner" role="status">
            <span className="preview-icon" aria-hidden="true">ℹ️</span>
            <div className="preview-banner-text">
              <strong>Admin-Only User Directory</strong>
              <span>
                Displays live user accounts queried directly from the local database. Account mutations, invitation workflows, and password resets are managed at the system administration level.
              </span>
            </div>
          </div>

          {/* Three Roles Explanation Cards (General Reference Policy) */}
          <div className="section-header-row" style={{ marginTop: '4px' }}>
            <div>
              <h2 className="section-title" style={{ fontSize: '15px' }}>
                General Access Policy Reference
              </h2>
              <p className="section-subtitle" style={{ fontSize: '13px' }}>
                Reference guide for role-based permissions enforced across this workspace.
              </p>
            </div>
          </div>

          <section className="roles-overview-grid" aria-label="Role Access Levels">
            <div className="role-card card-role-admin">
              <div className="role-card-header">
                <span className="role-badge badge-role-admin">Admin</span>
                <span className="role-access-tag">Full Access</span>
              </div>
              <h3 className="role-title">Workspace Administration</h3>
              <p className="role-description">
                Complete control over workspace configuration. Can create and configure job descriptions, manage screening runs, view the user directory, assign roles, and access system settings.
              </p>
            </div>

            <div className="role-card card-role-recruiter">
              <div className="role-card-header">
                <span className="role-badge badge-role-recruiter">Recruiter</span>
                <span className="role-access-tag">Pipeline Access</span>
              </div>
              <h3 className="role-title">Screening Operations</h3>
              <p className="role-description">
                Can create new screening sessions, upload resumes, run criteria evaluations, and search evidence. Cannot view or manage workspace users or system settings.
              </p>
            </div>

            <div className="role-card card-role-viewer">
              <div className="role-card-header">
                <span className="role-badge badge-role-viewer">Viewer</span>
                <span className="role-access-tag">Read-Only</span>
              </div>
              <h3 className="role-title">Auditing &amp; Review</h3>
              <p className="role-description">
                Read-only access to Job Descriptions and completed screening session metadata. Cannot view resume contents, run screenings, or access user accounts.
              </p>
            </div>
          </section>

          {/* Search & Role Filter Toolbar */}
          <div className="users-controls-bar">
            <div className="users-search-box">
              <svg
                className="users-search-icon"
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
                className="users-search-input"
                placeholder="Search by user email or ID..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                aria-label="Search users by email or ID"
              />
              {searchQuery && (
                <button
                  type="button"
                  className="users-clear-search"
                  onClick={() => setSearchQuery('')}
                  aria-label="Clear search input"
                >
                  ✕
                </button>
              )}
            </div>

            <div className="users-filter-group">
              <label htmlFor="role-filter-select" className="users-filter-label">
                Role:
              </label>
              <select
                id="role-filter-select"
                className="users-role-select"
                value={roleFilter}
                onChange={(e) => setRoleFilter(e.target.value as RoleFilter)}
              >
                <option value="All">All Roles</option>
                <option value="admin">Admin</option>
                <option value="recruiter">Recruiter</option>
                <option value="viewer">Viewer</option>
              </select>
            </div>

            <div className="users-count-indicator">
              Showing {filteredUsers.length} of {users.length} accounts
            </div>
          </div>

          {/* Users Table Card */}
          <section className="table-container-card" aria-labelledby="users-table-title">
            <div className="table-header-row">
              <div>
                <h2 id="users-table-title" className="section-title">
                  Registered Users
                </h2>
                <p className="section-subtitle">
                  Live user records registered in the persistent database.
                </p>
              </div>
            </div>

            {/* Loading State */}
            {isLoading && (
              <div className="users-status-card" role="status">
                <div className="users-spinner" aria-hidden="true" />
                <p className="status-title">Loading user directory from database...</p>
                <p className="status-sub">Connecting to {API_BASE_URL}/api/users</p>
              </div>
            )}

            {/* API Error State */}
            {!isLoading && apiError && (
              <div className="users-error-card" role="alert">
                <div className="error-icon" aria-hidden="true">⚠️</div>
                <h3 className="error-title">Unable to Load Users</h3>
                <p className="error-desc">{apiError}</p>
                <button
                  type="button"
                  className="btn-retry-users"
                  onClick={fetchUsers}
                >
                  Retry Connection
                </button>
              </div>
            )}

            {/* Empty DB State */}
            {!isLoading && !apiError && users.length === 0 && (
              <div className="users-empty-state">
                <div className="empty-icon" aria-hidden="true">📋</div>
                <h3 className="empty-title">No users found</h3>
                <p className="empty-sub">
                  There are no user accounts saved in the database.
                </p>
              </div>
            )}

            {/* Empty Filtered State */}
            {!isLoading && !apiError && users.length > 0 && filteredUsers.length === 0 && (
              <div className="users-empty-state">
                <div className="empty-icon" aria-hidden="true">🔍</div>
                <h3 className="empty-title">No matching users found</h3>
                <p className="empty-sub">
                  No accounts match &ldquo;{searchQuery}&rdquo; and role filter &ldquo;{roleFilter}&rdquo;.
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

            {/* Live Data Table */}
            {!isLoading && !apiError && filteredUsers.length > 0 && (
              <div className="table-responsive-wrapper">
                <table className="users-table">
                  <thead>
                    <tr>
                      <th scope="col">User Email</th>
                      <th scope="col">Role</th>
                      <th scope="col">Status</th>
                      <th scope="col">Date Created</th>
                      <th scope="col">User ID</th>
                      {isAdmin && <th scope="col" className="col-action">Action</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {filteredUsers.map((user) => (
                      <tr key={user.id}>
                        <td className="cell-user-profile">
                          <div className="user-profile-wrap">
                            <div className="user-avatar-circle" aria-hidden="true">
                              {user.email.slice(0, 2).toUpperCase()}
                            </div>
                            <div className="user-meta-texts">
                              <span className="user-fullname">{user.email}</span>
                            </div>
                          </div>
                        </td>

                        <td className="cell-role">
                          <span
                            className={`role-pill ${
                              user.role === 'admin'
                                ? 'pill-admin'
                                : user.role === 'recruiter'
                                ? 'pill-recruiter'
                                : 'pill-viewer'
                            }`}
                          >
                            {user.role.charAt(0).toUpperCase() + user.role.slice(1)}
                          </span>
                        </td>

                        <td className="cell-status">
                          <span
                            className={`status-pill ${
                              user.status === 'active'
                                ? 'status-completed'
                                : user.status === 'disabled'
                                ? 'status-disabled'
                                : 'status-inprogress'
                            }`}
                          >
                            <span className="status-dot" aria-hidden="true" />
                            {user.status.charAt(0).toUpperCase() + user.status.slice(1)}
                          </span>
                        </td>

                        <td className="cell-last-active">
                          {formatDisplayDate(user.created_at)}
                        </td>

                        <td
                          className="cell-user-id"
                          style={{
                            color: '#94a3b8',
                            fontSize: '12px',
                            fontFamily: 'monospace',
                          }}
                        >
                          {user.id}
                        </td>

                        {isAdmin && (
                          <td className="col-action">
                            <div className="users-actions-wrap">
                              <button
                                type="button"
                                className="btn-edit-role"
                                onClick={() => handleOpenRoleEdit(user)}
                                aria-label={`Change role for ${user.email}`}
                              >
                                Edit Role
                              </button>

                              {user.status === 'active' && (
                                <button
                                  type="button"
                                  className="btn-status-action btn-status-disable"
                                  onClick={() => handleOpenDisableConfirm(user)}
                                  aria-label={`Disable account for ${user.email}`}
                                >
                                  Disable
                                </button>
                              )}

                              {user.status === 'disabled' && (
                                <button
                                  type="button"
                                  className="btn-status-action btn-status-reactivate"
                                  onClick={() => handleReactivateUser(user)}
                                  disabled={isReactivating && statusActionUser?.id === user.id}
                                  aria-label={`Reactivate account for ${user.email}`}
                                >
                                  {isReactivating && statusActionUser?.id === user.id ? 'Reactivating...' : 'Reactivate'}
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
    </div>
  )
}

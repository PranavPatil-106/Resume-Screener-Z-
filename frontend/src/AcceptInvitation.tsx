import { useState, type FormEvent } from 'react'
import { apiFetch } from './api'
import './App.css'

interface AcceptInvitationProps {
  onNavigateToSignIn: () => void
}

export function AcceptInvitation({ onNavigateToSignIn }: AcceptInvitationProps) {
  const [token, setToken] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [isSuccess, setIsSuccess] = useState(false)
  const [activatedEmail, setActivatedEmail] = useState<string | null>(null)

  const handleAccept = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setErrorMessage(null)

    const trimmedToken = token.trim()
    if (!trimmedToken) {
      setErrorMessage('Please provide your invitation token.')
      return
    }

    if (!password || password.length < 8) {
      setErrorMessage('Password must be at least 8 characters long.')
      return
    }

    if (password !== confirmPassword) {
      setErrorMessage('Passwords do not match. Please re-enter your confirmation password.')
      return
    }

    setIsSubmitting(true)
    try {
      const response = await apiFetch('/api/auth/accept-invitation', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          token: trimmedToken,
          password: password,
        }),
      })

      if (response.ok) {
        const data = await response.json()
        setIsSuccess(true)
        setActivatedEmail(data.user?.email || null)
      } else {
        // Return generic error to prevent token enumeration
        setErrorMessage(
          'Invalid, expired, or already-consumed invitation token. Please check your token or contact your administrator.'
        )
      }
    } catch {
      setErrorMessage(
        'Authentication service is currently unavailable. Please ensure the backend server is running.'
      )
    } finally {
      // Clear token and passwords immediately after submission - never store in browser storage
      setToken('')
      setPassword('')
      setConfirmPassword('')
      setIsSubmitting(false)
    }
  }

  return (
    <div className="page-container">
      {/* Decorative ambient circular shapes */}
      <div className="bg-circle bg-circle-1" aria-hidden="true" />
      <div className="bg-circle bg-circle-2" aria-hidden="true" />
      <div className="bg-circle bg-circle-3" aria-hidden="true" />
      <div className="bg-circle bg-circle-4" aria-hidden="true" />

      <main className="auth-wrapper">
        {/* Centered Branding */}
        <header className="brand-header">
          <div className="brand-logo-mark" aria-hidden="true">
            <svg
              width="26"
              height="26"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <path d="m9 15 2 2 4-4" />
            </svg>
          </div>
          <h1 className="brand-title">AI Resume Screener</h1>
          <p className="brand-subtitle">
            Local HR intelligence suite for candidate evaluation.
          </p>
        </header>

        {/* Auth Card Container */}
        <section className="auth-card" aria-labelledby="accept-invitation-heading">
          {isSuccess ? (
            <div className="activation-success-card" style={{ textAlign: 'center', padding: '16px 0' }}>
              <div
                style={{
                  width: '56px',
                  height: '56px',
                  borderRadius: '50%',
                  backgroundColor: '#dcfce7',
                  color: '#16a34a',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '28px',
                  margin: '0 auto 16px',
                }}
                aria-hidden="true"
              >
                ✓
              </div>
              <h2 id="accept-invitation-heading" className="card-title" style={{ marginBottom: '8px' }}>
                Account Activated!
              </h2>
              <p className="card-subtitle" style={{ marginBottom: '20px' }}>
                {activatedEmail ? (
                  <>
                    Account for <strong>{activatedEmail}</strong> is now active.
                  </>
                ) : (
                  'Your account has been successfully activated.'
                )}
                {' '}You can now sign in using your corporate email and password.
              </p>
              <button
                type="button"
                className="btn btn-primary"
                onClick={onNavigateToSignIn}
                style={{ width: '100%' }}
              >
                <span>Proceed to Sign In</span>
                <span aria-hidden="true">→</span>
              </button>
            </div>
          ) : (
            <>
              <div className="card-header">
                <h2 id="accept-invitation-heading" className="card-title">
                  Accept Workspace Invitation
                </h2>
                <p className="card-subtitle">
                  Enter your one-time invitation token and choose a password for your account.
                </p>
              </div>

              {errorMessage && (
                <div className="auth-error-banner" role="alert">
                  <span className="error-icon" aria-hidden="true">⚠️</span>
                  <span className="error-text">{errorMessage}</span>
                </div>
              )}

              <form className="auth-form" onSubmit={handleAccept} noValidate>
                <div className="form-group">
                  <label htmlFor="invitation-token" className="form-label">
                    Invitation Token <span style={{ color: '#ef4444' }}>*</span>
                  </label>
                  <div className="input-wrapper">
                    <svg
                      className="input-icon"
                      viewBox="0 0 24 24"
                      width="18"
                      height="18"
                      aria-hidden="true"
                    >
                      <path d="M21 2l-2 2m-1-1l-3 3m-2-2l-2 2m-2-2l-3 3M3 21l8-8m0 0l-3-3 8-8 3 3-8 8z" />
                    </svg>
                    <input
                      id="invitation-token"
                      type="text"
                      className="form-input"
                      placeholder="Paste your one-time token"
                      value={token}
                      onChange={(e) => setToken(e.target.value)}
                      autoComplete="off"
                      spellCheck={false}
                      required
                    />
                  </div>
                  <span style={{ fontSize: '11.5px', color: '#64748b', marginTop: '4px' }}>
                    Shared by your workspace administrator through a secure channel.
                  </span>
                </div>

                <div className="form-group">
                  <label htmlFor="new-password" className="form-label">
                    New Password <span style={{ color: '#ef4444' }}>*</span>
                  </label>
                  <div className="input-wrapper">
                    <svg
                      className="input-icon"
                      viewBox="0 0 24 24"
                      width="18"
                      height="18"
                      aria-hidden="true"
                    >
                      <rect width="18" height="11" x="3" y="11" rx="2" ry="2" />
                      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                    </svg>
                    <input
                      id="new-password"
                      type={showPassword ? 'text' : 'password'}
                      className="form-input"
                      placeholder="At least 8 characters"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      autoComplete="new-password"
                      required
                    />
                    <button
                      type="button"
                      className="password-toggle-btn"
                      onClick={() => setShowPassword((prev) => !prev)}
                      aria-label={showPassword ? 'Hide password' : 'Show password'}
                    >
                      {showPassword ? (
                        <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
                          <path d="M9.88 9.88a3 3 0 1 0 4.24 4.24" />
                          <path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68" />
                          <path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61" />
                          <line x1="2" x2="22" y1="2" y2="22" />
                        </svg>
                      ) : (
                        <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
                          <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z" />
                          <circle cx="12" cy="12" r="3" />
                        </svg>
                      )}
                    </button>
                  </div>
                </div>

                <div className="form-group">
                  <label htmlFor="confirm-password" className="form-label">
                    Confirm Password <span style={{ color: '#ef4444' }}>*</span>
                  </label>
                  <div className="input-wrapper">
                    <svg
                      className="input-icon"
                      viewBox="0 0 24 24"
                      width="18"
                      height="18"
                      aria-hidden="true"
                    >
                      <rect width="18" height="11" x="3" y="11" rx="2" ry="2" />
                      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                    </svg>
                    <input
                      id="confirm-password"
                      type={showPassword ? 'text' : 'password'}
                      className="form-input"
                      placeholder="Re-enter password"
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      autoComplete="new-password"
                      required
                    />
                  </div>
                </div>

                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={isSubmitting}
                >
                  {isSubmitting ? (
                    <>
                      <span className="submit-spinner" aria-hidden="true" />
                      <span>Activating Account...</span>
                    </>
                  ) : (
                    <>
                      <span>Activate Account</span>
                      <span aria-hidden="true">→</span>
                    </>
                  )}
                </button>
              </form>

              <div style={{ marginTop: '20px', textAlign: 'center' }}>
                <button
                  type="button"
                  onClick={onNavigateToSignIn}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: '#2563eb',
                    fontSize: '13px',
                    fontWeight: 600,
                    cursor: 'pointer',
                    padding: 0,
                    textDecoration: 'underline',
                    fontFamily: 'inherit',
                  }}
                >
                  Already have an active account? Sign In
                </button>
              </div>
            </>
          )}

          <footer className="card-footer">
            <p className="prototype-badge">Argon2id Security • One-Time Activation</p>
          </footer>
        </section>
      </main>
    </div>
  )
}

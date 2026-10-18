import { useState, type FormEvent, type MouseEvent } from 'react'
import { IS_DEMO_MODE } from './config'
import { apiFetch } from './api'
import type { AuthUser } from './auth'
import './App.css'

interface SignInProps {
  onSignInSuccess: (user: AuthUser) => void
  onPreviewDashboard?: () => void
  onNavigateToAcceptInvitation?: () => void
}

export function SignIn({
  onSignInSuccess,
  onPreviewDashboard,
  onNavigateToAcceptInvitation,
}: SignInProps) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [infoNotice, setInfoNotice] = useState<string | null>(null)

  const handleSignIn = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setErrorMessage(null)
    setInfoNotice(null)

    const trimmedEmail = email.trim()
    if (!trimmedEmail || !password) {
      setErrorMessage('Please enter both email and password.')
      return
    }

    setIsSubmitting(true)
    try {
      const response = await apiFetch('/api/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          email: trimmedEmail,
          password: password,
        }),
      })

      if (response.ok) {
        const user: AuthUser = await response.json()
        onSignInSuccess(user)
      } else if (response.status === 401) {
        setErrorMessage('Invalid email or password.')
      } else {
        setErrorMessage('Sign in failed. Please check your credentials and try again.')
      }
    } catch {
      setErrorMessage(
        'Authentication service is unavailable. Please ensure the backend server is running.'
      )
    } finally {
      // Always clear password field after submission
      setPassword('')
      setIsSubmitting(false)
    }
  }

  const handleForgotPassword = (e: MouseEvent<HTMLButtonElement>) => {
    e.preventDefault()
    setInfoNotice(
      'Password recovery via email is not configured in this local setup. Please contact your system administrator to reset your credentials.'
    )
  }

  return (
    <div className="page-container">
      {/* Decorative ambient circular shapes matching reference */}
      <div className="bg-circle bg-circle-1" aria-hidden="true" />
      <div className="bg-circle bg-circle-2" aria-hidden="true" />
      <div className="bg-circle bg-circle-3" aria-hidden="true" />
      <div className="bg-circle bg-circle-4" aria-hidden="true" />

      <main className="auth-wrapper">
        {/* Centered Branding matching collage Screen 1 */}
        <header className="brand-header">
          <div className="brand-logo-inline">
            <div className="brand-logo-mark" aria-hidden="true">
              <span className="brand-logo-ai">AI</span>
            </div>
            <h1 className="brand-title">Resume Screener</h1>
          </div>
          <p className="brand-tagline">AI-powered resume screening for smarter hiring</p>
        </header>

        {/* Compact Sign-in Card */}
        <section className="auth-card" aria-labelledby="signin-heading">
          <div className="card-header">
            <h2 id="signin-heading" className="card-title">Welcome back</h2>
            <p className="card-subtitle">Sign in to your account</p>
          </div>

          {errorMessage && (
            <div className="auth-error-notice" role="alert" aria-live="assertive">
              <span className="notice-icon" aria-hidden="true">⚠</span>
              <span className="notice-text">{errorMessage}</span>
              <button
                type="button"
                className="notice-dismiss"
                onClick={() => setErrorMessage(null)}
                aria-label="Dismiss error"
              >
                ✕
              </button>
            </div>
          )}

          {infoNotice && (
            <div className="auth-info-notice" role="status" aria-live="polite">
              <span className="notice-icon" aria-hidden="true">ⓘ</span>
              <span className="notice-text">{infoNotice}</span>
              <button
                type="button"
                className="notice-dismiss"
                onClick={() => setInfoNotice(null)}
                aria-label="Dismiss notice"
              >
                ✕
              </button>
            </div>
          )}

          <form className="auth-form" onSubmit={handleSignIn} noValidate>
            {/* Email Field */}
            <div className="form-group">
              <label htmlFor="email" className="field-label">
                Email address
              </label>
              <input
                id="email"
                name="email"
                type="email"
                className="input-field"
                placeholder="you@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                required
              />
            </div>

            {/* Password Field */}
            <div className="form-group">
              <div className="label-row">
                <label htmlFor="password" className="field-label">
                  Password
                </label>
                <button
                  type="button"
                  className="link-button"
                  onClick={handleForgotPassword}
                >
                  Forgot password?
                </button>
              </div>

              <div className="password-input-wrapper">
                <input
                  id="password"
                  name="password"
                  type={showPassword ? 'text' : 'password'}
                  className="input-field password-field"
                  placeholder="Enter your password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  required
                />
                <button
                  type="button"
                  className="visibility-toggle"
                  onClick={() => setShowPassword((prev) => !prev)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  aria-pressed={showPassword}
                >
                  {showPassword ? (
                    <svg
                      width="18"
                      height="18"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      aria-hidden="true"
                    >
                      <path d="M9.88 9.88a3 3 0 1 0 4.24 4.24" />
                      <path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68" />
                      <path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61" />
                      <line x1="2" x2="22" y1="2" y2="22" />
                    </svg>
                  ) : (
                    <svg
                      width="18"
                      height="18"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      aria-hidden="true"
                    >
                      <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z" />
                      <circle cx="12" cy="12" r="3" />
                    </svg>
                  )}
                </button>
              </div>
            </div>

            {/* Primary Sign in button */}
            <button
              type="submit"
              className="btn btn-primary"
              disabled={isSubmitting}
            >
              {isSubmitting ? 'Signing in...' : 'Sign In'}
            </button>

            {/* Divider */}
            <div className="divider" role="separator">
              <span className="divider-text">Or continue with</span>
            </div>

            {/* Google SSO button (unconfigured external capability) */}
            <button
              type="button"
              className="btn sso-btn sso-btn-disabled"
              disabled
              title="Google SSO is not configured in this local setup. Please sign in with your email and password."
              aria-disabled="true"
            >
              <svg
                className="google-icon"
                viewBox="0 0 24 24"
                width="18"
                height="18"
                aria-hidden="true"
              >
                <path
                  fill="#4285F4"
                  d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.51h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.34z"
                />
                <path
                  fill="#34A853"
                  d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                />
                <path
                  fill="#FBBC05"
                  d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
                />
                <path
                  fill="#EA4335"
                  d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
                />
              </svg>
              <span>Google (Not configured)</span>
            </button>
          </form>

          {/* Invitation Acceptance Link */}
          {onNavigateToAcceptInvitation && (
            <div className="accept-invitation-prompt" style={{ marginTop: '16px', textAlign: 'center', fontSize: '13px', color: '#64748b' }}>
              <span>Have an invitation token? </span>
              <button
                type="button"
                className="btn-activate-account"
                onClick={onNavigateToAcceptInvitation}
                style={{
                  background: 'none',
                  border: 'none',
                  color: '#2563eb',
                  fontWeight: 600,
                  cursor: 'pointer',
                  padding: 0,
                  textDecoration: 'underline',
                  fontFamily: 'inherit',
                  fontSize: '13px',
                }}
              >
                Accept Invitation
              </button>
            </div>
          )}

          {/* Local Preview Action (Gated strictly behind VITE_DEMO_MODE) */}
          {IS_DEMO_MODE && onPreviewDashboard && (
            <div className="preview-action-box">
              <div className="preview-action-label">Developer / UI Preview (Demo Mode)</div>
              <button
                type="button"
                className="btn btn-preview"
                onClick={onPreviewDashboard}
              >
                <span>Preview Dashboard (UI Demo)</span>
                <span aria-hidden="true">→</span>
              </button>
            </div>
          )}

          <footer className="card-footer">
            <p className="auth-footer-help" style={{ fontSize: '12.5px', color: '#64748b', margin: '0 0 6px', textAlign: 'center' }}>
              Don&apos;t have an account? <span style={{ color: '#2563eb', fontWeight: 500 }}>Contact your administrator</span>
            </p>
            <p className="prototype-badge" style={{ margin: 0 }}>Local Authentication • Secure Session</p>
          </footer>
        </section>
      </main>
    </div>
  )
}

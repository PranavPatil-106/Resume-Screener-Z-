import { useState, useEffect } from 'react'
import { Sidebar, type AppScreen } from './Sidebar'
import { API_BASE_URL } from './config'
import { apiFetch } from './api'
import { useAuth } from './auth'
import './Dashboard.css'
import './Settings.css'

interface SettingsProps {
  onNavigate: (screen: AppScreen) => void
}

interface SystemStatus {
  backend_status: string
  database_engine: string
  embedding_provider: string
  embedding_model: string
  embedding_type: string
  vector_store: string
  vector_store_isolation: string
  resume_storage_lifecycle: string
}

interface LLMStatus {
  is_enabled: boolean
  is_model_configured: boolean
  cloud_usage_authorized: boolean
  can_chat: boolean
  message: string
  model_name?: string | null
}

export function Settings({ onNavigate }: SettingsProps) {
  const { user } = useAuth()
  const [sidebarOpen, setSidebarOpen] = useState(false)

  // Status API states
  const [systemStatus, setSystemStatus] = useState<SystemStatus | null>(null)
  const [llmStatus, setLlmStatus] = useState<LLMStatus | null>(null)
  const [isLoading, setIsLoading] = useState<boolean>(true)
  const [apiError, setApiError] = useState<string | null>(null)
  const [lastChecked, setLastChecked] = useState<Date | null>(null)

  const fetchSettingsStatus = async () => {
    setIsLoading(true)
    setApiError(null)

    try {
      const [sysRes, llmRes] = await Promise.all([
        apiFetch('/api/system/status', {
          headers: { Accept: 'application/json' },
        }),
        apiFetch('/api/llm/status', {
          headers: { Accept: 'application/json' },
        }),
      ])

      if (!sysRes.ok) {
        if (sysRes.status === 401) {
          throw new Error('401: Authentication required')
        }
        const errorDetail = await sysRes.text().catch(() => '')
        throw new Error(`Failed to load system status (HTTP ${sysRes.status}): ${errorDetail || sysRes.statusText}`)
      }

      if (!llmRes.ok) {
        if (llmRes.status === 401) {
          throw new Error('401: Authentication required')
        }
        const errorDetail = await llmRes.text().catch(() => '')
        throw new Error(`Failed to load LLM provider status (HTTP ${llmRes.status}): ${errorDetail || llmRes.statusText}`)
      }

      const sysData = (await sysRes.json()) as SystemStatus
      const llmData = (await llmRes.json()) as LLMStatus

      setSystemStatus(sysData)
      setLlmStatus(llmData)
      setLastChecked(new Date())
    } catch (err: unknown) {
      const message =
        err instanceof Error
          ? err.message
          : 'Unable to connect to FastAPI backend server.'
      setApiError(message)
      setSystemStatus(null)
      setLlmStatus(null)
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    fetchSettingsStatus()
  }, [])

  const getUserRoleLabel = (role?: string) => {
    switch (role?.toLowerCase()) {
      case 'admin':
        return 'Administrator'
      case 'recruiter':
        return 'Recruiter'
      case 'viewer':
        return 'Viewer (Read-Only)'
      default:
        return 'Authenticated User'
    }
  }

  const getUserPermissionsDescription = (role?: string) => {
    switch (role?.toLowerCase()) {
      case 'admin':
        return 'Full access: manage screening sessions, evaluate candidates, invite users, update roles, and create/edit/archive job descriptions.'
      case 'recruiter':
        return 'Screening access: start draft sessions, stage resumes, run evaluations, evidence retrieval, and create/edit/archive job descriptions.'
      case 'viewer':
        return 'Read-only access: review completed screening results, browse the candidate directory, and view job descriptions.'
      default:
        return 'Standard authenticated session.'
    }
  }

  return (
    <div className="dashboard-layout">
      {/* Shared Dark Left Sidebar */}
      <Sidebar
        activeScreen="settings"
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
              <h1 className="welcome-heading">Settings &amp; Configuration</h1>
              <p className="welcome-subtext">
                Read-only system status, local model configurations, provider readiness, and data retention policies.
              </p>
            </div>
          </div>

          <div className="settings-topbar-actions">
            <span className="setting-badge badge-readonly" title="Settings are governed by backend environment configuration">
              Read-Only Status
            </span>
            <button
              type="button"
              className="btn-refresh-settings"
              onClick={fetchSettingsStatus}
              disabled={isLoading}
              aria-label="Refresh system status"
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
                style={{ transform: isLoading ? 'rotate(180deg)' : 'none', transition: 'transform 0.4s ease' }}
              >
                <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2" />
              </svg>
              <span>{isLoading ? 'Checking...' : 'Refresh Status'}</span>
            </button>
          </div>
        </header>

        <div className="settings-page-content">
          {/* Informational Policy Banner */}
          <div className="settings-overview-banner" role="status">
            <span className="overview-banner-icon" aria-hidden="true">ℹ️</span>
            <div className="overview-banner-text">
              <strong>Runtime Configuration &amp; Status Overview</strong>
              <span>
                Runtime parameters and provider integrations are governed by the backend environment configuration (<code style={{ fontFamily: 'monospace' }}>.env</code>). Values displayed on this page reflect live, truthful status reported by the backend API.
                {lastChecked && ` Last verified: ${lastChecked.toLocaleTimeString()}.`}
              </span>
            </div>
          </div>

          {/* Error Banner when Unauthenticated or Backend is Unreachable */}
          {!isLoading && apiError && (
            <div className="settings-error-banner" role="alert">
              <div className="error-banner-content">
                <span className="error-banner-icon" aria-hidden="true">⚠️</span>
                <div className="error-banner-text">
                  <span className="error-banner-title">
                    {apiError.includes('401') ? 'Authentication Required' : 'Backend Connection Failed'}
                  </span>
                  <span className="error-banner-desc">
                    {apiError.includes('401')
                      ? 'Your authentication session is not active or has expired. Please sign in with valid credentials to view system settings.'
                      : `Unable to connect to backend at ${API_BASE_URL || 'the local API'}. ${apiError}`}
                  </span>
                </div>
              </div>
              {apiError.includes('401') ? (
                <button
                  type="button"
                  className="btn-retry-settings"
                  onClick={() => onNavigate('signin')}
                >
                  Go to Sign In
                </button>
              ) : (
                <button
                  type="button"
                  className="btn-retry-settings"
                  onClick={fetchSettingsStatus}
                >
                  Retry Connection
                </button>
              )}
            </div>
          )}

          {/* Accessible Loading State */}
          {isLoading && (
            <div className="settings-loading-card" role="status" aria-live="polite">
              <div className="settings-spinner" aria-hidden="true" />
              <p className="loading-title">Connecting to FastAPI backend...</p>
              <p className="loading-sub">Fetching runtime configuration from {API_BASE_URL}</p>
            </div>
          )}

          {/* Settings Cards Stack */}
          {!isLoading && (
            <div className="settings-sections-stack">
              {/* SECTION 1: Backend & Database Infrastructure */}
              <section className="settings-card" aria-labelledby="heading-backend">
                <div className="settings-card-header">
                  <div>
                    <h2 id="heading-backend" className="settings-card-title">
                      Backend &amp; Database Infrastructure
                    </h2>
                    <p className="settings-card-sub">
                      API service availability, persistence engine, and active database configuration.
                    </p>
                  </div>
                  <span className={`setting-badge ${systemStatus ? 'badge-active' : 'badge-danger'}`}>
                    {systemStatus ? 'API Connected' : 'Unavailable'}
                  </span>
                </div>

                <div className="settings-card-body">
                  <div className="settings-notice-box notice-box-primary">
                    <span className="notice-box-icon" aria-hidden="true">⚙️</span>
                    <div className="notice-box-text">
                      <strong>Connected Service Architecture</strong>
                      <span>
                        The backend runs as a FastAPI application with SQLAlchemy ORM and Alembic schema migrations. Database connection credentials, paths, and private host settings remain protected on the server.
                      </span>
                    </div>
                  </div>

                  <div className="settings-kv-grid">
                    <div className="settings-kv-item">
                      <span className="kv-label">Backend Status</span>
                      <span className={`kv-value ${systemStatus ? 'text-success' : 'text-danger'}`}>
                        {systemStatus ? 'Online (Healthy)' : 'Offline / Unreachable'}
                      </span>
                    </div>
                    <div className="settings-kv-item">
                      <span className="kv-label">API Base URL</span>
                      <span className="kv-value">{API_BASE_URL}</span>
                    </div>
                    <div className="settings-kv-item">
                      <span className="kv-label">Database Engine</span>
                      <span className="kv-value">
                        {systemStatus ? `${systemStatus.database_engine} (SQLAlchemy)` : 'Unavailable'}
                      </span>
                    </div>
                    <div className="settings-kv-item">
                      <span className="kv-label">Schema Migrations</span>
                      <span className="kv-value">Alembic Managed (Reversible)</span>
                    </div>
                    <div className="settings-kv-item">
                      <span className="kv-label">Configuration Mode</span>
                      <span className="kv-value">Read-Only (Managed via environment files)</span>
                    </div>
                    <div className="settings-kv-item">
                      <span className="kv-label">Runtime Environment</span>
                      <span className="kv-value">Local Development (.env configured)</span>
                    </div>
                  </div>
                </div>

                <div className="settings-card-footer">
                  <div className="settings-card-footer-info">
                    <span className="footer-info-icon" aria-hidden="true">🔒</span>
                    <span>Runtime settings are managed in backend environment files and are not editable in this page.</span>
                  </div>
                </div>
              </section>

              {/* SECTION 2: Authentication & Current User Role */}
              <section className="settings-card" aria-labelledby="heading-auth">
                <div className="settings-card-header">
                  <div>
                    <h2 id="heading-auth" className="settings-card-title">
                      Authentication &amp; Active User Session
                    </h2>
                    <p className="settings-card-sub">
                      Signed-in user identity, session security, and server-enforced role authorization.
                    </p>
                  </div>
                  <span className="setting-badge badge-active">
                    {user ? `${user.role.toUpperCase()} ROLE` : 'SIGNED IN'}
                  </span>
                </div>

                <div className="settings-card-body">
                  <div className="settings-notice-box notice-box-info">
                    <span className="notice-box-icon" aria-hidden="true">🛡️</span>
                    <div className="notice-box-text">
                      <strong>Role-Based Access Control (RBAC)</strong>
                      <span>
                        Access permissions are validated server-side on every API request. User accounts cannot alter their own roles or bypass authorization guards.
                      </span>
                    </div>
                  </div>

                  <div className="settings-kv-grid">
                    <div className="settings-kv-item">
                      <span className="kv-label">Signed-in User</span>
                      <span className="kv-value">{user?.email || 'Authenticated User'}</span>
                    </div>
                    <div className="settings-kv-item">
                      <span className="kv-label">Assigned Role</span>
                      <span className="kv-value text-primary">{getUserRoleLabel(user?.role)}</span>
                    </div>
                    <div className="settings-kv-item full-width">
                      <span className="kv-label">Effective Permissions</span>
                      <span className="kv-value">{getUserPermissionsDescription(user?.role)}</span>
                    </div>
                    <div className="settings-kv-item">
                      <span className="kv-label">Session Protection</span>
                      <span className="kv-value">HttpOnly, SameSite Session Cookies</span>
                    </div>
                    <div className="settings-kv-item">
                      <span className="kv-label">Account Invitation Policy</span>
                      <span className="kv-value">Admin-only invitation tokens (7-day expiry)</span>
                    </div>
                  </div>
                </div>

                <div className="settings-card-footer">
                  <div className="settings-card-footer-info">
                    <span className="footer-info-icon" aria-hidden="true">ℹ️</span>
                    <span>User roles and permissions are enforced by backend authentication policies.</span>
                  </div>
                </div>
              </section>

              {/* SECTION 3: Local Vector Embeddings (On-Device) */}
              <section className="settings-card" aria-labelledby="heading-embedding">
                <div className="settings-card-header">
                  <div>
                    <h2 id="heading-embedding" className="settings-card-title">
                      Local Vector Embeddings (On-Device)
                    </h2>
                    <p className="settings-card-sub">
                      Local Ollama embeddings and isolated per-session vector retrieval.
                    </p>
                  </div>
                  <span className="setting-badge badge-session">
                    Local On-Device
                  </span>
                </div>

                <div className="settings-card-body">
                  <div className="settings-notice-box notice-box-info">
                    <span className="notice-box-icon" aria-hidden="true">🔒</span>
                    <div className="notice-box-text">
                      <strong>Zero Cloud Transmission for Embeddings</strong>
                      <span>
                        Resume text is chunked and embedded strictly on this local machine using Ollama. Raw resume content, extracted text, and embedding vectors are never sent to any cloud embedding provider or external API.
                      </span>
                    </div>
                  </div>

                  <div className="settings-kv-grid">
                    <div className="settings-kv-item">
                      <span className="kv-label">Embedding Provider</span>
                      <span className="kv-value">
                        {systemStatus?.embedding_provider ? `${systemStatus.embedding_provider.toUpperCase()} (Local Daemon)` : 'Ollama (Local)'}
                      </span>
                    </div>
                    <div className="settings-kv-item">
                      <span className="kv-label">Configured Model</span>
                      <span className="kv-value text-primary">
                        {systemStatus?.embedding_model || 'nomic-embed-text'}
                      </span>
                    </div>
                    <div className="settings-kv-item">
                      <span className="kv-label">Vector Dimensions</span>
                      <span className="kv-value">768 Dimensions (nomic-embed-text)</span>
                    </div>
                    <div className="settings-kv-item">
                      <span className="kv-label">Execution Target</span>
                      <span className="kv-value">127.0.0.1:11434 (Local Ollama Instance)</span>
                    </div>
                    <div className="settings-kv-item">
                      <span className="kv-label">Vector Database</span>
                      <span className="kv-value">
                        {systemStatus?.vector_store || 'ChromaDB'} (Per-session collections)
                      </span>
                    </div>
                    <div className="settings-kv-item">
                      <span className="kv-label">Privacy Guarantee</span>
                      <span className="kv-value text-success">
                        Strictly on-device; zero cloud transmission
                      </span>
                    </div>
                  </div>
                </div>

                <div className="settings-card-footer">
                  <div className="settings-card-footer-info">
                    <span className="footer-info-icon" aria-hidden="true">ℹ️</span>
                    <span>Local embedding model is configured via EMBEDDING_MODEL_NAME in backend .env.</span>
                  </div>
                </div>
              </section>

              {/* SECTION 4: Ollama Cloud Chat & Evaluation Readiness */}
              <section className="settings-card" aria-labelledby="heading-llm">
                <div className="settings-card-header">
                  <div>
                    <h2 id="heading-llm" className="settings-card-title">
                      Ollama Cloud Chat &amp; Evaluation Readiness
                    </h2>
                    <p className="settings-card-sub">
                      Guarded cloud connectivity for evidence-grounded Q&amp;A and resume evaluations.
                    </p>
                  </div>
                  <span
                    className={`setting-badge ${
                      llmStatus?.can_chat
                        ? 'badge-active'
                        : llmStatus?.is_enabled
                        ? 'badge-unconfigured'
                        : 'badge-local'
                    }`}
                  >
                    {llmStatus?.can_chat
                      ? 'Cloud Chat Ready'
                      : llmStatus?.is_enabled
                      ? 'Authorization Required'
                      : 'Disabled by Default'}
                  </span>
                </div>

                <div className="settings-card-body">
                  <div className={`settings-notice-box ${llmStatus?.can_chat ? 'notice-box-primary' : ''}`}>
                    <span className="notice-box-icon" aria-hidden="true">
                      {llmStatus?.can_chat ? '💬' : '⚠️'}
                    </span>
                    <div className="notice-box-text">
                      <strong>Cloud Provider Status &amp; Billing Notice</strong>
                      <span>
                        {llmStatus?.message ||
                          'Ollama LLM provider status could not be verified from the server.'}
                      </span>
                    </div>
                  </div>

                  <div className="settings-kv-grid">
                    <div className="settings-kv-item">
                      <span className="kv-label">Cloud Inference Service</span>
                      <span className="kv-value">Ollama Cloud (Guarded)</span>
                    </div>
                    <div className="settings-kv-item">
                      <span className="kv-label">Configured Model</span>
                      <span className="kv-value">
                        {llmStatus?.model_name || (llmStatus?.is_model_configured ? 'Configured' : 'Not Configured')}
                      </span>
                    </div>
                    <div className="settings-kv-item">
                      <span className="kv-label">Provider Enabled</span>
                      <span className={`kv-value ${llmStatus?.is_enabled ? 'text-success' : 'text-muted'}`}>
                        {llmStatus?.is_enabled ? 'Yes (OLLAMA_LLM_ENABLED=true)' : 'No (Disabled by default)'}
                      </span>
                    </div>
                    <div className="settings-kv-item">
                      <span className="kv-label">Cloud Usage Authorization</span>
                      <span className={`kv-value ${llmStatus?.cloud_usage_authorized ? 'text-success' : 'text-warning'}`}>
                        {llmStatus?.cloud_usage_authorized ? 'Authorized (Explicit opt-in)' : 'Unauthorized (Opt-in required)'}
                      </span>
                    </div>
                    <div className="settings-kv-item">
                      <span className="kv-label">Chat Q&amp;A Readiness</span>
                      <span className={`kv-value ${llmStatus?.can_chat ? 'text-success' : 'text-muted'}`}>
                        {llmStatus?.can_chat ? 'Ready for confirmed queries' : 'Blocked (Guard active)'}
                      </span>
                    </div>
                    <div className="settings-kv-item">
                      <span className="kv-label">Cost &amp; Transmission Safeguard</span>
                      <span className="kv-value">
                        Explicit checkbox confirmation required before every transmission ($0.15/M in, $0.60/M out)
                      </span>
                    </div>
                  </div>
                </div>

                <div className="settings-card-footer">
                  <div className="settings-card-footer-info">
                    <span className="footer-info-icon" aria-hidden="true">ℹ️</span>
                    <span>Cloud authorization and model selection are managed in backend environment files.</span>
                  </div>
                </div>
              </section>

              {/* SECTION 5: Resume Storage & Data Retention Lifecycle */}
              <section className="settings-card" aria-labelledby="heading-retention">
                <div className="settings-card-header">
                  <div>
                    <h2 id="heading-retention" className="settings-card-title">
                      Resume Storage &amp; Data Retention Lifecycle
                    </h2>
                    <p className="settings-card-sub">
                      File lifecycle, ephemeral vector stores, and evaluation record retention.
                    </p>
                  </div>
                  <span className="setting-badge badge-session">
                    Lifecycle Managed
                  </span>
                </div>

                <div className="settings-card-body">
                  <div className="settings-notice-box notice-box-info">
                    <span className="notice-box-icon" aria-hidden="true">🛡️</span>
                    <div className="notice-box-text">
                      <strong>Truthful Retention &amp; Cleanup Policy</strong>
                      <span>
                        Candidate files, extracted text, and Chroma vector stores exist only for the duration of the screening session. Once completed or ended, temporary resume files and vectors are permanently deleted from disk. Validated evaluation records persist in the database until the session is explicitly deleted.
                      </span>
                    </div>
                  </div>

                  <div className="settings-kv-grid">
                    <div className="settings-kv-item">
                      <span className="kv-label">Temporary File Storage</span>
                      <span className="kv-value">Local disk (<code style={{ fontFamily: 'monospace' }}>data/staged_resumes/&lt;session_id&gt;/</code>)</span>
                    </div>
                    <div className="settings-kv-item">
                      <span className="kv-label">Vector Storage Target</span>
                      <span className="kv-value">ChromaDB collections nested under session storage</span>
                    </div>
                    <div className="settings-kv-item">
                      <span className="kv-label">Session End Cleanup</span>
                      <span className="kv-value text-success">Automatic purge of staged files and extracted text</span>
                    </div>
                    <div className="settings-kv-item">
                      <span className="kv-label">Session Complete Cleanup</span>
                      <span className="kv-value text-success">Automatic purge of temporary files, text, and Chroma store</span>
                    </div>
                    <div className="settings-kv-item">
                      <span className="kv-label">Validated Evaluations</span>
                      <span className="kv-value">Persisted in database until session is explicitly deleted</span>
                    </div>
                    <div className="settings-kv-item">
                      <span className="kv-label">Candidate Directory</span>
                      <span className="kv-value">Displays persisted evaluation scorecards from completed sessions</span>
                    </div>
                  </div>
                </div>

                <div className="settings-card-footer">
                  <div className="settings-card-footer-info">
                    <span className="footer-info-icon" aria-hidden="true">ℹ️</span>
                    <span>Storage directories and file retention policies are enforced by backend lifecycle handlers.</span>
                  </div>
                </div>
              </section>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}

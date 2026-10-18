import { useState, useEffect } from 'react'
import { SignIn } from './SignIn'
import { AcceptInvitation } from './AcceptInvitation'
import { Dashboard } from './Dashboard'
import { JobDescriptions } from './JobDescriptions'
import { ScreeningSessions } from './ScreeningSessions'
import { Candidates } from './Candidates'
import { Users } from './Users'
import { Settings } from './Settings'
import { NewScreeningWizard, type DraftSessionDetail } from './NewScreeningWizard'
import { ScreeningWorkspace } from './ScreeningWorkspace'
import { AuthProvider, type AuthUser, isAdminRole, isPrivilegedRole, isViewerRole } from './auth'
import { IS_DEMO_MODE } from './config'
import { apiFetch } from './api'
import type { AppScreen } from './Sidebar'

export default function App() {
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null)
  const [isCheckingAuth, setIsCheckingAuth] = useState(true)
  const [currentScreen, setCurrentScreen] = useState<AppScreen>('signin')
  const [previousScreen, setPreviousScreen] = useState<
    'dashboard' | 'jobs' | 'sessions' | 'candidates' | 'users' | 'settings'
  >('dashboard')
  const [selectedJdIdForScreening, setSelectedJdIdForScreening] = useState<string | null>(null)
  const [resumedSessionData, setResumedSessionData] = useState<DraftSessionDetail | null>(null)
  const [workspaceSessionId, setWorkspaceSessionId] = useState<string | null>(null)

  const isAdmin = isAdminRole(currentUser?.role)
  const isPrivileged = isPrivilegedRole(currentUser?.role)
  const isViewer = isViewerRole(currentUser?.role)

  // Verify existing session on initial application mount
  useEffect(() => {
    let isMounted = true

    async function checkSession() {
      try {
        const response = await apiFetch('/api/auth/me')

        if (response.ok) {
          const user: AuthUser = await response.json()
          if (isMounted) {
            setCurrentUser(user)
            if (isPrivilegedRole(user.role)) {
              setCurrentScreen('dashboard')
            } else {
              // Viewers land on Job Descriptions screen
              setCurrentScreen('jobs')
            }
          }
        } else {
          // Treat 401 and other non-200 responses as signed out
          if (isMounted) {
            setCurrentUser(null)
            setCurrentScreen('signin')
          }
        }
      } catch {
        // Backend unavailable or network error -> treat as signed out
        if (isMounted) {
          setCurrentUser(null)
          setCurrentScreen('signin')
        }
      } finally {
        if (isMounted) {
          setIsCheckingAuth(false)
        }
      }
    }

    checkSession()

    return () => {
      isMounted = false
    }
  }, [])

  const handleSignInSuccess = (user: AuthUser) => {
    setCurrentUser(user)
    if (isPrivilegedRole(user.role)) {
      setCurrentScreen('dashboard')
    } else {
      // Viewers land on Job Descriptions screen
      setCurrentScreen('jobs')
    }
  }

  const handleLogout = async () => {
    try {
      await apiFetch('/api/auth/logout', {
        method: 'POST',
      })
    } catch (err) {
      console.error('Logout error:', err)
    } finally {
      setCurrentUser(null)
      setCurrentScreen('signin')
    }
  }

  const handleNavigate = (screen: AppScreen) => {
    setWorkspaceSessionId(null)
    // If not authenticated and demo mode is not enabled, restrict navigation to signin or accept-invitation
    if (!currentUser && !IS_DEMO_MODE && screen !== 'signin' && screen !== 'accept-invitation') {
      setCurrentScreen('signin')
      return
    }

    // Role-based gating: Viewers may only navigate to 'jobs', 'sessions', or 'signin'
    if (currentUser && !isPrivileged) {
      if (screen !== 'jobs' && screen !== 'sessions' && screen !== 'signin') {
        setCurrentScreen('jobs')
        return
      }
    }

    // Role-based gating: Only admins may navigate to 'users'
    if (currentUser && screen === 'users' && !isAdmin) {
      setCurrentScreen(isPrivileged ? 'dashboard' : 'jobs')
      return
    }

    if (screen === 'new-screening') {
      if (
        currentScreen === 'dashboard' ||
        currentScreen === 'jobs' ||
        currentScreen === 'sessions' ||
        currentScreen === 'candidates' ||
        currentScreen === 'users' ||
        currentScreen === 'settings'
      ) {
        setPreviousScreen(currentScreen)
      }
      setSelectedJdIdForScreening(null)
      setResumedSessionData(null)
    }
    setCurrentScreen(screen)
  }

  const handleUseJdInScreening = (jdId: string) => {
    if (!isPrivileged) return // Viewers are not permitted to start screening sessions
    setPreviousScreen('jobs')
    setSelectedJdIdForScreening(jdId)
    setResumedSessionData(null)
    setCurrentScreen('new-screening')
  }

  const handleResumeDraft = (draft: DraftSessionDetail) => {
    if (!isPrivileged) return
    setPreviousScreen('sessions')
    setSelectedJdIdForScreening(draft.job_description?.id || draft.job_description_id)
    setResumedSessionData(draft)
    setCurrentScreen('new-screening')
  }

  const handleBackFromWizard = () => {
    setCurrentScreen(previousScreen)
    setSelectedJdIdForScreening(null)
    setResumedSessionData(null)
  }

  // Display clean loading indicator while checking session
  if (isCheckingAuth) {
    return (
      <div className="auth-loading-container">
        <div className="auth-loading-card">
          <div className="auth-loading-spinner" aria-hidden="true" />
          <h2 className="auth-loading-title">AI Resume Screener</h2>
          <p className="auth-loading-text">Verifying session...</p>
        </div>
      </div>
    )
  }

  const authContextValue = {
    user: currentUser,
    loading: isCheckingAuth,
    isAdmin,
    isPrivileged,
    isViewer,
    setUser: setCurrentUser,
    logout: handleLogout,
  }

  // Compute effective screen: enforce signin if unauth (unless on accept-invitation), enforce jobs if viewer is on disallowed screen, enforce dashboard/jobs if non-admin on users
  let effectiveScreen: AppScreen = currentScreen
  if (!currentUser && !IS_DEMO_MODE) {
    if (effectiveScreen !== 'signin' && effectiveScreen !== 'accept-invitation') {
      effectiveScreen = 'signin'
    }
  } else if (currentUser && !isPrivileged) {
    if (effectiveScreen !== 'jobs' && effectiveScreen !== 'sessions' && effectiveScreen !== 'signin') {
      effectiveScreen = 'jobs'
    }
  } else if (currentUser && effectiveScreen === 'users' && !isAdmin) {
    effectiveScreen = isPrivileged ? 'dashboard' : 'jobs'
  }

  return (
    <AuthProvider value={authContextValue}>
      {effectiveScreen === 'signin' && (
        <SignIn
          onSignInSuccess={handleSignInSuccess}
          onPreviewDashboard={
            IS_DEMO_MODE ? () => handleNavigate('dashboard') : undefined
          }
          onNavigateToAcceptInvitation={() => handleNavigate('accept-invitation')}
        />
      )}

      {effectiveScreen === 'accept-invitation' && (
        <AcceptInvitation onNavigateToSignIn={() => handleNavigate('signin')} />
      )}

      {effectiveScreen === 'dashboard' && !workspaceSessionId && (
        <Dashboard onNavigate={handleNavigate} onOpenSession={setWorkspaceSessionId} />
      )}

      {workspaceSessionId && effectiveScreen === 'dashboard' && (
        <ScreeningWorkspace
          sessionId={workspaceSessionId}
          initialView="results"
          onNavigate={handleNavigate}
          onExit={() => setWorkspaceSessionId(null)}
        />
      )}

      {effectiveScreen === 'jobs' && (
        <JobDescriptions
          onNavigate={handleNavigate}
          onUseJd={handleUseJdInScreening}
        />
      )}

      {effectiveScreen === 'sessions' && (
        <ScreeningSessions
          onNavigate={handleNavigate}
          onNewSession={() => handleNavigate('new-screening')}
          onResumeDraft={handleResumeDraft}
        />
      )}

      {effectiveScreen === 'candidates' && (
        <Candidates onNavigate={handleNavigate} />
      )}

      {effectiveScreen === 'users' && (
        <Users onNavigate={handleNavigate} />
      )}

      {effectiveScreen === 'settings' && (
        <Settings onNavigate={handleNavigate} />
      )}

      {effectiveScreen === 'new-screening' && (
        <NewScreeningWizard
          initialJdId={selectedJdIdForScreening}
          initialSessionData={resumedSessionData}
          onNavigate={handleNavigate}
          onBack={handleBackFromWizard}
        />
      )}
    </AuthProvider>
  )
}

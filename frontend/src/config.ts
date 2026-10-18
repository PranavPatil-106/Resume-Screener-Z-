// Centralized API and runtime configuration for frontend

export const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL || ''

// Demo mode allows previewing the dashboard UI without backend authentication.
// Defaults strictly to false for production and secure local operation.
export const IS_DEMO_MODE: boolean =
  import.meta.env.VITE_DEMO_MODE === 'true'

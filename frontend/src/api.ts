import { API_BASE_URL } from './config'

export interface ApiFetchOptions extends RequestInit {
  /**
   * Request headers dictionary or Headers instance.
   */
  headers?: HeadersInit
}

/**
 * Shared API request helper for backend calls.
 * - Resolves relative endpoint paths against the centralized API_BASE_URL.
 * - Defaults credentials to "include" to transmit HTTP-only authentication cookies.
 * - Preserves FormData uploads without setting a manual multipart Content-Type header.
 * - Never logs request bodies, passwords, resume text, cookies, or response credentials.
 */
export async function apiFetch(
  endpoint: string,
  options: ApiFetchOptions = {}
): Promise<Response> {
  const url =
    endpoint.startsWith('http://') || endpoint.startsWith('https://')
      ? endpoint
      : `${API_BASE_URL}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`

  const headers = new Headers(options.headers || {})

  // Preserve FormData uploads: do not manually override boundary-defined multipart Content-Type
  if (options.body instanceof FormData) {
    if (headers.has('Content-Type')) {
      headers.delete('Content-Type')
    }
  }

  const finalOptions: RequestInit = {
    ...options,
    credentials: options.credentials ?? 'include',
    headers,
  }

  return fetch(url, finalOptions)
}

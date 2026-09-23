import axios from 'axios'

/**
 * Centralized Axios instance for all backend API calls.
 *
 * `baseURL` is intentionally left as an empty string so requests use
 * relative paths (e.g. `apiClient.get('/api/health')`). In development,
 * Vite's dev-server proxy (see vite.config.js) forwards `/api/*` to the
 * local FastAPI backend. In production, the frontend and backend are
 * deployed separately (Vercel + Render), so VITE_API_BASE_URL is used
 * instead when provided.
 *
 * No domain-specific API methods are defined here yet. Feature-specific
 * calls (auth, statement upload, analytics, scenarios, risk, document
 * upload/Q&A, AI insights) will be added as their own modules in later
 * phases.
 */
const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
})

export default apiClient

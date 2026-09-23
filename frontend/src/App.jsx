import { useEffect, useState } from 'react'
import apiClient from './services/apiClient'

/**
 * Root application component.
 *
 * This is a bootstrapping shell, not the product UI. It exists to prove
 * the full stack is wired correctly end-to-end — React -> FastAPI ->
 * SQLAlchemy -> SQLite, plus the local storage directories the RAG
 * feature will use — by calling the backend's `/api/health` endpoint on
 * mount and rendering the result.
 *
 * Pages, routing (react-router-dom), and the real product UI (KPI cards,
 * health score gauge, trend charts, ratio table, scenario simulator,
 * Base-vs-Scenario comparison, ML risk result, document upload + Q&A
 * panel, AI executive summary) are introduced in later phases.
 */
function App() {
  const [health, setHealth] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let isMounted = true

    apiClient
      .get('/api/health')
      .then((response) => {
        if (isMounted) {
          setHealth(response.data)
          setLoading(false)
        }
      })
      .catch((err) => {
        if (isMounted) {
          setError(err.message || 'Failed to reach backend service.')
          setLoading(false)
        }
      })

    return () => {
      isMounted = false
    }
  }, [])

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-lg rounded-2xl border border-gray-200 bg-white p-8 shadow-sm">
        <h1 className="text-2xl font-semibold text-brand-700">FinSight AI</h1>
        <p className="mt-1 text-sm text-gray-500">
          Financial Health & Business Impact Analytics — infrastructure scaffold
        </p>

        <div className="mt-6 rounded-xl bg-gray-50 p-4">
          <h2 className="text-sm font-medium text-gray-700">
            Backend connectivity check
          </h2>

          {loading && (
            <p className="mt-2 text-sm text-gray-500">Checking backend status...</p>
          )}

          {!loading && error && (
            <p className="mt-2 text-sm text-red-600">
              Could not reach the backend: {error}
            </p>
          )}

          {!loading && health && (
            <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
              <dt className="text-gray-500">Status</dt>
              <dd className="font-medium text-gray-900">{health.status}</dd>

              <dt className="text-gray-500">Service</dt>
              <dd className="font-medium text-gray-900">{health.service}</dd>

              <dt className="text-gray-500">Version</dt>
              <dd className="font-medium text-gray-900">{health.version}</dd>

              <dt className="text-gray-500">Environment</dt>
              <dd className="font-medium text-gray-900">{health.environment}</dd>

              <dt className="text-gray-500">Database</dt>
              <dd className="font-medium text-gray-900">{health.database}</dd>

              <dt className="text-gray-500">Document storage</dt>
              <dd className="font-medium text-gray-900">
                {health.storage?.documents_dir}
              </dd>

              <dt className="text-gray-500">FAISS index storage</dt>
              <dd className="font-medium text-gray-900">
                {health.storage?.faiss_index_dir}
              </dd>
            </dl>
          )}
        </div>

        <p className="mt-6 text-xs text-gray-400">
          This screen will be replaced by the authentication and dashboard
          UI in later phases.
        </p>
      </div>
    </div>
  )
}

export default App

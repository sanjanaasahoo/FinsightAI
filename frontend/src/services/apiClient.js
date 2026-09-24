import axios from 'axios'

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json',
  },
})

export const listCompanies = () => apiClient.get('/api/companies')

export const getCompanyStatements = (companyId) =>
  apiClient.get(`/api/companies/${companyId}/statements`)

export const runAnalysis = (statementId) =>
  apiClient.post(`/api/analyses/${statementId}`)

export const getCompanyTrend = (companyId) =>
  apiClient.get(`/api/analyses/company/${companyId}/trend`)

export const assessRisk = (statementId, scenarioRunId) =>
  apiClient.post('/api/risk/assess', {
    statement_id: Number(statementId),
    scenario_run_id: scenarioRunId ? Number(scenarioRunId) : null,
  })

export const listScenarioTypes = () => apiClient.get('/api/scenarios/types')

export const runScenario = (statementId, scenarioType) => {
  const payload =
    scenarioType === 'combined_stress'
      ? { statement_id: Number(statementId) }
      : { statement_id: Number(statementId), scenario_type: scenarioType }

  return apiClient.post(
    scenarioType === 'combined_stress'
      ? '/api/scenarios/stress-test'
      : '/api/scenarios/simulate',
    payload,
  )
}

export const getInsightSummary = (statementId, scenarioRunId) =>
  apiClient.post('/api/insights/summary', {
    statement_id: Number(statementId),
    scenario_run_id: scenarioRunId ? Number(scenarioRunId) : null,
  })

export const askInsightQuestion = (statementId, question, scenarioRunId) =>
  apiClient.post('/api/insights/ask', {
    statement_id: Number(statementId),
    scenario_run_id: scenarioRunId ? Number(scenarioRunId) : null,
    question,
  })

export default apiClient

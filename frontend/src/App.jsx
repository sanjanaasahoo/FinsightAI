/* eslint-disable react/prop-types */
import { useEffect, useMemo, useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  askInsightQuestion,
  assessRisk,
  getCompanyStatements,
  getCompanyTrend,
  getInsightSummary,
  listCompanies,
  listScenarioTypes,
  runAnalysis,
  runScenario,
} from './services/apiClient'

const TREND_OPTIONS = [
  { key: 'revenue', label: 'Revenue', type: 'currency' },
  { key: 'operating_margin', label: 'Operating Margin', type: 'percent' },
  { key: 'net_margin', label: 'Net Margin', type: 'percent' },
]

const IMPACT_METRICS = [
  { key: 'revenue', label: 'Revenue', type: 'currency', source: 'line_item' },
  { key: 'net_income', label: 'Net Income', type: 'currency', source: 'line_item' },
  {
    key: 'operating_cash_flow',
    label: 'Operating Cash Flow',
    type: 'currency',
    source: 'line_item',
  },
  { key: 'health_score', label: 'Health Score', type: 'score', source: 'score' },
]

const KPI_CARDS = [
  { key: 'gross_margin', label: 'Gross Margin', type: 'percent' },
  { key: 'operating_margin', label: 'Operating Margin', type: 'percent' },
  { key: 'net_margin', label: 'Net Margin', type: 'percent' },
  { key: 'current_ratio', label: 'Current Ratio', type: 'number' },
  { key: 'debt_to_equity', label: 'Debt / Equity', type: 'number' },
  { key: 'operating_cash_flow_margin', label: 'OCF Margin', type: 'percent' },
]

const RISK_COLORS = {
  Low: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  Medium: 'bg-amber-100 text-amber-800 border-amber-200',
  High: 'bg-rose-100 text-rose-800 border-rose-200',
}

function App() {
  const [companies, setCompanies] = useState([])
  const [selectedCompanyId, setSelectedCompanyId] = useState('')
  const [statements, setStatements] = useState([])
  const [selectedStatementId, setSelectedStatementId] = useState('')
  const [analysis, setAnalysis] = useState(null)
  const [risk, setRisk] = useState(null)
  const [trend, setTrend] = useState(null)
  const [scenarioTypes, setScenarioTypes] = useState([])
  const [selectedScenario, setSelectedScenario] = useState('')
  const [scenarioRun, setScenarioRun] = useState(null)
  const [insight, setInsight] = useState(null)
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState(null)
  const [trendMetric, setTrendMetric] = useState('revenue')
  const [status, setStatus] = useState({
    boot: 'loading',
    company: 'idle',
    analysis: 'idle',
    scenario: 'idle',
    insight: 'idle',
    ask: 'idle',
  })
  const [errors, setErrors] = useState({})

  useEffect(() => {
    let active = true

    Promise.all([listCompanies(), listScenarioTypes()])
      .then(([companyResponse, scenarioResponse]) => {
        if (!active) return
        const nextCompanies = companyResponse.data || []
        const nextScenarioTypes = scenarioResponse.data || []
        setCompanies(nextCompanies)
        setScenarioTypes(nextScenarioTypes)
        setSelectedCompanyId(nextCompanies[0]?.id ? String(nextCompanies[0].id) : '')
        setSelectedScenario(nextScenarioTypes[0]?.scenario_type || '')
        setStatus((current) => ({ ...current, boot: 'success' }))
      })
      .catch((error) => {
        if (!active) return
        setErrors((current) => ({ ...current, boot: toErrorMessage(error) }))
        setStatus((current) => ({ ...current, boot: 'error' }))
      })

    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (!selectedCompanyId) return
    let active = true

    setStatus((current) => ({ ...current, company: 'loading' }))
    setErrors((current) => ({ ...current, company: null }))
    setAnalysis(null)
    setRisk(null)
    setTrend(null)
    setScenarioRun(null)
    setInsight(null)
    setAnswer(null)
    setStatus((current) => ({ ...current, insight: 'idle', ask: 'idle' }))

    Promise.all([
      getCompanyStatements(selectedCompanyId),
      getCompanyTrend(selectedCompanyId),
    ])
      .then(([statementResponse, trendResponse]) => {
        if (!active) return
        const nextStatements = statementResponse.data || []
        setStatements(nextStatements)
        setTrend(trendResponse.data?.trend || null)
        setSelectedStatementId(
          nextStatements[nextStatements.length - 1]?.id
            ? String(nextStatements[nextStatements.length - 1].id)
            : '',
        )
        setStatus((current) => ({ ...current, company: 'success' }))
      })
      .catch((error) => {
        if (!active) return
        setStatements([])
        setSelectedStatementId('')
        setErrors((current) => ({ ...current, company: toErrorMessage(error) }))
        setStatus((current) => ({ ...current, company: 'error' }))
      })

    return () => {
      active = false
    }
  }, [selectedCompanyId])

  useEffect(() => {
    if (!selectedStatementId) return
    let active = true

    setStatus((current) => ({ ...current, analysis: 'loading' }))
    setErrors((current) => ({ ...current, analysis: null }))
    setScenarioRun(null)
    setInsight(null)
    setAnswer(null)
    setStatus((current) => ({ ...current, insight: 'idle', ask: 'idle' }))

    Promise.all([runAnalysis(selectedStatementId), assessRisk(selectedStatementId)])
      .then(([analysisResponse, riskResponse]) => {
        if (!active) return
        setAnalysis(analysisResponse.data)
        setRisk(riskResponse.data)
        setStatus((current) => ({ ...current, analysis: 'success' }))
      })
      .catch((error) => {
        if (!active) return
        setErrors((current) => ({ ...current, analysis: toErrorMessage(error) }))
        setStatus((current) => ({ ...current, analysis: 'error' }))
      })

    return () => {
      active = false
    }
  }, [selectedStatementId])

  useEffect(() => {
    if (!selectedStatementId || !selectedScenario) return
    let active = true

    setStatus((current) => ({ ...current, scenario: 'loading' }))
    setErrors((current) => ({ ...current, scenario: null }))
    setScenarioRun(null)
    setInsight(null)
    setAnswer(null)
    setStatus((current) => ({ ...current, insight: 'idle', ask: 'idle' }))

    runScenario(selectedStatementId, selectedScenario)
      .then((response) => {
        if (!active) return
        setScenarioRun(response.data)
        setStatus((current) => ({ ...current, scenario: 'success' }))
      })
      .catch((error) => {
        if (!active) return
        setErrors((current) => ({ ...current, scenario: toErrorMessage(error) }))
        setStatus((current) => ({ ...current, scenario: 'error' }))
      })

    return () => {
      active = false
    }
  }, [selectedScenario, selectedStatementId])

  const selectedCompany = useMemo(
    () => companies.find((company) => String(company.id) === selectedCompanyId),
    [companies, selectedCompanyId],
  )

  const selectedStatement = useMemo(
    () => statements.find((statement) => String(statement.id) === selectedStatementId),
    [selectedStatementId, statements],
  )

  const selectedTrend = TREND_OPTIONS.find((option) => option.key === trendMetric)
  const trendData = useMemo(() => {
    const series = trend?.[trendMetric]?.series || []
    return series.map((point) => ({
      period: point.period_label,
      value: point.value,
    }))
  }, [trend, trendMetric])

  const comparisonData = useMemo(() => {
    if (!scenarioRun?.impact_json) return []
    return IMPACT_METRICS.map((metric) => {
      if (metric.source === 'score') {
        return {
          metric: metric.label,
          base: scenarioRun.health_score_base,
          scenario: scenarioRun.health_score_scenario,
        }
      }

      const comparison = scenarioRun.impact_json.line_item_comparison?.[metric.key]
      return {
        metric: metric.label,
        base: comparison?.base ?? null,
        scenario: comparison?.scenario ?? null,
      }
    })
  }, [scenarioRun])

  const riskDriverData = useMemo(() => {
    const drivers = risk?.feature_importance_json || []
    return drivers.slice(0, 6).map((driver) => ({
      name: formatLabel(driver.feature || driver.metric || 'Driver'),
      importance: Math.abs(Number(driver.importance ?? driver.value ?? 0)),
    }))
  }, [risk])

  const handleAsk = (event) => {
    event.preventDefault()
    if (!question.trim() || !selectedStatementId) return

    setStatus((current) => ({ ...current, ask: 'loading' }))
    setErrors((current) => ({ ...current, ask: null }))
    setAnswer(null)

    askInsightQuestion(selectedStatementId, question.trim(), scenarioRun?.id)
      .then((response) => {
        setAnswer(response.data)
        setStatus((current) => ({ ...current, ask: 'success' }))
      })
      .catch((error) => {
        setErrors((current) => ({ ...current, ask: toErrorMessage(error) }))
        setStatus((current) => ({ ...current, ask: 'error' }))
      })
  }

  const handleGenerateInsight = () => {
    if (!selectedStatementId) return

    setStatus((current) => ({ ...current, insight: 'loading' }))
    setErrors((current) => ({ ...current, insight: null }))
    setInsight(null)

    getInsightSummary(selectedStatementId, scenarioRun?.id)
      .then((response) => {
        setInsight(response.data)
        setStatus((current) => ({ ...current, insight: 'success' }))
      })
      .catch((error) => {
        setErrors((current) => ({ ...current, insight: toErrorMessage(error) }))
        setStatus((current) => ({ ...current, insight: 'error' }))
      })
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-950">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-5 sm:px-6 lg:px-8">
          <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
            <div>
              <p className="text-sm font-medium text-teal-700">FinSight AI</p>
              <h1 className="mt-1 text-3xl font-semibold tracking-tight">
                Financial Analytics Dashboard
              </h1>
              <p className="mt-2 max-w-2xl text-sm text-slate-500">
                Backend-powered health scoring, risk classification, scenario impact,
                and Gemini insights.
              </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <SelectField
                label="Company"
                value={selectedCompanyId}
                onChange={setSelectedCompanyId}
                disabled={status.boot === 'loading' || companies.length === 0}
                options={companies.map((company) => ({
                  value: String(company.id),
                  label: company.name,
                }))}
              />
              <SelectField
                label="Statement"
                value={selectedStatementId}
                onChange={setSelectedStatementId}
                disabled={status.company === 'loading' || statements.length === 0}
                options={statements.map((statement) => ({
                  value: String(statement.id),
                  label: statement.period_label,
                }))}
              />
            </div>
          </div>
          {status.boot === 'error' && <ErrorBanner message={errors.boot} />}
          {companies.length === 0 && status.boot === 'success' && (
            <EmptyState message="No companies found. Upload or seed backend data first." />
          )}
        </div>
      </header>

      <main className="mx-auto grid max-w-7xl gap-6 px-4 py-6 sm:px-6 lg:px-8">
        <section className="grid gap-6" aria-labelledby="overview-heading">
          <SectionTitle
            eyebrow="Overview"
            title={selectedCompany?.name || 'Company overview'}
            description={
              selectedStatement
                ? `${selectedStatement.period_label} · ${selectedCompany?.sector || 'Sector unavailable'}`
                : 'Choose a company and statement to begin.'
            }
          />

          {status.company === 'loading' || status.analysis === 'loading' ? (
            <LoadingPanel message="Loading financial analysis..." />
          ) : status.company === 'error' || status.analysis === 'error' ? (
            <ErrorPanel message={errors.company || errors.analysis} />
          ) : !analysis ? (
            <EmptyState message="No analysis available for the selected statement." />
          ) : (
            <>
              <div className="grid gap-4 lg:grid-cols-[1fr_1fr_2fr]">
                <HealthScoreCard score={analysis.health_score} />
                <RiskCard risk={risk} />
                <KpiGrid kpis={analysis.kpi_json} />
              </div>

              <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
                <TrendSummary trend={trend} />
                <ChartPanel
                  title="Historical Trend"
                  control={
                    <div className="flex rounded-md border border-slate-200 bg-white p-1">
                      {TREND_OPTIONS.map((option) => (
                        <button
                          key={option.key}
                          type="button"
                          onClick={() => setTrendMetric(option.key)}
                          className={`rounded px-3 py-1.5 text-xs font-medium transition ${
                            trendMetric === option.key
                              ? 'bg-slate-900 text-white'
                              : 'text-slate-600 hover:bg-slate-100'
                          }`}
                        >
                          {option.label}
                        </button>
                      ))}
                    </div>
                  }
                >
                  {trendData.length === 0 ? (
                    <EmptyState message="Trend data is not available for this company." />
                  ) : (
                    <ResponsiveContainer width="100%" height={300}>
                      <LineChart data={trendData} margin={{ left: 4, right: 16 }}>
                        <CartesianGrid stroke="#e2e8f0" strokeDasharray="4 4" />
                        <XAxis dataKey="period" tick={{ fill: '#64748b', fontSize: 12 }} />
                        <YAxis
                          tick={{ fill: '#64748b', fontSize: 12 }}
                          tickFormatter={(value) => formatChartValue(value, selectedTrend.type)}
                        />
                        <Tooltip
                          formatter={(value) => formatValue(value, selectedTrend.type)}
                          labelClassName="font-medium"
                        />
                        <Line
                          type="monotone"
                          dataKey="value"
                          name={selectedTrend.label}
                          stroke="#0f766e"
                          strokeWidth={3}
                          dot={{ r: 4, fill: '#0f766e' }}
                          activeDot={{ r: 6 }}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  )}
                </ChartPanel>
              </div>
            </>
          )}
        </section>

        <section className="grid gap-6" aria-labelledby="scenario-heading">
          <SectionTitle
            eyebrow="Scenario Analysis"
            title="Base vs scenario impact"
            description="Scenario calculations are produced by the FastAPI impact engine."
          />
          <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
            <Panel>
              <SelectField
                label="Scenario"
                value={selectedScenario}
                onChange={setSelectedScenario}
                disabled={scenarioTypes.length === 0 || !selectedStatementId}
                options={scenarioTypes.map((scenario) => ({
                  value: scenario.scenario_type,
                  label: formatLabel(scenario.scenario_type),
                }))}
              />
              <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Assumption
                </p>
                <p className="mt-2 text-sm text-slate-700">
                  {scenarioTypes.find((item) => item.scenario_type === selectedScenario)
                    ?.magnitude_meaning || 'Select a scenario to view assumptions.'}
                </p>
              </div>
              <ImpactSummary scenarioRun={scenarioRun} loading={status.scenario === 'loading'} />
            </Panel>

            <ChartPanel title="Base vs Scenario">
              {status.scenario === 'loading' ? (
                <LoadingPanel message="Running scenario..." compact />
              ) : status.scenario === 'error' ? (
                <ErrorPanel message={errors.scenario} compact />
              ) : comparisonData.length === 0 ? (
                <EmptyState message="No scenario result available." />
              ) : (
                <ResponsiveContainer width="100%" height={340}>
                  <BarChart data={comparisonData} margin={{ left: 4, right: 16 }}>
                    <CartesianGrid stroke="#e2e8f0" strokeDasharray="4 4" />
                    <XAxis dataKey="metric" tick={{ fill: '#64748b', fontSize: 12 }} />
                    <YAxis tick={{ fill: '#64748b', fontSize: 12 }} tickFormatter={shortNumber} />
                    <Tooltip formatter={(value) => formatValue(value, 'currency')} />
                    <Legend />
                    <Bar dataKey="base" name="Base" fill="#334155" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="scenario" name="Scenario" fill="#0f766e" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </ChartPanel>
          </div>
        </section>

        <section className="grid gap-6" aria-labelledby="insights-heading">
          <SectionTitle
            eyebrow="AI Insights"
            title="Gemini-backed interpretation"
            description="The frontend only calls the backend insights API."
          />
          <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
            <Panel>
              {status.insight === 'loading' ? (
                <LoadingPanel message="Generating Gemini insight..." compact />
              ) : insight ? (
                <div className="space-y-5">
                  <TextBlock title="Gemini Insight" body={insight.overall_insight} />
                  {insight.scenario_explanation && (
                    <TextBlock title="Scenario Explanation" body={insight.scenario_explanation} />
                  )}
                  <ListBlock title="Main Risk Drivers" items={insight.risk_drivers} />
                  <ListBlock title="Business Considerations" items={insight.recommendations} />
                </div>
              ) : (
                <div className="space-y-3">
                  {status.insight === 'error' ? (
                    <ErrorPanel compact message={errors.insight} />
                  ) : (
                    <EmptyState message="Generate an AI insight for the selected company and scenario." />
                  )}
                  <button
                    type="button"
                    onClick={handleGenerateInsight}
                    disabled={!selectedStatementId}
                    className="min-h-11 rounded-md bg-teal-700 px-4 text-sm font-semibold text-white transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:bg-slate-300"
                  >
                    Generate AI insight
                  </button>
                </div>
              )}
              <form onSubmit={handleAsk} className="mt-6 border-t border-slate-200 pt-5">
                <label className="text-sm font-medium text-slate-700" htmlFor="question">
                  Ask FinSight
                </label>
                <div className="mt-2 flex flex-col gap-2 sm:flex-row">
                  <input
                    id="question"
                    value={question}
                    onChange={(event) => setQuestion(event.target.value)}
                    placeholder="What is the biggest financial risk here?"
                    className="min-h-11 flex-1 rounded-md border border-slate-300 bg-white px-3 text-sm outline-none ring-teal-600 transition focus:ring-2"
                  />
                  <button
                    type="submit"
                    disabled={!question.trim() || status.ask === 'loading'}
                    className="min-h-11 rounded-md bg-teal-700 px-4 text-sm font-semibold text-white transition hover:bg-teal-800 disabled:cursor-not-allowed disabled:bg-slate-300"
                  >
                    {status.ask === 'loading' ? 'Asking...' : 'Ask'}
                  </button>
                </div>
                {status.ask === 'error' && <p className="mt-2 text-sm text-rose-700">{errors.ask}</p>}
                {answer?.answer && (
                  <div className="mt-4 rounded-lg border border-teal-100 bg-teal-50 p-4 text-sm text-slate-700">
                    {answer.answer}
                  </div>
                )}
              </form>
            </Panel>

            <ChartPanel title="Risk Drivers">
              {riskDriverData.length === 0 ? (
                <EmptyState message="Risk driver data is not available." />
              ) : (
                <ResponsiveContainer width="100%" height={360}>
                  <BarChart
                    data={riskDriverData}
                    layout="vertical"
                    margin={{ left: 24, right: 20, top: 8, bottom: 8 }}
                  >
                    <CartesianGrid stroke="#e2e8f0" strokeDasharray="4 4" />
                    <XAxis type="number" tick={{ fill: '#64748b', fontSize: 12 }} />
                    <YAxis
                      type="category"
                      dataKey="name"
                      width={140}
                      tick={{ fill: '#64748b', fontSize: 12 }}
                    />
                    <Tooltip formatter={(value) => formatNumber(value)} />
                    <Bar dataKey="importance" name="Importance" radius={[0, 4, 4, 0]}>
                      {riskDriverData.map((entry, index) => (
                        <Cell key={entry.name} fill={index % 2 === 0 ? '#0f766e' : '#475569'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </ChartPanel>
          </div>
        </section>
      </main>
    </div>
  )
}

function SelectField({ label, value, onChange, options, disabled }) {
  return (
    <label className="block min-w-0">
      <span className="text-xs font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </span>
      <select
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 h-11 w-full min-w-0 rounded-md border border-slate-300 bg-white px-3 text-sm font-medium text-slate-900 outline-none ring-teal-600 transition focus:ring-2 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-400"
      >
        {options.length === 0 ? (
          <option value="">No options</option>
        ) : (
          options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))
        )}
      </select>
    </label>
  )
}

function SectionTitle({ eyebrow, title, description }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide text-teal-700">{eyebrow}</p>
      <h2 className="mt-1 text-xl font-semibold text-slate-950">{title}</h2>
      <p className="mt-1 text-sm text-slate-500">{description}</p>
    </div>
  )
}

function Panel({ children }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      {children}
    </div>
  )
}

function ChartPanel({ title, control, children }) {
  return (
    <Panel>
      <div className="mb-4 flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
        <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
        {control}
      </div>
      {children}
    </Panel>
  )
}

function HealthScoreCard({ score }) {
  const normalizedScore = Number(score || 0)
  return (
    <Panel>
      <p className="text-sm font-medium text-slate-500">Financial Health Score</p>
      <div className="mt-4 flex items-end gap-3">
        <span className="text-5xl font-semibold tracking-tight text-slate-950">
          {formatNumber(normalizedScore)}
        </span>
        <span className="pb-2 text-sm text-slate-500">/ 100</span>
      </div>
      <div className="mt-5 h-2 rounded-full bg-slate-100">
        <div
          className="h-2 rounded-full bg-teal-700"
          style={{ width: `${Math.min(Math.max(normalizedScore, 0), 100)}%` }}
        />
      </div>
    </Panel>
  )
}

function RiskCard({ risk }) {
  const category = risk?.risk_category || 'Unavailable'
  return (
    <Panel>
      <p className="text-sm font-medium text-slate-500">Risk Classification</p>
      <div
        className={`mt-4 inline-flex rounded-full border px-3 py-1 text-sm font-semibold ${
          RISK_COLORS[category] || 'border-slate-200 bg-slate-100 text-slate-700'
        }`}
      >
        {category}
      </div>
      <p className="mt-4 text-3xl font-semibold text-slate-950">
        {risk?.confidence != null ? formatValue(risk.confidence, 'percent') : 'N/A'}
      </p>
      <p className="mt-1 text-sm text-slate-500">Model confidence</p>
    </Panel>
  )
}

function KpiGrid({ kpis }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {KPI_CARDS.map((kpi) => (
        <div key={kpi.key} className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{kpi.label}</p>
          <p className="mt-2 text-2xl font-semibold text-slate-950">
            {formatValue(kpis?.[kpi.key], kpi.type)}
          </p>
        </div>
      ))}
    </div>
  )
}

function TrendSummary({ trend }) {
  const rows = TREND_OPTIONS.map((option) => ({
    label: option.label,
    direction: trend?.[option.key]?.direction || 'unavailable',
  }))

  return (
    <Panel>
      <h3 className="text-sm font-semibold text-slate-900">Historical Trend</h3>
      <div className="mt-4 space-y-3">
        {rows.map((row) => (
          <div key={row.label} className="flex items-center justify-between gap-3">
            <span className="text-sm text-slate-600">{row.label}</span>
            <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-medium capitalize text-slate-700">
              {row.direction.replace('_', ' ')}
            </span>
          </div>
        ))}
      </div>
    </Panel>
  )
}

function ImpactSummary({ scenarioRun, loading }) {
  if (loading) return <LoadingPanel message="Calculating impact..." compact />
  if (!scenarioRun?.impact_json) return <EmptyState message="No impact summary yet." />

  const affected = scenarioRun.impact_json.most_affected_metrics || []

  return (
    <div className="mt-4">
      <div className="grid grid-cols-2 gap-3">
        <MiniMetric label="Base Score" value={formatNumber(scenarioRun.health_score_base)} />
        <MiniMetric label="Scenario Score" value={formatNumber(scenarioRun.health_score_scenario)} />
      </div>
      <div className="mt-4 rounded-lg border border-slate-200 p-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Impact Summary
        </p>
        <p className="mt-2 text-sm text-slate-700">
          Health score changed by{' '}
          <span className="font-semibold text-slate-950">
            {formatSignedNumber(scenarioRun.health_score_change)}
          </span>{' '}
          points.
        </p>
        <div className="mt-3 space-y-2">
          {affected.slice(0, 3).map((item) => (
            <div key={`${item.metric}-${item.metric_kind}`} className="text-sm text-slate-600">
              {formatLabel(item.metric)}: {formatSignedNumber(item.ranking_value)}
              {item.ranking_measure === 'pct_of_base_revenue' ? '% of revenue' : ' score pts'}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function MiniMetric({ label, value }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
      <p className="text-xs font-medium text-slate-500">{label}</p>
      <p className="mt-1 text-lg font-semibold text-slate-950">{value}</p>
    </div>
  )
}

function TextBlock({ title, body }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
      <p className="mt-2 text-sm leading-6 text-slate-700">{body}</p>
    </div>
  )
}

function ListBlock({ title, items }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
      <ul className="mt-2 space-y-2">
        {(items || []).map((item) => (
          <li key={item} className="rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-700">
            {item}
          </li>
        ))}
      </ul>
    </div>
  )
}

function LoadingPanel({ message, compact = false }) {
  return (
    <div
      className={`flex items-center justify-center rounded-lg border border-slate-200 bg-white text-sm text-slate-500 ${
        compact ? 'min-h-32 p-4' : 'min-h-48 p-6'
      }`}
    >
      {message}
    </div>
  )
}

function EmptyState({ message }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-white p-5 text-sm text-slate-500">
      {message}
    </div>
  )
}

function ErrorBanner({ message }) {
  return (
    <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
      {message}
    </div>
  )
}

function ErrorPanel({ message, compact = false }) {
  return (
    <div
      className={`rounded-lg border border-rose-200 bg-rose-50 text-sm text-rose-700 ${
        compact ? 'p-4' : 'p-5'
      }`}
    >
      {message}
    </div>
  )
}

function toErrorMessage(error) {
  const rawMessage = String(
    error?.response?.data?.message ||
      error?.response?.data?.detail ||
      error?.message ||
      'Something went wrong.',
  )

  if (
    error?.response?.status === 429 ||
    rawMessage.includes('RESOURCE_EXHAUSTED') ||
    rawMessage.toLowerCase().includes('quota')
  ) {
    return 'Gemini free quota is exhausted. You will not be charged unless billing is enabled in Google AI Studio. Try again later, or leave AI off and keep using the dashboard analytics.'
  }

  if (rawMessage.toLowerCase().includes('timeout')) {
    return 'The AI request took too long. This usually means Gemini is slow or unavailable right now.'
  }

  return (
    rawMessage
  )
}

function formatValue(value, type = 'number') {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return 'N/A'
  if (type === 'percent') return `${formatNumber(Number(value) * 100)}%`
  if (type === 'currency') return shortCurrency(value)
  if (type === 'score') return formatNumber(value)
  return formatNumber(value)
}

function formatChartValue(value, type) {
  if (type === 'percent') return `${formatNumber(Number(value) * 100)}%`
  if (type === 'currency') return shortNumber(value)
  return formatNumber(value)
}

function formatNumber(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return 'N/A'
  return new Intl.NumberFormat('en-US', {
    maximumFractionDigits: 2,
  }).format(Number(value))
}

function formatSignedNumber(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return 'N/A'
  const number = Number(value)
  return `${number > 0 ? '+' : ''}${formatNumber(number)}`
}

function shortCurrency(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return 'N/A'
  return new Intl.NumberFormat('en-US', {
    notation: 'compact',
    maximumFractionDigits: 2,
    style: 'currency',
    currency: 'USD',
  }).format(Number(value))
}

function shortNumber(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return 'N/A'
  return new Intl.NumberFormat('en-US', {
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(Number(value))
}

function formatLabel(value) {
  return String(value || '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
}

export default App

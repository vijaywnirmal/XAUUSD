'use client'

import { useEffect, useState } from 'react'
import {
  Activity,
  BarChart3,
  Check,
  ChevronRight,
  FlaskConical,
  GitCompare,
  Play,
  Search,
  Sparkles,
  TrendingUp,
  Zap,
} from 'lucide-react'
import ParamFields from '@/components/ParamFields'
import ResultsPanel from '@/components/ResultsPanel'
import ComparePanel from '@/components/ComparePanel'
import StrategyBuilder from '@/components/StrategyBuilder'
import LiveBotPanel from '@/components/LiveBotPanel'
import {
  defaultsFrom,
  fetchIndicators,
  fetchStrategies,
  runBacktest,
  type BacktestResult,
  type IndicatorInfo,
  type RunConfig,
  type StrategyInfo,
} from '@/lib/api'

type Tab = 'Setup' | 'Results' | 'Compare' | 'LiveBot'
type CategoryFilter = 'all' | 'intraday' | 'daily-portfolio'

const CAT_COLOR: Record<string, string> = {
  intraday: 'indigo',
  'daily-portfolio': 'teal',
}

const CAT_ICON = {
  intraday: TrendingUp,
  'daily-portfolio': Zap,
}

const SPLITS = ['in_sample', 'walk_forward', 'out_of_sample'] as const
const TIMEFRAMES = ['1min', '5min', '15min', '1D']

export default function Page() {
  const [tab, setTab] = useState<Tab>('Setup')
  const [dark, setDark] = useState(false)
  const [query, setQuery] = useState('')
  const [cat, setCat] = useState<CategoryFilter>('all')
  const [strategies, setStrategies] = useState<StrategyInfo[]>([])
  const [indicators, setIndicators] = useState<IndicatorInfo[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string>('')
  const [params, setParams] = useState<Record<string, unknown>>({})
  const [runConfig, setRunConfig] = useState<RunConfig>({
    split: 'in_sample',
    size_mode: 'fixed',
    size_lots: 0.01,
    initial_equity: 1000,
    slippage_ticks: 1,
  })
  const [result, setResult] = useState<BacktestResult | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    setReady(true)
  }, [])

  useEffect(() => {
    fetchStrategies()
      .then((list) => {
        setStrategies(list)
        if (list[0]) {
          setSelectedId(list[0].id)
          setParams(defaultsFrom(list[0].params))
          setRunConfig((c) => ({ ...c, timeframe: list[0].timeframe }))
        }
      })
      .catch((e) => setLoadError(e instanceof Error ? e.message : String(e)))
    fetchIndicators().then(setIndicators).catch(() => setIndicators([]))
  }, [])

  if (!ready) {
    return (
      <div className="app">
        <main className="main">
          <p className="empty-state">Loading workspace…</p>
        </main>
      </div>
    )
  }

  const selected = selectedId === 'custom' ? null : strategies.find((s) => s.id === selectedId)
  const q = query.toLowerCase()
  const filtered = strategies.filter((s) => {
    if (cat !== 'all' && s.category !== cat) return false
    return !q || s.name.toLowerCase().includes(q) || s.id.toLowerCase().includes(q) || s.description.toLowerCase().includes(q)
  })

  const pickStrategy = (id: string) => {
    setSelectedId(id)
    if (id === 'custom') return
    const s = strategies.find((x) => x.id === id)
    if (s) {
      setParams(defaultsFrom(s.params))
      setRunConfig((c) => ({ ...c, timeframe: s.timeframe }))
    }
  }

  const patchConfig = (patch: Partial<RunConfig>) => setRunConfig((c) => ({ ...c, ...patch }))

  const oosBlocked = runConfig.split === 'out_of_sample' && !runConfig.allow_oos

  const run = async () => {
    if (!selected || oosBlocked) return
    setRunning(true)
    setError(null)
    try {
      const res = await runBacktest(selected.id, params, {
        ...runConfig,
        timeframe: runConfig.timeframe || selected.timeframe,
      })
      setResult(res)
      setTab('Results')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className={dark ? 'app dark' : 'app'}>
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><FlaskConical size={18} /></div>
          <span>XAUUSD<span className="brand-dot">.</span></span>
        </div>
        <div className="workspace-label">Workspace</div>
        <nav className="side-nav">
          <button className={tab !== 'Compare' ? 'side-link active' : 'side-link'} onClick={() => setTab('Setup')}>
            <BarChart3 size={17} /><span>Backtest</span>
          </button>
          <button className={tab === 'Compare' ? 'side-link active' : 'side-link'} onClick={() => setTab('Compare')}>
            <GitCompare size={17} /><span>Compare</span>
          </button>
          <button className={tab === 'LiveBot' ? 'side-link active' : 'side-link'} onClick={() => setTab('LiveBot')}>
            <Activity size={17} /><span>Live bot</span>
          </button>
        </nav>
        <div className="sidebar-bottom">
          <p className="side-note">Gold research backtester. Data stays on this machine.</p>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div className="breadcrumbs">
            <span>Backtest</span>
            <ChevronRight size={14} />
            <strong>{tab === 'Compare' ? 'Compare' : tab === 'LiveBot' ? 'Live bot' : selected?.name || (selectedId === 'custom' ? 'Strategy builder' : 'Setup')}</strong>
          </div>
          <button className="theme-toggle" onClick={() => setDark((d) => !d)}>{dark ? 'Light mode' : 'Dark mode'}</button>
        </header>

        <section className="page-head">
          <div>
            <div className="eyebrow"><span className="status-dot" /> XAUUSD research</div>
            <h1>{tab === 'Compare' ? 'Compare strategies' : tab === 'LiveBot' ? 'H1 execution bot' : 'Run a backtest'}</h1>
            <p>{tab === 'LiveBot'
              ? 'Live read-only view of the paper-trading H1 bot (livebot/). It runs as its own process.'
              : 'Re-run the project hypotheses with live parameters, then inspect equity, trades, and the success bar.'}</p>
          </div>
          {tab !== 'Compare' && selectedId !== 'custom' && (
            <div className="head-actions">
              <button className="primary-btn" disabled={running || !selected || oosBlocked} onClick={run}>
                <Play size={15} fill="currentColor" /> {running ? 'Running…' : 'Run backtest'}
              </button>
            </div>
          )}
        </section>

        <div className="tabs" role="tablist" style={{ display: tab === 'LiveBot' ? 'none' : undefined }}>
          {(['Setup', 'Results', 'Compare'] as Tab[]).map((t) => (
            <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? 'tab active' : 'tab'} onClick={() => setTab(t)}>
              {t}
              {t === 'Results' && result && <span className="tab-count">1</span>}
            </button>
          ))}
        </div>

        {loadError && <p className="error">Could not load strategies. Is the FastAPI server running on port 8000? {loadError}</p>}

        {/* Kept mounted (hidden via CSS, not unmounted) across tab switches so
            StrategyBuilder's rule state, ParamFields, and ResultsPanel's own
            state (e.g. trade-table pagination) all survive navigating away
            and back — previously switching to Results reset any in-progress
            custom strategy rules to defaults. */}
        <div style={{ display: tab === 'Setup' ? undefined : 'none' }}>
          <div className="setup-layout">
            <section className="setup-main">
              <div className="section-title">
                <div>
                  <span className="step">01</span>
                  <div>
                    <h2>Choose a strategy</h2>
                    <p>Research registry plus a custom indicator builder.</p>
                  </div>
                </div>
                <div className="filter-pills">
                  {(['all', 'intraday', 'daily-portfolio'] as CategoryFilter[]).map((c) => (
                    <button key={c} className={cat === c ? 'selected' : ''} onClick={() => setCat(c)}>{c}</button>
                  ))}
                </div>
              </div>
              <div className="search-input">
                <Search size={16} />
                <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search strategies" />
              </div>
              <div className="strategy-grid">
                <button
                  onClick={() => pickStrategy('custom')}
                  className={selectedId === 'custom' ? 'strategy-card selected slate' : 'strategy-card slate'}
                >
                  <div className="strategy-icon"><Sparkles size={18} /></div>
                  <div className="strategy-copy">
                    <div><h3>Custom builder</h3><span className="tag">builder</span></div>
                    <p>Compose long/short rules from SMA, EMA, RSI, ATR, and the rest of the indicator library.</p>
                  </div>
                  {selectedId === 'custom' && <span className="selected-check"><Check size={13} /></span>}
                </button>
                {filtered.map((s) => {
                  const Icon = CAT_ICON[s.category]
                  const color = CAT_COLOR[s.category]
                  return (
                    <button
                      key={s.id}
                      onClick={() => pickStrategy(s.id)}
                      className={selectedId === s.id ? `strategy-card selected ${color}` : `strategy-card ${color}`}
                    >
                      <div className="strategy-icon"><Icon size={18} /></div>
                      <div className="strategy-copy">
                        <div><h3>{s.name}</h3><span className="tag">{s.category}</span></div>
                        <p>{s.description}</p>
                      </div>
                      {selectedId === s.id && <span className="selected-check"><Check size={13} /></span>}
                    </button>
                  )
                })}
              </div>

              {selectedId === 'custom' ? (
                <>
                  <div className="section-title rules-title">
                    <div>
                      <span className="step">02</span>
                      <div>
                        <h2>Define your rules</h2>
                        <p>These compile through the same Backtester as the research scripts.</p>
                      </div>
                    </div>
                  </div>
                  <StrategyBuilder
                    indicators={indicators}
                    timeframe={runConfig.timeframe || '5min'}
                    split={runConfig.split || 'in_sample'}
                    start={runConfig.start}
                    end={runConfig.end}
                    sizeMode={runConfig.size_mode}
                    sizeLots={runConfig.size_lots}
                    riskPct={runConfig.risk_pct}
                    initialEquity={runConfig.initial_equity}
                    slippageTicks={runConfig.slippage_ticks}
                    onRun={(res) => {
                      setResult(res)
                      setTab('Results')
                    }}
                  />
                </>
              ) : selected && (
                <>
                  <div className="section-title rules-title">
                    <div>
                      <span className="step">02</span>
                      <div>
                        <h2>Parameters</h2>
                        <p>{selected.notes || 'Values passed through to the research module.'}</p>
                      </div>
                    </div>
                  </div>
                  <div className="rule-builder">
                    <ParamFields params={selected.params} values={params} onChange={(n, v) => setParams((p) => ({ ...p, [n]: v }))} />
                  </div>
                </>
              )}
            </section>

            <aside className="config-panel">
              <div className="config-heading">
                <div>
                  <span className="step">03</span>
                  <div>
                    <h2>Run configuration</h2>
                    <p>Split, window, and sizing for this test.</p>
                  </div>
                </div>
              </div>
              <label className="field-label">Asset</label>
              <div className="select-button static">
                <span className="asset-icon gold">Au</span>
                <span><b>XAUUSD</b><small>Spot gold · research data</small></span>
              </div>
              <label className="field-label">Timeframe</label>
              <div className="segmented">
                {TIMEFRAMES.map((tf) => (
                  <button key={tf} className={runConfig.timeframe === tf ? 'selected' : ''} onClick={() => patchConfig({ timeframe: tf })}>
                    {tf}
                  </button>
                ))}
              </div>
              <label className="field-label">Split</label>
              <select
                className="field-select"
                value={runConfig.split}
                onChange={(e) => patchConfig({ split: e.target.value, allow_oos: e.target.value === 'out_of_sample' ? runConfig.allow_oos : false })}
              >
                {SPLITS.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
              {runConfig.split === 'out_of_sample' && (
                <label className="config-options" style={{ marginTop: 10 }}>
                  <input type="checkbox" checked={!!runConfig.allow_oos} onChange={(e) => patchConfig({ allow_oos: e.target.checked })} />
                  I understand out-of-sample is touch-once
                </label>
              )}
              <label className="field-label">Optional date window</label>
              <div className="date-grid">
                <div>
                  <small>From</small>
                  <input type="date" value={runConfig.start || ''} onChange={(e) => patchConfig({ start: e.target.value || null })} />
                </div>
                <div>
                  <small>To</small>
                  <input type="date" value={runConfig.end || ''} onChange={(e) => patchConfig({ end: e.target.value || null })} />
                </div>
              </div>
              <div className="config-divider" />
              <div className="funds-head">
                <label className="field-label">Starting funds</label>
                <span>USD</span>
              </div>
              <div className="funds-input">
                <span>$</span>
                <input
                  type="number"
                  value={runConfig.initial_equity ?? 1000}
                  onChange={(e) => patchConfig({ initial_equity: Number(e.target.value) })}
                />
              </div>
              <label className="field-label">Size mode</label>
              <select className="field-select" value={runConfig.size_mode} onChange={(e) => patchConfig({ size_mode: e.target.value })}>
                <option value="fixed">Fixed lots</option>
                <option value="risk_pct">Risk % of equity</option>
              </select>
              {runConfig.size_mode === 'risk_pct' ? (
                <>
                  <label className="field-label">Risk %</label>
                  <input className="field-select" type="number" step="0.001" value={runConfig.risk_pct ?? 0.005} onChange={(e) => patchConfig({ risk_pct: Number(e.target.value) })} />
                </>
              ) : (
                <>
                  <label className="field-label">Lots</label>
                  <input className="field-select" type="number" step="0.01" value={runConfig.size_lots ?? 0.01} onChange={(e) => patchConfig({ size_lots: Number(e.target.value) })} />
                </>
              )}
              <label className="field-label">Slippage (ticks)</label>
              <input className="field-select" type="number" step="0.5" value={runConfig.slippage_ticks ?? 1} onChange={(e) => patchConfig({ slippage_ticks: Number(e.target.value) })} />
              {selectedId !== 'custom' && (
                <button className="run-full" disabled={running || !selected || oosBlocked} onClick={run}>
                  <Play size={15} fill="currentColor" /> {running ? 'Running analysis…' : 'Run backtest'}
                </button>
              )}
              {oosBlocked && <p className="run-note">Confirm the out-of-sample checkbox to run that split.</p>}
              {error && <p className="error">{error}</p>}
            </aside>
          </div>
        </div>

        <div style={{ display: tab === 'Results' ? undefined : 'none' }}>
          {result ? <ResultsPanel result={result} /> : <p className="empty-state">Run a backtest from Setup to see equity, trades, and the success bar.</p>}
        </div>
        <div style={{ display: tab === 'Compare' ? undefined : 'none' }}>
          <ComparePanel strategies={strategies} runConfig={runConfig} />
        </div>
        <div style={{ display: tab === 'LiveBot' ? undefined : 'none' }}>
          <LiveBotPanel />
        </div>
      </main>
    </div>
  )
}

'use client'

import { useMemo, useState } from 'react'
import { Play, Plus, X } from 'lucide-react'
import type { BacktestResult, RunConfig, StrategyInfo } from '@/lib/api'
import { defaultsFrom, runCompare } from '@/lib/api'
import { fmtNum, fmtPct } from '@/lib/format'
import { EquityChart } from '@/components/Charts'

const DOT = ['indigo', 'teal', 'gray', 'amber']

export default function ComparePanel({
  strategies,
  runConfig,
}: {
  strategies: StrategyInfo[]
  runConfig: RunConfig
}) {
  const [ids, setIds] = useState<string[]>([])
  const [results, setResults] = useState<BacktestResult[]>([])
  const [errors, setErrors] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [pickerOpen, setPickerOpen] = useState(false)

  const selected = useMemo(() => strategies.filter((s) => ids.includes(s.id)), [strategies, ids])

  const toggle = (id: string) => {
    setIds((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]))
  }

  const run = async () => {
    if (!ids.length) return
    setLoading(true)
    setErrors([])
    try {
      const payload = ids.map((id) => {
        const strat = strategies.find((s) => s.id === id)
        return {
          strategy_id: id,
          params: defaultsFrom(strat?.params || []),
          run_config: { ...runConfig, timeframe: runConfig.timeframe || strat?.timeframe },
        }
      })
      const { runs } = await runCompare(payload)
      const ok: BacktestResult[] = []
      const bad: string[] = []
      for (const r of runs) {
        if (r.error) bad.push(`${r.strategy_id || r.strategy?.id}: ${r.error}`)
        else ok.push(r)
      }
      setResults(ok)
      setErrors(bad)
    } catch (e) {
      setErrors([e instanceof Error ? e.message : String(e)])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="compare-view">
      <div className="compare-head">
        <div>
          <div className="eyebrow">
            <span className="status-dot" /> {ids.length} selected
          </div>
          <h2>Compare strategies</h2>
          <p>Same split, dates, and sizing. Each strategy uses its own default parameters.</p>
        </div>
        <div className="head-actions">
          <button className="secondary-btn" onClick={() => setPickerOpen((v) => !v)}>
            <Plus size={15} /> {pickerOpen ? 'Hide list' : 'Add strategy'}
          </button>
          <button className="primary-btn" disabled={loading || ids.length < 2} onClick={run}>
            <Play size={15} fill="currentColor" /> {loading ? 'Running…' : `Run ${ids.length}`}
          </button>
        </div>
      </div>

      {pickerOpen && (
        <div className="compare-picker">
          {strategies.map((s) => (
            <label key={s.id} className="compare-option">
              <input type="checkbox" checked={ids.includes(s.id)} onChange={() => toggle(s.id)} />
              <span>
                <b>{s.name}</b>
                <small>{s.category}</small>
              </span>
            </label>
          ))}
        </div>
      )}

      {selected.length > 0 && (
        <div className="selected-chips">
          {selected.map((s) => (
            <button key={s.id} className="chip" onClick={() => toggle(s.id)}>
              {s.name} <X size={12} />
            </button>
          ))}
        </div>
      )}

      {errors.map((e) => (
        <p key={e} className="error">{e}</p>
      ))}

      {results.length > 0 && (
        <>
          <div className="panel compare-chart-panel">
            <div className="panel-head">
              <div>
                <h3>Equity overlay</h3>
                <p>Raw equity from each run (not rebased)</p>
              </div>
            </div>
            <EquityChart
              series={results.map((r, i) => ({
                label: r.strategy.name,
                color: ['#5564e8', '#18a88a', '#ee6f62', '#bc7712', '#8b5cf6', '#0ea5e9'][i % 6],
                points: r.equity,
              }))}
            />
          </div>
          <div className="panel compare-table">
            <div className="compare-row compare-header">
              <span>Strategy</span>
              <span>Return</span>
              <span>Max drawdown</span>
              <span>Sharpe</span>
              <span>Win rate</span>
              <span>Trades</span>
              <span />
            </div>
            {results.map((r, i) => (
              <div className="compare-row" key={r.run_id}>
                <span className="strategy-name">
                  <i className={`dot ${DOT[i % DOT.length]}`} />
                  <b>{r.strategy.name}</b>
                </span>
                <span className={Number(r.metrics.total_return_pct) >= 0 ? 'positive' : 'negative'}>
                  {typeof r.metrics.total_return_pct === 'number' ? fmtPct(r.metrics.total_return_pct) : fmtNum(r.metrics.total_return_pct)}
                </span>
                <span className="negative">
                  {typeof r.metrics.max_drawdown_pct === 'number' ? fmtPct(-Math.abs(r.metrics.max_drawdown_pct)) : fmtNum(r.metrics.max_drawdown_pct)}
                </span>
                <span>{fmtNum(r.metrics.sharpe, 3)}</span>
                <span>{fmtNum(r.metrics.win_rate, 3)}</span>
                <span>{fmtNum(r.metrics.n_trades, 0)}</span>
                <span />
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

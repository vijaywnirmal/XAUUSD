'use client'

import { useState } from 'react'
import { ChevronDown, Download, Gauge } from 'lucide-react'
import type { BacktestResult } from '@/lib/api'
import { exportUrl } from '@/lib/api'
import { fmtNum, fmtPct, fmtTs, fmtUsd } from '@/lib/format'
import { CloseChart, EquityChart } from '@/components/Charts'
import TradingChart from '@/components/TradingChart'

function metric(result: BacktestResult, key: string) {
  return result.metrics[key]
}

export default function ResultsPanel({ result }: { result: BacktestResult }) {
  const [page, setPage] = useState(0)
  const [exportOpen, setExportOpen] = useState(false)
  const trades = result.trades || []
  const pageSize = 20
  const start = page * pageSize
  const rows = trades.slice(start, start + pageSize)
  const nTrades = metric(result, 'n_trades')
  const ret = metric(result, 'total_return_pct')
  const cagr = metric(result, 'cagr_pct')
  const dd = metric(result, 'max_drawdown_pct')
  const sharpe = metric(result, 'sharpe')
  const cards: [string, string, string, boolean][] = [
    ['Total return', typeof ret === 'number' ? fmtPct(ret) : fmtNum(ret), `${result.n_bars.toLocaleString()} bars`, typeof ret === 'number' && ret < 0],
    ['CAGR', typeof cagr === 'number' ? fmtPct(cagr) : fmtNum(cagr), 'Annualized', typeof cagr === 'number' && cagr < 0],
    ['Max drawdown', typeof dd === 'number' ? fmtPct(-Math.abs(dd)) : fmtNum(dd), 'Peak to trough', true],
    ['Sharpe', fmtNum(sharpe, 3), 'Risk-adjusted return', typeof sharpe === 'number' && sharpe < 0],
  ]

  return (
    <div className="results">
      <div className="result-banner">
        <div>
          <div className="success-label">
            <span className="status-dot" />
            {result.success_bar_all_pass ? 'Success bar passed' : 'Backtest complete'}
            <span>
              · {typeof nTrades === 'number' ? `${nTrades.toLocaleString()} trades` : 'no discrete trade list'}
            </span>
          </div>
          <h2>
            {result.strategy.name} <span className="muted">on XAUUSD · {result.run_config.timeframe || result.category}</span>
          </h2>
        </div>
        <div className="result-actions">
          <div className="export-wrap">
            <button className="secondary-btn" onClick={() => setExportOpen((v) => !v)}>
              <Download size={15} /> Export <ChevronDown size={14} />
            </button>
            {exportOpen && (
              <div className="export-menu">
                {(['csv', 'json', 'pdf'] as const).map((fmt) => (
                  <a key={fmt} href={exportUrl(result.run_id, fmt)} target="_blank" rel="noreferrer" onClick={() => setExportOpen(false)}>
                    {fmt.toUpperCase()}
                  </a>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="metric-grid">
        {cards.map((m) => (
          <div className="metric-card" key={m[0]}>
            <span>{m[0]}</span>
            <strong className={m[3] ? 'negative' : 'positive'}>{m[1]}</strong>
            <small>{m[2]}</small>
          </div>
        ))}
      </div>

      <div className="results-grid">
        <section className="panel equity-panel">
          <div className="panel-head">
            <div>
              <h3>Equity curve</h3>
              <p>Account equity over the selected split</p>
            </div>
          </div>
          <EquityChart series={[{ label: result.strategy.name, points: result.equity }]} />
        </section>
        <section className="panel summary-panel">
          <div className="panel-head">
            <div>
              <h3>Performance summary</h3>
              <p>Engine metrics for this run</p>
            </div>
            <Gauge size={18} className="muted-icon" />
          </div>
          <div className="summary-list">
            {[
              ['Profit factor', fmtNum(metric(result, 'profit_factor'), 3)],
              ['Win rate', typeof metric(result, 'win_rate') === 'number' ? `${Number(metric(result, 'win_rate')).toFixed(1)}%` : fmtNum(metric(result, 'win_rate'))],
              ['Expectancy', fmtUsd(metric(result, 'expectancy_usd'))],
              ['Final equity', fmtNum(metric(result, 'final_equity'), 2)],
              ['Net PnL', fmtUsd(metric(result, 'net_pnl_usd'))],
            ].map((row) => (
              <div key={row[0]}>
                <span>{row[0]}</span>
                <b>{row[1]}</b>
              </div>
            ))}
          </div>
          <div className="confidence">
            <div>
              <span>Success bar</span>
              <b className={result.success_bar_all_pass ? undefined : 'negative'}>
                {result.success_bar_all_pass ? 'ALL PASS' : `${result.success_bar.filter((r) => r.pass === 'PASS').length}/${result.success_bar.length} pass`}
              </b>
            </div>
            <div className="success-rows">
              {result.success_bar.map((r) => (
                <div key={r.metric} className={r.pass === 'PASS' ? 'pass' : r.pass === 'FAIL' ? 'fail' : ''}>
                  <span>{r.metric}</span>
                  <em>{r.pass}</em>
                </div>
              ))}
            </div>
          </div>
        </section>
      </div>

      {result.ohlc.length > 0 && (
        <section className="panel price-panel">
          <div className="panel-head">
            <div>
              <h3>Price action &amp; trades</h3>
              <p>XAUUSD close · downsampled for display · entry markers (first 80 trades)</p>
            </div>
          </div>
          <CloseChart ohlc={result.ohlc} trades={trades} />
        </section>
      )}

      {result.category !== 'daily-portfolio' && <TradingChart runId={result.run_id} />}

      <section className="panel trades-panel">
        <div className="panel-head">
          <div>
            <h3>Trade history</h3>
            <p>
              {trades.length
                ? `Showing ${start + 1}–${Math.min(start + pageSize, trades.length)} of ${trades.length}`
                : 'No discrete trades for this hypothesis'}
            </p>
          </div>
          {trades.length > pageSize && (
            <div className="pager">
              <button className="ghost-btn" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>Prev</button>
              <button className="ghost-btn" disabled={start + pageSize >= trades.length} onClick={() => setPage((p) => p + 1)}>Next</button>
            </div>
          )}
        </div>
        {trades.length > 0 && (
          <div className="trade-table">
            <div className="trade-tr trade-header">
              <span>Entry</span><span>Side</span><span>Entry px</span><span>Exit px</span><span>P&amp;L</span><span>R</span><span>Status</span>
            </div>
            {rows.map((t, i) => {
              const pnl = Number(t.net_pnl)
              const win = pnl > 0
              const side = Number(t.side) === 1 ? 'Long' : Number(t.side) === -1 ? 'Short' : String(t.side ?? '')
              return (
                <div className="trade-tr" key={`${t.entry_ts}-${i}`}>
                  <span>{fmtTs(t.entry_ts)}</span>
                  <span className={side === 'Long' ? 'long' : 'short'}>{side}</span>
                  <span>{fmtNum(t.entry_mid, 2)}</span>
                  <span>{fmtNum(t.exit_mid, 2)}</span>
                  <span className={win ? 'positive' : 'negative'}>{fmtUsd(pnl)}</span>
                  <span>{fmtNum(t.r_multiple, 2)}</span>
                  <span><em className={win ? 'win' : 'loss'}>{win ? 'Win' : 'Loss'}</em></span>
                </div>
              )
            })}
          </div>
        )}
      </section>
    </div>
  )
}

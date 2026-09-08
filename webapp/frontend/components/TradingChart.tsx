'use client'

import { useEffect, useRef, useState } from 'react'
import type { RunDetail, RunDetailTrade } from '@/lib/api'
import { fetchRunDetail } from '@/lib/api'

const WINDOW_OPTIONS = [
  { label: '1 week', days: 7 },
  { label: '1 month', days: 30 },
  { label: '3 months', days: 90 },
]

export default function TradingChart({ runId }: { runId: string }) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<{ remove: () => void } | null>(null)
  const [days, setDays] = useState(30)
  const [detail, setDetail] = useState<RunDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchRunDetail(runId, days)
      .then((d) => { if (!cancelled) setDetail(d) })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [runId, days])

  useEffect(() => {
    if (!detail || !containerRef.current) return
    let disposed = false

    import('lightweight-charts').then(({ createChart, ColorType, LineStyle, CrosshairMode }) => {
      if (disposed || !containerRef.current) return
      containerRef.current.innerHTML = ''

      const isDark = document.documentElement.classList.contains('dark') || document.querySelector('.app.dark')
      const textColor = isDark ? '#c9cedb' : '#4b5163'
      const gridColor = isDark ? '#2a2f3d' : '#eceef3'

      const chart = createChart(containerRef.current, {
        width: containerRef.current.clientWidth,
        height: 440,
        layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor },
        grid: { vertLines: { color: gridColor }, horzLines: { color: gridColor } },
        crosshair: { mode: CrosshairMode.Normal },
        timeScale: { timeVisible: true, secondsVisible: false, borderColor: gridColor },
        rightPriceScale: { borderColor: gridColor },
      })
      chartRef.current = chart

      const candleSeries = chart.addCandlestickSeries({
        upColor: '#18a88a', downColor: '#ee6f62',
        borderUpColor: '#18a88a', borderDownColor: '#ee6f62',
        wickUpColor: '#18a88a', wickDownColor: '#ee6f62',
      })
      candleSeries.setData(detail.candles)

      const markers = detail.trades.flatMap((t: RunDetailTrade) => {
        const entryTime = Math.floor(Date.parse(t.entry_ts) / 1000)
        const exitTime = Math.floor(Date.parse(t.exit_ts) / 1000)
        const isLong = t.side === 1
        const won = t.net_pnl > 0
        return [
          {
            time: entryTime, position: isLong ? 'belowBar' : 'aboveBar',
            color: isLong ? '#18a88a' : '#ee6f62',
            shape: isLong ? 'arrowUp' : 'arrowDown',
            text: isLong ? 'Long' : 'Short',
          },
          {
            time: exitTime, position: isLong ? 'aboveBar' : 'belowBar',
            color: won ? '#18a88a' : '#ee6f62',
            shape: 'circle',
            text: `Exit (${t.exit_reason})`,
          },
        ]
      }).sort((a, b) => a.time - b.time)
      candleSeries.setMarkers(markers as never)

      // Per-trade SL/TP as short segments spanning only the trade's own
      // lifetime (entry -> exit), not full-width lines, so brackets from
      // different trades at different levels don't clutter each other.
      for (const t of detail.trades) {
        const entryTime = Math.floor(Date.parse(t.entry_ts) / 1000)
        const exitTime = Math.floor(Date.parse(t.exit_ts) / 1000)
        if (t.stop_lvl != null) {
          const s = chart.addLineSeries({ color: '#ee6f62', lineWidth: 1, lineStyle: LineStyle.Dashed, lastValueVisible: false, priceLineVisible: false })
          s.setData([{ time: entryTime, value: t.stop_lvl }, { time: exitTime, value: t.stop_lvl }] as never)
        }
        if (t.tgt_lvl != null) {
          const s = chart.addLineSeries({ color: '#18a88a', lineWidth: 1, lineStyle: LineStyle.Dashed, lastValueVisible: false, priceLineVisible: false })
          s.setData([{ time: entryTime, value: t.tgt_lvl }, { time: exitTime, value: t.tgt_lvl }] as never)
        }
      }

      chart.timeScale().fitContent()

      const onResize = () => {
        if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth })
      }
      window.addEventListener('resize', onResize)
      return () => window.removeEventListener('resize', onResize)
    })

    return () => {
      disposed = true
      chartRef.current?.remove()
      chartRef.current = null
    }
  }, [detail])

  return (
    <div className="panel price-panel">
      <div className="panel-head">
        <div>
          <h3>Candlestick view — entries, exits, SL/TP</h3>
          <p>Real TradingView-style chart for a bounded window (full resolution, not downsampled).</p>
        </div>
        <div className="period-pills">
          {WINDOW_OPTIONS.map((o) => (
            <button key={o.days} className={days === o.days ? 'active' : ''} onClick={() => setDays(o.days)}>
              {o.label}
            </button>
          ))}
        </div>
      </div>
      {loading && <p className="muted" style={{ marginTop: 16 }}>Loading candles…</p>}
      {error && <p className="error">{error}</p>}
      {detail && (
        <p className="muted" style={{ marginTop: 12 }}>
          {detail.n_candles.toLocaleString()} candles, {detail.n_trades_in_window} trade(s) in this window
          ({String(detail.window_start).slice(0, 10)} – {String(detail.window_end).slice(0, 10)}).
          {' '}<span style={{ color: '#ee6f62' }}>‑ ‑ ‑</span> stop &nbsp; <span style={{ color: '#18a88a' }}>‑ ‑ ‑</span> target
        </p>
      )}
      <div ref={containerRef} style={{ marginTop: 12, width: '100%' }} />
    </div>
  )
}

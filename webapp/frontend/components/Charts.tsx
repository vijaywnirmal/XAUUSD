'use client'

function downsample<T>(items: T[], max = 240): T[] {
  if (items.length <= max) return items
  const step = Math.ceil(items.length / max)
  const out: T[] = []
  for (let i = 0; i < items.length; i += step) out.push(items[i])
  if (out[out.length - 1] !== items[items.length - 1]) out.push(items[items.length - 1])
  return out
}

const COLORS = ['#5564e8', '#18a88a', '#ee6f62', '#bc7712', '#8b5cf6', '#0ea5e9']

export function EquityChart({
  series,
}: {
  series: { label: string; color?: string; points: { ts: string; equity: number }[] }[]
}) {
  const sampled = series.map((s) => ({ ...s, points: downsample(s.points) }))
  const all = sampled.flatMap((s) => s.points.map((p) => p.equity)).filter((n) => Number.isFinite(n))
  if (!all.length) return <p className="muted">No equity series for this run.</p>

  const min = Math.min(...all)
  const max = Math.max(...all)
  const pad = (max - min) || Math.abs(max) * 0.05 || 1
  const lo = min - pad * 0.08
  const hi = max + pad * 0.08
  const w = 720
  const h = 260
  const x = (i: number, n: number) => (n <= 1 ? 0 : (i / (n - 1)) * w)
  const y = (v: number) => h - ((v - lo) / (hi - lo)) * h

  const paths = sampled.map((s, si) => {
    const n = s.points.length
    const d = s.points.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(i, n).toFixed(1)} ${y(p.equity).toFixed(1)}`).join(' ')
    return { ...s, d, color: s.color || COLORS[si % COLORS.length], n }
  })
  const area = paths[0]
  const areaFill = area
    ? `${area.d} L${w} ${h} L0 ${h} Z`
    : ''
  const firstTs = sampled[0]?.points[0]?.ts
  const lastTs = sampled[0]?.points.at(-1)?.ts
  const midTs = sampled[0]?.points[Math.floor((sampled[0].points.length - 1) / 2)]?.ts

  return (
    <div className="chart-wrap" aria-label="Equity curve">
      <div className="chart-y-labels">
        <span>{hi.toFixed(0)}</span>
        <span>{((hi + lo) / 2).toFixed(0)}</span>
        <span>{lo.toFixed(0)}</span>
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} className="equity-chart" role="img">
        <defs>
          <linearGradient id="eq-area" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#5564e8" stopOpacity=".22" />
            <stop offset="100%" stopColor="#5564e8" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[35, 92, 149, 206].map((gy) => (
          <line key={gy} x1="0" x2={w} y1={gy} y2={gy} className="grid-line" />
        ))}
        {area && <path d={areaFill} fill="url(#eq-area)" />}
        {paths.map((p) => (
          <path key={p.label} d={p.d} fill="none" stroke={p.color} strokeWidth="2.5" strokeLinecap="round" />
        ))}
      </svg>
      <div className="chart-x-labels">
        <span>{firstTs ? String(firstTs).slice(0, 10) : ''}</span>
        <span>{midTs ? String(midTs).slice(0, 10) : ''}</span>
        <span>{lastTs ? String(lastTs).slice(0, 10) : ''}</span>
      </div>
      <div className="chart-legend">
        {paths.map((p) => (
          <span key={p.label}>
            <i className="dot" style={{ background: p.color }} /> {p.label}
          </span>
        ))}
      </div>
    </div>
  )
}

const PRICE_SCALE_PREFIXES = ['sma', 'ema', 'bollinger', 'donchian']

export function PreviewChart({
  ohlc, indicators, longMarkers, shortMarkers,
}: {
  ohlc: { ts: string; open: number; high: number; low: number; close: number }[]
  indicators: Record<string, (number | null)[]>
  longMarkers: string[]
  shortMarkers: string[]
}) {
  if (!ohlc.length) return <p className="muted">No data for this window.</p>
  const closes = ohlc.map((p) => p.close).filter((n) => Number.isFinite(n))
  const priceLo = Math.min(...closes)
  const priceHi = Math.max(...closes)
  const pricePad = (priceHi - priceLo) || 1

  const indNames = Object.keys(indicators)
  const w = 720
  const h = 260
  const n = ohlc.length
  const t0 = Date.parse(ohlc[0].ts)
  const t1 = Date.parse(ohlc[n - 1].ts)
  const x = (i: number) => (n <= 1 ? 0 : (i / (n - 1)) * w)
  const tx = (ts: string) => {
    const t = Date.parse(ts)
    if (!Number.isFinite(t) || t1 === t0) return 0
    return ((t - t0) / (t1 - t0)) * w
  }
  const lo = priceLo - pricePad * 0.08
  const hi = priceHi + pricePad * 0.08
  const y = (v: number) => h - ((v - lo) / (hi - lo)) * h

  const pricePath = ohlc.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)} ${y(p.close).toFixed(1)}`).join(' ')

  const indPaths = indNames.map((name, ni) => {
    const vals = indicators[name]
    const priceScale = PRICE_SCALE_PREFIXES.some((p) => name.startsWith(p))
    const finite = vals.filter((v): v is number => v != null && Number.isFinite(v))
    const vlo = finite.length ? Math.min(...finite) : 0
    const vhi = finite.length ? Math.max(...finite) : 1
    const vpad = (vhi - vlo) || 1
    const scaleY = (v: number) => (priceScale ? y(v) : h - ((v - vlo) / vpad) * h)
    let d = ''
    let started = false
    vals.forEach((v, i) => {
      if (v == null || !Number.isFinite(v)) { started = false; return }
      d += `${started ? 'L' : 'M'}${x(i).toFixed(1)} ${scaleY(v).toFixed(1)} `
      started = true
    })
    return { name, d, color: COLORS[(ni + 1) % COLORS.length], normalized: !priceScale }
  })

  const longX = longMarkers.map(tx).filter((v) => v >= 0 && v <= w)
  const shortX = shortMarkers.map(tx).filter((v) => v >= 0 && v <= w)

  return (
    <div className="price-chart">
      <div className="price-y">
        <span>{hi.toFixed(0)}</span>
        <span>{((hi + lo) / 2).toFixed(0)}</span>
        <span>{lo.toFixed(0)}</span>
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-label="Strategy preview: price, indicators, and where entries would fire">
        {[35, 90, 145, 200].map((gy) => (
          <line key={gy} x1="0" x2={w} y1={gy} y2={gy} className="grid-line" />
        ))}
        <path d={pricePath} fill="none" stroke="#5564e8" strokeWidth="2" />
        {indPaths.map((p) => (
          <path key={p.name} d={p.d} fill="none" stroke={p.color} strokeWidth="1.6"
                strokeDasharray={p.normalized ? '4 3' : undefined} />
        ))}
        {longX.map((px, i) => (
          <polygon key={`l-${i}`} points={`${px - 4},${h - 2} ${px + 4},${h - 2} ${px},${h - 11}`} fill="#18a88a" />
        ))}
        {shortX.map((px, i) => (
          <polygon key={`s-${i}`} points={`${px - 4},2 ${px + 4},2 ${px},11`} fill="#ee6f62" />
        ))}
      </svg>
      <div className="price-x">
        <span>{String(ohlc[0].ts).slice(0, 10)}</span>
        <span>{String(ohlc[Math.floor((n - 1) / 2)].ts).slice(0, 10)}</span>
        <span>{String(ohlc[n - 1].ts).slice(0, 10)}</span>
      </div>
      <div className="legend">
        <span><i className="line" style={{ borderTopColor: '#5564e8' }} /> Close price</span>
        {indPaths.map((p) => (
          <span key={p.name}>
            <i className="line" style={{ borderTopColor: p.color, borderTopStyle: p.normalized ? 'dashed' : 'solid' }} />
            {' '}{p.name}{p.normalized ? ' (normalized)' : ''}
          </span>
        ))}
        <span><i className="dot buy" /> Long entry ({longX.length})</span>
        <span><i className="dot sell" /> Short entry ({shortX.length})</span>
      </div>
    </div>
  )
}

export function CloseChart({
  ohlc,
  trades,
}: {
  ohlc: { ts: string; close: number }[]
  trades?: Record<string, unknown>[]
}) {
  const points = downsample(ohlc, 300)
  const closes = points.map((p) => p.close).filter((n) => Number.isFinite(n))
  if (!closes.length) return <p className="muted">No OHLC series for this hypothesis.</p>
  const min = Math.min(...closes)
  const max = Math.max(...closes)
  const pad = (max - min) || 1
  const lo = min - pad * 0.08
  const hi = max + pad * 0.08
  const w = 720
  const h = 230
  const x = (i: number, n: number) => (n <= 1 ? 0 : (i / (n - 1)) * w)
  const y = (v: number) => h - ((v - lo) / (hi - lo)) * h
  const n = points.length
  const d = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(i, n).toFixed(1)} ${y(p.close).toFixed(1)}`).join(' ')
  const t0 = Date.parse(points[0].ts)
  const t1 = Date.parse(points[n - 1].ts)
  const tx = (ts: unknown) => {
    const t = Date.parse(String(ts))
    if (!Number.isFinite(t) || t1 === t0) return 0
    return ((t - t0) / (t1 - t0)) * w
  }
  const markers = (trades || []).slice(0, 80).map((t, i) => {
    const side = Number(t.side)
    return {
      key: i,
      x: tx(t.entry_ts),
      y: y(Number(t.entry_mid ?? t.entry ?? points[0].close)),
      up: side === 1,
    }
  })

  return (
    <div className="price-chart">
      <div className="price-y">
        <span>{hi.toFixed(0)}</span>
        <span>{((hi + lo) / 2).toFixed(0)}</span>
        <span>{lo.toFixed(0)}</span>
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-label="XAUUSD close with trade entries">
        {[35, 90, 145, 200].map((gy) => (
          <line key={gy} x1="0" x2={w} y1={gy} y2={gy} className="grid-line" />
        ))}
        <path d={d} fill="none" stroke="#5564e8" strokeWidth="2.5" />
        {markers.map((m) => (
          <circle key={m.key} cx={m.x} cy={m.y} r="4" fill="#fff" stroke={m.up ? '#18a88a' : '#ee6f62'} strokeWidth="2.5" />
        ))}
      </svg>
      <div className="price-x">
        <span>{String(points[0].ts).slice(0, 10)}</span>
        <span>{String(points[Math.floor((n - 1) / 2)].ts).slice(0, 10)}</span>
        <span>{String(points[n - 1].ts).slice(0, 10)}</span>
      </div>
      <div className="legend">
        <span><i className="dot buy" /> Long entry</span>
        <span><i className="dot sell" /> Short entry</span>
        <span><i className="line" /> XAUUSD close</span>
      </div>
    </div>
  )
}

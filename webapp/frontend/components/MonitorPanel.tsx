'use client'

import { useEffect, useState } from 'react'
import { Radar, CircleDot, Newspaper, AlertTriangle } from 'lucide-react'

interface Snapshot {
  running: boolean
  detail?: string
  ts?: string
  age_seconds?: number | null
  price?: number
  spread?: number
  session?: string
  features?: Record<string, number | null>
  patterns?: { name: string; firing: boolean; direction: number; note: string; detail: string }[]
  patterns_firing?: string[]
  pattern_lean?: number
  direction?: {
    available: boolean; p_up?: number; lean?: string; confidence?: number; horizon?: string
    top_drivers?: [string, number][]; model_oos_auc?: number; caveat?: string; detail?: string
  }
  news_calendar?: {
    blackout?: boolean; blackout_reason?: string; minutes_to_next_high?: number | null
    next_high?: { title: string; country: string; when_utc: string } | null
    upcoming_24h?: { in_min: number; title: string; country: string; impact: string }[]
  }
  news_sentiment?: {
    available?: boolean; tone_now?: number; tone_z?: number; vol_z?: number | null
    tone_mean_24h?: number; last_point_utc?: string
  }
  read?: { verdict?: string; notes?: string[]; tradeable?: boolean }
}

const f2 = (x: number | null | undefined, d = 2) =>
  x === null || x === undefined || Number.isNaN(x) ? '—' : x.toFixed(d)

export default function MonitorPanel() {
  const [s, setS] = useState<Snapshot | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    const load = () =>
      fetch('/api/monitor/snapshot')
        .then((r) => r.json())
        .then((d) => alive && setS(d))
        .catch((e) => alive && setErr(String(e)))
    load()
    const id = setInterval(load, 4000)
    return () => { alive = false; clearInterval(id) }
  }, [])

  const dir = s?.direction
  const cal = s?.news_calendar
  const sent = s?.news_sentiment
  const pUp = dir?.p_up ?? 0.5

  return (
    <div className="setup-main" style={{ display: 'grid', gap: 16 }}>
      <div className="rule-builder">
        <div className="section-title">
          <span><Radar size={16} style={{ verticalAlign: -3 }} /> Real-time monitor</span>
          <span className="muted" style={{ fontSize: 12 }}>features · patterns · direction lean · news</span>
        </div>
        {err && <p className="error">{err}</p>}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <CircleDot size={14} color={s?.running ? '#12b76a' : '#f04438'} />
          <strong>{s?.running ? 'running' : 'not running'}</strong>
          <span className="muted">
            {s?.age_seconds != null ? `updated ${s.age_seconds}s ago` : ''}
            {s?.session ? ` · ${s.session} session` : ''}
            {s?.price ? ` · ${f2(s.price)} · spread $${f2(s.spread, 3)}` : ''}
          </span>
        </div>
        {!s?.running && <p className="muted">{s?.detail || 'Start it:'} <code>python -m monitor</code></p>}
      </div>

      {/* --- composite read --- */}
      {s?.read && (
        <div className="rule-builder" style={{
          borderLeft: `4px solid ${cal?.blackout ? '#f04438' : s.read.tradeable ? '#12b76a' : '#98a2b3'}`,
        }}>
          <div className="section-title"><span>Read</span></div>
          <p style={{ fontSize: 16, fontWeight: 600, margin: '2px 0 8px' }}>
            {cal?.blackout && <AlertTriangle size={16} color="#f04438" style={{ verticalAlign: -3 }} />}{' '}
            {s.read.verdict}
          </p>
          {(s.read.notes || []).map((n, i) => <p key={i} className="muted" style={{ margin: '2px 0' }}>• {n}</p>)}
        </div>
      )}

      {/* --- direction lean --- */}
      <div className="rule-builder">
        <div className="section-title"><span>Direction lean ({dir?.horizon || '~1h'})</span></div>
        {!dir?.available ? (
          <p className="muted">{dir?.detail || 'No model — run python -m monitor.calibrate'}</p>
        ) : (
          <>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
              <span style={{
                fontSize: 30, fontWeight: 700,
                color: pUp > 0.55 ? '#12b76a' : pUp < 0.45 ? '#f04438' : '#475467',
              }}>
                {(pUp * 100).toFixed(1)}%
              </span>
              <span className="muted">P(up) · lean <strong>{dir.lean}</strong> · confidence {f2(dir.confidence, 2)}</span>
            </div>
            <div style={{ height: 8, borderRadius: 4, background: '#eee', margin: '8px 0', position: 'relative' }}>
              <div style={{
                position: 'absolute', left: `${Math.min(100, Math.max(0, pUp * 100))}%`,
                top: -3, width: 2, height: 14, background: '#111',
              }} />
              <div style={{ position: 'absolute', left: '50%', top: 0, width: 1, height: 8, background: '#bbb' }} />
            </div>
            <p className="muted" style={{ fontSize: 12 }}>
              drivers now: {(dir.top_drivers || []).map(([k, v]) => `${k} ${v >= 0 ? '+' : ''}${v}`).join(' · ')}
            </p>
            <p className="muted" style={{ fontSize: 12, color: '#b54708' }}>{dir.caveat}</p>
          </>
        )}
      </div>

      {/* --- patterns --- */}
      <div className="rule-builder">
        <div className="section-title">
          <span>Patterns</span>
          <span className="muted">net lean {s?.pattern_lean != null ? (s.pattern_lean > 0 ? `+${s.pattern_lean}` : s.pattern_lean) : '—'}</span>
        </div>
        <div style={{ display: 'grid', gap: 6 }}>
          {(s?.patterns || []).map((p) => (
            <div key={p.name} style={{ opacity: p.firing ? 1 : 0.4, fontSize: 13 }}>
              <span style={{
                display: 'inline-block', width: 8, height: 8, borderRadius: 8, marginRight: 8,
                background: p.firing ? (p.direction > 0 ? '#12b76a' : p.direction < 0 ? '#f04438' : '#98a2b3') : '#d0d5dd',
              }} />
              <strong>{p.name}</strong>{p.firing && p.detail ? ` — ${p.detail}` : ''}
              <div className="muted" style={{ fontSize: 11, marginLeft: 16 }}>{p.note}</div>
            </div>
          ))}
        </div>
      </div>

      {/* --- news --- */}
      <div className="rule-builder">
        <div className="section-title">
          <span><Newspaper size={15} style={{ verticalAlign: -2 }} /> News</span>
          <span className="muted" style={{ fontSize: 12 }}>ForexFactory calendar · GDELT tone</span>
        </div>
        {cal?.blackout && (
          <p style={{ color: '#b42318', fontWeight: 600 }}>
            BLACKOUT — {cal.blackout_reason}
          </p>
        )}
        <p className="muted">
          Next high-impact:{' '}
          {cal?.next_high
            ? `${cal.next_high.title} (${cal.next_high.country}) in ${f2(cal.minutes_to_next_high, 0)} min`
            : '—'}
        </p>
        {(cal?.upcoming_24h || []).length > 0 && (
          <ul style={{ fontSize: 12, margin: '4px 0', paddingLeft: 18 }}>
            {cal!.upcoming_24h!.map((e, i) => (
              <li key={i} className="muted">
                +{e.in_min}m — {e.title} ({e.country}) <em>{e.impact}</em>
              </li>
            ))}
          </ul>
        )}
        <p className="muted" style={{ marginTop: 6 }}>
          GDELT gold tone: {sent?.available ? (
            <>
              <strong>{f2(sent.tone_now, 2)}</strong> (24h mean {f2(sent.tone_mean_24h, 2)}, z {f2(sent.tone_z, 2)})
              {sent.vol_z != null && ` · coverage volume z ${f2(sent.vol_z, 2)}`}
            </>
          ) : 'unavailable'}
        </p>
      </div>

      {/* --- features --- */}
      <div className="rule-builder">
        <div className="section-title"><span>Key features</span></div>
        <div className="param-grid" style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(120px,1fr))', fontSize: 13 }}>
          {Object.entries(s?.features || {}).map(([k, v]) => (
            <div key={k}>
              <div className="muted" style={{ fontSize: 11 }}>{k}</div>
              <div style={{ fontWeight: 600 }}>{typeof v === 'number' ? f2(v, 4) : '—'}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

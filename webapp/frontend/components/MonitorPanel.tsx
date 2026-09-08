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
    session?: string; session_auc?: number | null; trust_now?: boolean
  }
  volatility?: {
    available: boolean; rv_pred_bps?: number; regime?: string; percentile?: number | null
    model_r2_oos?: number; tercile_acc_oos?: number; note?: string; detail?: string
  }
  event_proximity?: {
    ev_mins_to?: number; ev_next_weight?: number; ev_pre2h?: number; ev_window60?: number
    next_kind?: string | null; next_when_utc?: string | null
  }
  meta?: {
    available: boolean; p_dir?: number; primary_side?: string; p_correct?: number
    threshold?: number; act?: boolean; recommendation?: string; detail?: string
  }
  london?: {
    available: boolean; p_up?: number; lean?: string; at_decision_time?: boolean; reliable?: boolean
    horizon?: string; top_drivers?: [string, number][]; oos_auc?: number; note?: string; detail?: string
  }
  cross_asset?: Record<string, number | null>
  live_auc?: {
    available: boolean; n_resolved?: number; direction_live_auc?: number | null
    direction_live_hit?: number | null; meta_selected_hit?: number | null; meta_selected_n?: number
    london_live_auc?: number | null; detail?: string; note?: string
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
  const vol = s?.volatility
  const ev = s?.event_proximity
  const ca = s?.cross_asset
  const cal = s?.news_calendar
  const sent = s?.news_sentiment
  const pUp = dir?.p_up ?? 0.5
  const regClr: Record<string, string> = { quiet: '#12b76a', normal: '#475467', explosive: '#f04438' }

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

      {/* --- meta-label (the gate) + live accuracy --- */}
      <div className="rule-builder" style={{
        borderLeft: `4px solid ${s?.meta?.act ? '#12b76a' : '#98a2b3'}`,
      }}>
        <div className="section-title">
          <span>Meta-label — should we act?</span>
          {s?.live_auc?.available && (
            <span className="muted" style={{ fontSize: 12 }}>
              live: {s.live_auc.n_resolved} resolved
            </span>
          )}
        </div>
        {!s?.meta?.available ? (
          <p className="muted">{s?.meta?.detail || 'run python -m monitor.calibrate'}</p>
        ) : (
          <>
            <p style={{ fontSize: 15, fontWeight: 600, margin: '2px 0 6px' }}>
              {s.meta.recommendation}
            </p>
            <p className="muted" style={{ fontSize: 13 }}>
              P(direction call correct) <strong>{f2(s.meta.p_correct, 3)}</strong> vs
              threshold {f2(s.meta.threshold, 2)} · primary side {s.meta.primary_side}
              {' '}(P_dir {f2(s.meta.p_dir, 3)})
            </p>
            {s?.live_auc?.available ? (
              <p className="muted" style={{ fontSize: 12, marginTop: 6 }}>
                <strong>Live so far:</strong> direction hit {f2(s.live_auc.direction_live_hit, 3)}
                {s.live_auc.direction_live_auc != null && ` (AUC ${f2(s.live_auc.direction_live_auc, 3)})`}
                {s.live_auc.meta_selected_hit != null &&
                  ` · meta-selected hit ${f2(s.live_auc.meta_selected_hit, 3)} (n=${s.live_auc.meta_selected_n})`}
                {s.live_auc.london_live_auc != null && ` · London AUC ${f2(s.live_auc.london_live_auc, 3)}`}
              </p>
            ) : (
              <p className="muted" style={{ fontSize: 12, marginTop: 6 }}>
                {s?.live_auc?.detail || 'live accuracy accumulates as the monitor runs'}
              </p>
            )}
          </>
        )}
      </div>

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
            <p style={{ fontSize: 12, fontWeight: 600, color: dir.trust_now ? '#12b76a' : '#98a2b3' }}>
              {dir.session} session · OOS AUC {f2(dir.session_auc, 3)} ·{' '}
              {dir.trust_now ? 'worth reading here' : 'not reliable now — ignore the lean'}
            </p>
            <p className="muted" style={{ fontSize: 12, color: '#b54708' }}>{dir.caveat}</p>
          </>
        )}
      </div>

      {/* --- London continuation model --- */}
      {s?.london?.available && (
        <div className="rule-builder">
          <div className="section-title">
            <span>London model (13:00→17:00 UTC)</span>
            <span className="muted" style={{ fontSize: 12 }}>OOS AUC {f2(s.london.oos_auc, 3)}</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
            <span style={{
              fontSize: 22, fontWeight: 700,
              color: (s.london.p_up ?? 0.5) > 0.55 ? '#12b76a' : (s.london.p_up ?? 0.5) < 0.45 ? '#f04438' : '#475467',
            }}>
              {((s.london.p_up ?? 0.5) * 100).toFixed(1)}%
            </span>
            <span className="muted">P(up) · lean {s.london.lean}</span>
            {s.london.at_decision_time && (
              <span style={{ background: '#ecfdf3', color: '#027a48', border: '1px solid #a6f4c5',
                borderRadius: 6, padding: '1px 7px', fontSize: 11, fontWeight: 600 }}>
                DECISION TIME
              </span>
            )}
          </div>
          <p style={{ fontSize: 12, color: s.london.reliable ? undefined : '#b42318', fontWeight: s.london.reliable ? 400 : 600 }}>{s.london.note}</p>
        </div>
      )}

      {/* --- volatility regime --- */}
      <div className="rule-builder">
        <div className="section-title"><span>Volatility regime ({vol?.detail ? '' : '~1h'})</span></div>
        {!vol?.available ? (
          <p className="muted">{vol?.detail || 'No vol model — run python -m monitor.calibrate'}</p>
        ) : (
          <>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
              <span style={{ fontSize: 24, fontWeight: 700, color: regClr[vol.regime || 'normal'] }}>
                {(vol.regime || '—').toUpperCase()}
              </span>
              <span className="muted">
                ~{f2(vol.rv_pred_bps, 0)} bps predicted 1σ move
                {vol.percentile != null ? ` · ${(vol.percentile * 100).toFixed(0)}th pct` : ''}
              </span>
            </div>
            <p className="muted" style={{ fontSize: 12 }}>{vol.note}</p>
            {ev && (ev.ev_mins_to ?? 9e9) < 240 && (
              <p style={{ fontSize: 12, color: '#b54708' }}>
                {ev.next_kind || 'event'} in {f2(ev.ev_mins_to, 0)} min (weight {ev.ev_next_weight})
                {ev.ev_window60 ? ' — inside the ±60 min window' : ''}
              </p>
            )}
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
        {ca && (
          <p className="muted" style={{ fontSize: 12, marginTop: -4 }}>
            cross-asset · USD 15m {f2(ca.xa_usd_15m, 5)} · 30m {f2(ca.xa_usd_30m, 5)} · 60m {f2(ca.xa_usd_60m, 5)}
            {ca.xa_btc_60m != null && ` · BTC 60m ${f2(ca.xa_btc_60m, 4)}`}
            {' '}(USD↑ ≈ gold headwind)
          </p>
        )}
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

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
  candles?: { name: string; direction: number; note: string; detail: string }[]
  candle_lean?: number
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
    available: boolean; n?: number; n_resolved?: number; preliminary?: boolean
    direction_hit?: number | null; direction_hit_n?: number
    direction_hit_recent?: number | null; recent_n?: number
    always_one_way_baseline?: number | null; beats_trend_baseline?: boolean
    meta_selected_hit?: number | null; meta_selected_n?: number; meta_selected_hit_recent?: number | null
    direction_auc?: number | null; direction_auc_note?: string | null
    london_auc?: number | null; london_auc_n?: number
    detail?: string; note?: string
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
const pct = (x: number | null | undefined, d = 0) =>
  x === null || x === undefined || Number.isNaN(x) ? '—' : `${(x * 100).toFixed(d)}%`
const convWord = (c: number | null | undefined) =>
  c == null ? '—' : c < 0.08 ? 'very low' : c < 0.18 ? 'low' : c < 0.35 ? 'moderate' : 'high'

// technical feature key -> plain name
const FEAT: Record<string, string> = {
  ret_1h: 'move over last hour', ret_1d: 'move over last day',
  trend: 'trend direction (−2…+2)', ema_f_gap: 'distance above/below 20-bar avg',
  rsi: 'RSI (overbought >70 / oversold <30)', macd_hist: 'MACD momentum',
  atr_pct: 'how volatile vs history (0–1)', range_pos: 'position in 24h range (0=low, 1=high)',
  streak: 'up/down bar streak', london_drift_atr: 'London-session drift so far',
  ny_box_width_atr: 'NY opening-range width', ny_box_pos: 'position in the NY opening range',
}

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
          <span className="muted" style={{ fontSize: 12 }}>updates every few seconds · read-only</span>
        </div>
        {err && <p className="error">{err}</p>}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <CircleDot size={14} color={s?.running ? '#12b76a' : '#f04438'} />
          <strong>{s?.running ? 'live' : 'not running'}</strong>
          <span className="muted">
            {s?.age_seconds != null ? `last update ${s.age_seconds}s ago` : ''}
            {s?.session ? ` · ${s.session} trading session` : ''}
            {s?.price ? ` · gold ${f2(s.price)} · dealer spread $${f2(s.spread, 3)}` : ''}
          </span>
        </div>
        {!s?.running && <p className="muted">{s?.detail || 'Start it:'} <code>python -m monitor</code></p>}
        <p className="muted" style={{ fontSize: 12, marginTop: 6 }}>
          Reads the market, runs a few models, and gives a plain go / no-go call. The models are
          weak on purpose — a coin toss is 50%; these land in the mid-50s at best, and only on the
          small share of moments they're confident. Treat it as a nudge, not a signal.
        </p>
      </div>

      {/* --- composite read --- */}
      {s?.read && (
        <div className="rule-builder" style={{
          borderLeft: `4px solid ${cal?.blackout ? '#f04438' : s.read.tradeable ? '#12b76a' : '#98a2b3'}`,
        }}>
          <div className="section-title"><span>Bottom line</span></div>
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
          <span>Confidence filter — trade or skip?</span>
          <span className="muted" style={{ fontSize: 12 }}>a.k.a. the meta-model</span>
        </div>
        {!s?.meta?.available ? (
          <p className="muted">{s?.meta?.detail || 'run python -m monitor.calibrate'}</p>
        ) : (
          <>
            <p style={{ fontSize: 15, fontWeight: 600, margin: '2px 0 6px' }}>
              {s.meta.act
                ? `Confident enough — lean ${s.meta.primary_side?.toUpperCase()}`
                : 'Not confident enough — no trade'}
            </p>
            <p className="muted" style={{ fontSize: 13 }}>
              This checks whether the direction call is trustworthy right now.
              It's <strong>{pct(s.meta.p_correct)}</strong> sure the “{s.meta.primary_side}” call is right
              (it needs {pct(s.meta.threshold)} to say “go”). The raw model itself leans
              {' '}{s.meta.primary_side} at {pct(s.meta.p_dir)}.
            </p>
            <div style={{ borderTop: '1px solid var(--border,#eee)', marginTop: 8, paddingTop: 8 }}>
              <strong style={{ fontSize: 13 }}>Live scorecard </strong>
              {s?.live_auc?.available && s.live_auc.preliminary && (
                <span style={{ background: '#fffaeb', color: '#b54708', border: '1px solid #fedf89',
                  borderRadius: 6, padding: '1px 6px', fontSize: 11, fontWeight: 600 }}>
                  PRELIMINARY
                </span>
              )}
              {s?.live_auc?.available ? (
                <p className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                  {s.live_auc.n_resolved} calls graded (each ~1h after it was made).{' '}
                  Direction right <strong>{pct(s.live_auc.direction_hit)}</strong>
                  {s.live_auc.direction_hit_recent != null && s.live_auc.recent_n
                    ? ` overall, ${pct(s.live_auc.direction_hit_recent)} over the last ${s.live_auc.recent_n}`
                    : ''}
                  .
                  {s.live_auc.meta_selected_hit != null &&
                    ` High-confidence calls right ${pct(s.live_auc.meta_selected_hit)} (${s.live_auc.meta_selected_n} of them).`}
                  {s.live_auc.always_one_way_baseline != null && (
                    <> {' '}<span style={{ color: s.live_auc.beats_trend_baseline ? '#027a48' : '#b42318', fontWeight: 600 }}>
                      Blindly guessing the trend would have scored {pct(s.live_auc.always_one_way_baseline)} —
                      {s.live_auc.beats_trend_baseline ? ' the model is above that.' : ' the model is NOT clearly above that, so this is drift, not skill.'}
                    </span></>
                  )}
                  {s.live_auc.direction_auc != null
                    ? ` Ranking accuracy (AUC) ${f2(s.live_auc.direction_auc, 2)} — 0.50 is random.`
                    : s.live_auc.direction_auc_note ? ` (${s.live_auc.direction_auc_note})` : ''}
                  {' '}{s.live_auc.note}
                </p>
              ) : (
                <p className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                  {s?.live_auc?.detail || 'builds up as the monitor runs'} · each call is graded ~1h later against
                  what price actually did.
                </p>
              )}
            </div>
          </>
        )}
      </div>

      {/* --- direction lean --- */}
      <div className="rule-builder">
        <div className="section-title">
          <span>Where's price headed in the next hour?</span>
          <span className="muted" style={{ fontSize: 12 }}>the raw direction model</span>
        </div>
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
              <span className="muted">
                chance price is <strong>higher</strong> in ~1h · leaning <strong>{dir.lean}</strong> ·
                {' '}conviction {convWord(dir.confidence)}
              </span>
            </div>
            <div style={{ height: 8, borderRadius: 4, background: '#eee', margin: '8px 0', position: 'relative' }}>
              <div style={{
                position: 'absolute', left: `${Math.min(100, Math.max(0, pUp * 100))}%`,
                top: -3, width: 2, height: 14, background: '#111',
              }} />
              <div style={{ position: 'absolute', left: '50%', top: 0, width: 1, height: 8, background: '#bbb' }} />
            </div>
            <p className="muted" style={{ fontSize: 12 }}>
              what's pushing the call: {(dir.top_drivers || []).map(([k, v]) =>
                `${FEAT[k] || k} ${v >= 0 ? '↑' : '↓'}`).join(' · ')}
            </p>
            <p style={{ fontSize: 12, fontWeight: 600, color: dir.trust_now ? '#12b76a' : '#98a2b3' }}>
              {dir.trust_now
                ? `In the ${dir.session} session this model is ${pct(dir.session_auc)} accurate on unseen data — worth a look.`
                : `In the ${dir.session} session it's only ${pct(dir.session_auc)} accurate on unseen data — basically a coin toss, ignore the guess.`}
            </p>
          </>
        )}
      </div>

      {/* --- London continuation model --- */}
      {s?.london?.available && (
        <div className="rule-builder" style={{ opacity: s.london.reliable ? 1 : 0.75 }}>
          <div className="section-title">
            <span>London-session model (the 1pm→5pm UTC move)</span>
            <span className="muted" style={{ fontSize: 12 }}>
              {pct(s.london.oos_auc)} accurate on unseen data
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
            <span style={{
              fontSize: 22, fontWeight: 700,
              color: (s.london.p_up ?? 0.5) > 0.55 ? '#12b76a' : (s.london.p_up ?? 0.5) < 0.45 ? '#f04438' : '#475467',
            }}>
              {((s.london.p_up ?? 0.5) * 100).toFixed(1)}%
            </span>
            <span className="muted">chance the afternoon move is up · leaning {s.london.lean}</span>
            {s.london.at_decision_time && s.london.reliable && (
              <span style={{ background: '#ecfdf3', color: '#027a48', border: '1px solid #a6f4c5',
                borderRadius: 6, padding: '1px 7px', fontSize: 11, fontWeight: 600 }}>
                DECISION TIME
              </span>
            )}
          </div>
          <p style={{ fontSize: 12, color: s.london.reliable ? undefined : '#b42318', fontWeight: s.london.reliable ? 400 : 600 }}>
            {s.london.reliable ? s.london.note
              : `This idea didn't pan out — on data it never saw it was right only ${pct(s.london.oos_auc)} of the time (worse than a coin toss). Left visible for honesty; don't act on it.`}
          </p>
        </div>
      )}

      {/* --- volatility regime --- */}
      <div className="rule-builder">
        <div className="section-title">
          <span>How wild will the next hour be?</span>
          <span className="muted" style={{ fontSize: 12 }}>quiet / normal / wild</span>
        </div>
        {!vol?.available ? (
          <p className="muted">{vol?.detail || 'No vol model — run python -m monitor.calibrate'}</p>
        ) : (
          <>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 12 }}>
              <span style={{ fontSize: 24, fontWeight: 700, color: regClr[vol.regime || 'normal'] }}>
                {vol.regime === 'explosive' ? 'WILD' : (vol.regime || '—').toUpperCase()}
              </span>
              <span className="muted">
                expect a move of roughly <strong>{f2((vol.rv_pred_bps ?? 0) / 100, 2)}%</strong> either way
                {vol.percentile != null ? ` · bigger than ${(vol.percentile * 100).toFixed(0)}% of hours` : ''}
              </span>
            </div>
            <p className="muted" style={{ fontSize: 12 }}>
              The quiet/normal/wild call is right about {pct(vol.tercile_acc_oos)} of the time on unseen data
              (a random guess would be 33%). The exact % move is a rough estimate.
            </p>
            {ev && (ev.ev_mins_to ?? 9e9) < 240 && (
              <p style={{ fontSize: 12, color: '#b54708' }}>
                {ev.next_kind || 'a scheduled event'} in {f2(ev.ev_mins_to, 0)} min
                {ev.ev_window60 ? ' — within the hour, expect a jump' : ''}
              </p>
            )}
          </>
        )}
      </div>

      {/* --- patterns --- */}
      <div className="rule-builder">
        <div className="section-title">
          <span>Chart patterns</span>
          <span className="muted" style={{ fontSize: 12 }}>
            combined: {s?.pattern_lean == null ? '—' : s.pattern_lean > 0 ? 'bullish' : s.pattern_lean < 0 ? 'bearish' : 'neutral'}
          </span>
        </div>
        <p className="muted" style={{ fontSize: 12, marginTop: -4, marginBottom: 6 }}>
          Classic setups, each shown with what the project's own backtests found about it. Dim = not
          firing right now. None of these beat costs on their own — they're context.
        </p>
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

        <div style={{ borderTop: '1px solid var(--border,#eee)', marginTop: 10, paddingTop: 8 }}>
          <strong style={{ fontSize: 13 }}>Candlestick patterns on the current bar</strong>
          <p className="muted" style={{ fontSize: 12, margin: '2px 0 6px' }}>
            The full set of named candlestick figures (engulfing, hammer, stars, harami…). Detected
            for completeness — none is separately proven on gold; the project's indicator, S/R and
            SMC tests all came back flat. Context only.
          </p>
          {(s?.candles || []).length === 0 ? (
            <p className="muted" style={{ fontSize: 12 }}>none on the latest completed bar</p>
          ) : (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {(s?.candles || []).map((cd) => (
                <span key={cd.name} title={cd.detail} style={{
                  fontSize: 12, padding: '2px 8px', borderRadius: 6, fontWeight: 600,
                  background: cd.direction > 0 ? '#ecfdf3' : cd.direction < 0 ? '#fef3f2' : '#f2f4f7',
                  color: cd.direction > 0 ? '#027a48' : cd.direction < 0 ? '#b42318' : '#475467',
                }}>
                  {cd.name.replace(/_/g, ' ')}
                </span>
              ))}
            </div>
          )}
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
          Next market-moving release:{' '}
          {cal?.next_high
            ? `${cal.next_high.title} (${cal.next_high.country}) in ${f2(cal.minutes_to_next_high, 0)} min`
            : '—'}
          {' '}· the bot stands aside for 15 min either side of high-impact US news.
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
          News tone (gold coverage): {sent?.available ? (
            <>
              <strong>{f2(sent.tone_now, 2)}</strong> now vs {f2(sent.tone_mean_24h, 2)} 24h-average
              {sent.tone_z != null && ` — ${Math.abs(sent.tone_z) < 1 ? 'about normal' : sent.tone_z > 0 ? 'unusually positive' : 'unusually negative'}`}
            </>
          ) : 'unavailable (rate-limited, retries automatically)'}
        </p>
      </div>

      {/* --- features --- */}
      <div className="rule-builder">
        <div className="section-title">
          <span>What the models are looking at</span>
          <span className="muted" style={{ fontSize: 12 }}>raw inputs</span>
        </div>
        {ca && (
          <p className="muted" style={{ fontSize: 12, marginTop: -4 }}>
            Dollar strength over the last hour: <strong>{ca.xa_usd_60m != null && ca.xa_usd_60m > 0 ? 'rising' : ca.xa_usd_60m != null ? 'falling' : '—'}</strong>
            {' '}(a stronger dollar is usually a headwind for gold)
            {ca.xa_btc_60m != null && ` · Bitcoin ${ca.xa_btc_60m > 0 ? 'up' : 'down'} ${f2(Math.abs(ca.xa_btc_60m) * 100, 1)}% (risk mood)`}
          </p>
        )}
        <div className="param-grid" style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', fontSize: 13 }}>
          {Object.entries(s?.features || {}).map(([k, v]) => (
            <div key={k}>
              <div className="muted" style={{ fontSize: 11 }}>{FEAT[k] || k}</div>
              <div style={{ fontWeight: 600 }}>{typeof v === 'number' ? f2(v, 4) : '—'}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

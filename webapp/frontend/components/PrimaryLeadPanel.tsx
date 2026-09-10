'use client'

import { useEffect, useState } from 'react'
import { FlaskConical, AlertTriangle, Lock, LockOpen } from 'lucide-react'
import { fetchPrimaryLeadStatus, type PrimaryLeadStatus, type PrimaryLeadBook } from '@/lib/api'

const card: React.CSSProperties = {
  border: '1px solid var(--border, #2a2a2a)', borderRadius: 10, padding: '14px 16px',
  background: 'var(--panel, #161616)',
}

function verdictColor(v: string): string {
  if (v.startsWith('PASS')) return '#3fb950'
  if (v.startsWith('FAIL')) return '#f85149'
  return '#8b949e'
}

function Book({ name, b }: { name: string; b: PrimaryLeadBook }) {
  return (
    <div style={card}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <strong style={{ fontSize: 15 }}>{name} book</strong>
        <span style={{ fontSize: 12, fontWeight: 700, color: verdictColor(b.verdict) }}>{b.verdict}</span>
      </div>
      <table style={{ width: '100%', fontSize: 13, marginTop: 8, borderCollapse: 'collapse' }}>
        <tbody>
          <tr><td style={{ opacity: 0.7 }}>resolved / open</td><td style={{ textAlign: 'right' }}>{b.n_resolved} / {b.n_open}</td></tr>
          <tr><td style={{ opacity: 0.7 }}>mean net (σ)</td><td style={{ textAlign: 'right' }}>{b.mean_net_sigma ?? '—'}</td></tr>
          <tr><td style={{ opacity: 0.7 }}>95% CI (net)</td><td style={{ textAlign: 'right' }}>{b.ci[0] ?? '—'} … {b.ci[1] ?? '—'}</td></tr>
          <tr><td colSpan={2} style={{ borderTop: '1px solid var(--border,#2a2a2a)', paddingTop: 6, opacity: 0.55, fontSize: 12 }}>
            historical (already-touched, NOT validation): gross {b.expect.gross}σ · net {b.expect.net}σ · CI [{b.expect.ci[0]}, {b.expect.ci[1]}] · win {b.expect.win}%
          </td></tr>
        </tbody>
      </table>
    </div>
  )
}

export default function PrimaryLeadPanel() {
  const [s, setS] = useState<PrimaryLeadStatus | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    const load = () => fetchPrimaryLeadStatus().then(d => { if (live) { setS(d); setErr(null) } })
      .catch(e => { if (live) setErr(String(e)) })
    load()
    const t = setInterval(load, 60_000)
    return () => { live = false; clearInterval(t) }
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14, maxWidth: 860 }}>
      <div style={{ ...card, borderColor: '#8957e5', background: 'rgba(137,87,229,0.08)' }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6 }}>
          <AlertTriangle size={16} color="#d29922" />
          <strong>Forward-paper observation — no edge established</strong>
        </div>
        <p style={{ margin: 0, fontSize: 13, lineHeight: 1.5, opacity: 0.9 }}>
          {s?.disclaimer ??
            'A frozen, pre-registered hypothesis under forward-paper observation. Nothing here trades. Every earlier candidate that reached this stage in this project later failed forward or out-of-sample.'}
        </p>
        {s?.spec && <p style={{ margin: '6px 0 0', fontSize: 12, opacity: 0.6 }}>spec: {s.spec}</p>}
      </div>

      {err && <div style={{ ...card, borderColor: '#f85149', color: '#f85149' }}>{err}</div>}
      {s?.error && <div style={{ ...card, borderColor: '#f85149', color: '#f85149' }}>{s.error}</div>}

      {s && !s.error && (
        <>
          <div style={card}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              {s.gate_open ? <LockOpen size={16} color="#3fb950" /> : <Lock size={16} color="#8b949e" />}
              <strong style={{ fontSize: 15 }}>Regime gate</strong>
            </div>
            <div style={{ fontSize: 14, marginTop: 8 }}>{s.regime}</div>
            <div style={{ fontSize: 13, opacity: 0.7, marginTop: 4 }}>
              20-day realised-vol percentile: <strong>{s.rv20_pctile == null ? '—' : (s.rv20_pctile * 100).toFixed(0) + 'th'}</strong>
              {' · '}gate opens only in the bottom third
            </div>
            <div style={{ fontSize: 12, opacity: 0.6, marginTop: 4 }}>
              ATR14 {s.atr14 ?? '—'} (floor {s.atr_floor}) · as of {s.as_of_bar} ({s.bar_age_min}m ago)
            </div>
          </div>

          <div style={{ ...card, borderColor: s.signal_now ? '#3fb950' : undefined }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <FlaskConical size={16} color={s.signal_now ? '#3fb950' : '#8b949e'} />
              <strong style={{ fontSize: 15 }}>Signal on the latest bar</strong>
            </div>
            <div style={{ fontSize: 16, fontWeight: 700, marginTop: 8, color: s.signal_now ? '#3fb950' : undefined }}>
              {s.signal_now
                ? `PAPER SIGNAL — ${s.signal_side === 1 ? 'LONG (new 1-day high, low-vol regime)' : 'SHORT (new 1-day low, low-vol regime)'}`
                : 'No signal'}
            </div>
            <div style={{ fontSize: 13, opacity: 0.7, marginTop: 6 }}>
              new 1-day extreme on latest bar: {s.a3_on_latest_bar ? 'yes' : 'no'}
              {s.last_a3_anchor?.ts && <> · last extreme: {s.last_a3_anchor.ts} ({s.last_a3_anchor.side === 1 ? 'high' : 'low'})</>}
            </div>
            <div style={{ fontSize: 12, opacity: 0.6, marginTop: 4 }}>
              last historical signal: {s.last_historical_signal ?? '—'} · signals since {s.F_start}: <strong>{s.signals_since_F}</strong>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(320px,1fr))', gap: 12 }}>
            {s.books && Object.entries(s.books).map(([k, b]) => <Book key={k} name={k} b={b} />)}
          </div>

          <p style={{ fontSize: 12, opacity: 0.55, margin: 0 }}>
            Verdict stays INCONCLUSIVE until ≥150 resolved signals per book (~10 months). PASS requires mean net ≥ +0.05σ
            with a CI lower bound above 0 and no quarter carrying &gt;60% of P&amp;L; FAIL requires mean net ≤ 0 with a CI
            upper bound below +0.10σ. A PASS only earns "keep paper trading" — never live.
          </p>
        </>
      )}
    </div>
  )
}

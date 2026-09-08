'use client'

import { useEffect, useState } from 'react'
import { Activity, CircleDot, RefreshCw } from 'lucide-react'
import {
  fetchLiveBotStatus,
  fetchLiveBotDecisions,
  fetchLiveBotTrades,
  type LiveBotStatus,
  type LiveBotDecision,
  type LiveBotTrades,
} from '@/lib/api'

const n2 = (x: number | null | undefined, d = 2) =>
  x === null || x === undefined || Number.isNaN(x) ? '—' : x.toFixed(d)
const money = (x: number | null | undefined) =>
  x === null || x === undefined ? '—' : (x >= 0 ? '+$' : '−$') + Math.abs(x).toFixed(2)

export default function LiveBotPanel() {
  const [status, setStatus] = useState<LiveBotStatus | null>(null)
  const [decisions, setDecisions] = useState<LiveBotDecision[]>([])
  const [trades, setTrades] = useState<LiveBotTrades | null>(null)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    const load = () => {
      fetchLiveBotStatus().then((s) => alive && setStatus(s)).catch((e) => alive && setErr(String(e)))
      fetchLiveBotDecisions(40).then((d) => alive && setDecisions(d)).catch(() => {})
      fetchLiveBotTrades().then((t) => alive && setTrades(t)).catch(() => {})
    }
    load()
    const id = setInterval(load, 3000)
    return () => { alive = false; clearInterval(id) }
  }, [])

  const running = status?.running
  const acc = status?.account
  const s = trades?.summary

  return (
    <div className="setup-main" style={{ display: 'grid', gap: 16 }}>
      <div className="rule-builder">
        <div className="section-title">
          <span><Activity size={16} style={{ verticalAlign: -3 }} /> H1 execution bot</span>
          <span className="muted" style={{ fontSize: 12 }}>
            <RefreshCw size={11} style={{ verticalAlign: -1 }} /> live view · read-only
          </span>
        </div>

        {err && <p className="error">{err}</p>}

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
          <CircleDot size={14} color={running ? '#12b76a' : '#f04438'} />
          <strong>{running ? 'running' : 'not running'}</strong>
          <span className="muted">
            {status?.mode ? `${status.mode} mode` : ''}
            {status?.age_seconds != null ? ` · updated ${status.age_seconds}s ago` : ''}
          </span>
          {acc?.is_live && (
            <span style={{ background: '#fef3f2', color: '#b42318', border: '1px solid #fecdca',
              borderRadius: 6, padding: '1px 7px', fontSize: 12, fontWeight: 600 }}>
              LIVE ACCOUNT
            </span>
          )}
        </div>

        {!running && (
          <p className="muted">
            {status?.detail || 'Start it from a terminal:'} <code>python -m livebot</code> (paper mode).
          </p>
        )}

        {acc && (
          <p className="muted" style={{ fontSize: 12, marginTop: 0 }}>
            {acc.broker} · {acc.server} · #{acc.login} · bal {n2(acc.balance)} {acc.currency}
            {' · '}algo trading {acc.trade_allowed ? 'ON' : 'off'}
          </p>
        )}
      </div>

      {/* --- today --- */}
      <div className="rule-builder">
        <div className="section-title"><span>Today ({status?.symbol || 'XAUUSD'})</span></div>
        <div className="param-grid" style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(130px,1fr))' }}>
          <Stat label="UTC now" value={status?.now_utc?.slice(11, 16) ?? '—'} />
          <Stat label="Price" value={n2(status?.price)} />
          <Stat label="Spread" value={`$${n2(status?.spread, 3)}`}
                tone={status?.spread != null && status.spread > 0.35 ? 'warn' : undefined} />
          <Stat label="Box high" value={n2(status?.box?.high)} />
          <Stat label="Box low" value={n2(status?.box?.low)} />
          <Stat label="Box width" value={status?.box ? `$${n2(status.box.width)}` : '—'} />
          <Stat label="Trades today" value={String(status?.trades_today ?? 0)} />
          <Stat label="P&L today" value={money(status?.realised_today)} />
        </div>
        <p className="muted" style={{ marginTop: 8 }}>
          <strong>State:</strong> {status?.state ?? '—'}
          {status?.kill_switch && ' · KILL SWITCH ON'}
          {status?.armed_today && ' · armed today'}
        </p>
        {status?.position && (
          <p style={{ marginTop: 4 }}>
            <strong>Position:</strong> {status.position.side} @ {n2(status.position.entry)} ·
            SL {n2(status.position.sl)} · unrealised {money(status.position.unrealised)}
          </p>
        )}
      </div>

      {/* --- realised vs backtest --- */}
      <div className="rule-builder">
        <div className="section-title"><span>Realised (paper) vs backtest</span></div>
        {!s ? (
          <p className="muted">No closed trades yet. H1 fires ~once/day; give it a few sessions.</p>
        ) : (
          <>
            <div className="param-grid" style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(120px,1fr))' }}>
              <Stat label="Trades" value={String(s.n)} />
              <Stat label="Win rate" value={s.win_rate != null ? `${(s.win_rate * 100).toFixed(0)}%` : '—'} />
              <Stat label="Exp net / trade" value={money(s.exp_net)}
                    tone={s.exp_net != null ? (s.exp_net >= 0 ? 'good' : 'warn') : undefined} />
              <Stat label="Exp gross / trade" value={money(s.exp_gross)} />
              <Stat label="Profit factor" value={n2(s.pf)} />
              <Stat label="Cum net" value={money(s.cum_net)}
                    tone={s.cum_net >= 0 ? 'good' : 'warn'} />
              <Stat label="Avg spread" value={`$${n2(s.avg_entry_spread, 3)}`} />
              <Stat label="Avg slippage" value={`$${n2(s.avg_slippage, 3)}`} />
            </div>
            <p className="muted" style={{ marginTop: 10 }}>
              Effective round-trip cost <strong>${n2(s.effective_cost, 3)}</strong> vs backtest
              breakeven <strong>${s.breakeven_spread.toFixed(2)}</strong> —{' '}
              <span style={{ color: s.edge_intact ? '#12b76a' : '#f04438', fontWeight: 600 }}>
                {s.edge_intact ? 'BELOW breakeven (edge intact)' : 'ABOVE breakeven (edge eroded)'}
              </span>
              . Backtest gross ${s.backtest_gross.toFixed(3)}/trade. Needs ~60–100 trades to trust.
            </p>
          </>
        )}
      </div>

      {/* --- decision feed --- */}
      <div className="rule-builder">
        <div className="section-title"><span>Decision feed</span></div>
        <div style={{ maxHeight: 320, overflowY: 'auto', fontFamily: 'ui-monospace,Menlo,monospace', fontSize: 12 }}>
          {decisions.length === 0 && <p className="muted">no events yet</p>}
          {decisions.map((d, i) => (
            <div key={i} style={{ padding: '3px 0', borderBottom: '1px solid var(--border,#eee)' }}>
              <span className="muted">{String(d.ts).slice(11, 19)}</span>{' '}
              <strong>{d.event || d.intent}</strong>{' '}
              {d.status ? `— ${d.status}` : ''}
              {Object.entries(d)
                .filter(([k]) => !['ts', 'mode', 'event', 'intent', 'status'].includes(k))
                .map(([k, v]) => ` ${k}=${v}`)
                .join('')}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: 'good' | 'warn' }) {
  const color = tone === 'good' ? '#12b76a' : tone === 'warn' ? '#f04438' : undefined
  return (
    <div>
      <div className="muted" style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.4 }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 600, color }}>{value}</div>
    </div>
  )
}

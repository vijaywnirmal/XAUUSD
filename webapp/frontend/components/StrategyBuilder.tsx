'use client'

import { useEffect, useState } from 'react'
import { Eye, FolderOpen, Play, Plus, Save, Sparkles, Trash2, X } from 'lucide-react'
import type { BacktestResult, BuilderPreview, IndicatorInfo, ParsedRule, SavedStrategySummary } from '@/lib/api'
import {
  deleteSavedStrategy,
  fetchSavedStrategy,
  listSavedStrategies,
  parseStrategyText,
  previewBuilder,
  runBuilder,
  saveStrategy,
} from '@/lib/api'
import { PreviewChart } from '@/components/Charts'

interface Rule {
  indicator: string
  indParams: Record<string, number>
  output: string
  op: string
  rightKind: 'value' | 'price' | 'indicator'
  value: number
  field: string
  rightIndicator: string
  rightIndParams: Record<string, number>
  rightOutput: string
}

const OPS = ['>', '<', '>=', '<=', '==', 'cross_above', 'cross_below']

function defaultRule(indicators: IndicatorInfo[]): Rule {
  const ind = indicators[0]
  return {
    indicator: ind?.id || 'rsi',
    indParams: Object.fromEntries((ind?.params || []).map((p) => [p.name, p.default])),
    output: ind?.outputs[0] || 'rsi',
    op: '<',
    rightKind: 'value',
    value: 30,
    field: 'close',
    rightIndicator: ind?.id || 'rsi',
    rightIndParams: Object.fromEntries((ind?.params || []).map((p) => [p.name, p.default])),
    rightOutput: ind?.outputs[0] || 'rsi',
  }
}

export default function StrategyBuilder({
  indicators,
  timeframe,
  split,
  start,
  end,
  sizeMode,
  sizeLots,
  riskPct,
  initialEquity,
  slippageTicks,
  onRun,
}: {
  indicators: IndicatorInfo[]
  timeframe: string
  split: string
  start?: string | null
  end?: string | null
  sizeMode?: string
  sizeLots?: number
  riskPct?: number
  initialEquity?: number
  slippageTicks?: number
  onRun: (result: BacktestResult) => void
}) {
  const [longRules, setLongRules] = useState<Rule[]>(() => [defaultRule(indicators)])
  const [shortRules, setShortRules] = useState<Rule[]>([])
  const [stopMode, setStopMode] = useState<'fixed' | 'atr'>('fixed')
  const [stopDist, setStopDist] = useState<number | null>(5)
  const [stopAtrMult, setStopAtrMult] = useState<number | null>(30)
  const [stopAtrN, setStopAtrN] = useState(14)
  const [targetMode, setTargetMode] = useState<'fixed' | 'atr'>('fixed')
  const [targetDist, setTargetDist] = useState<number | null>(10)
  const [targetAtrMult, setTargetAtrMult] = useState<number | null>(30)
  const [targetAtrN, setTargetAtrN] = useState(14)
  const [sessionFlat, setSessionFlat] = useState<number | null>(21)
  // Entry time-of-day window (UTC hours): new entries only fire when the bar's
  // hour is in [entryStart, entryEnd). null/null = no restriction. Distinct
  // from sessionFlat, which is when an *open* trade is force-closed.
  const [entryStart, setEntryStart] = useState<number | null>(null)
  const [entryEnd, setEntryEnd] = useState<number | null>(null)
  const [oneTradePerDay, setOneTradePerDay] = useState(true)
  // Trailing stop: once a trade is `trailActivateR` R in profit, the stop
  // ratchets to `trailDist` behind the running extreme (close, or high/low)
  // instead of staying fixed — lets winners run rather than capping at a
  // fixed target. null trailDist = no trailing (fixed stop/target only).
  const [trailDist, setTrailDist] = useState<number | null>(null)
  const [trailActivateR, setTrailActivateR] = useState<number | null>(1)
  const [trailRef, setTrailRef] = useState<'close' | 'hl'>('close')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [nlText, setNlText] = useState('')
  const [nlLoading, setNlLoading] = useState(false)
  const [nlError, setNlError] = useState<string | null>(null)
  const [nlNotes, setNlNotes] = useState<string | null>(null)
  const [nlBackend, setNlBackend] = useState<string | null>(null)

  const [preview, setPreview] = useState<BuilderPreview | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewError, setPreviewError] = useState<string | null>(null)

  const [savedList, setSavedList] = useState<SavedStrategySummary[]>([])
  const [savedLoading, setSavedLoading] = useState(false)
  const [savedError, setSavedError] = useState<string | null>(null)
  const [saveName, setSaveName] = useState('')
  const [currentSavedId, setCurrentSavedId] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveMsg, setSaveMsg] = useState<string | null>(null)

  const refreshSavedList = () => {
    listSavedStrategies().then(setSavedList).catch(() => {})
  }
  useEffect(() => { refreshSavedList() }, [])

  useEffect(() => {
    if (!indicators.length) return
    setLongRules([defaultRule(indicators)])
  }, [indicators])

  const toRule = (r: ParsedRule): Rule => {
    const ind = indicators.find((i) => i.id === r.indicator)
    const rightInd = indicators.find((i) => i.id === r.rightIndicator) || ind
    return {
      indicator: r.indicator,
      indParams: r.indParams,
      output: r.output || ind?.outputs[0] || r.indicator,
      op: r.op,
      rightKind: r.rightKind,
      value: r.value,
      field: r.field || 'close',
      rightIndicator: r.rightIndicator || rightInd?.id || 'ema',
      rightIndParams: r.rightIndParams || {},
      rightOutput: r.rightOutput || rightInd?.outputs[0] || 'ema',
    }
  }

  // Reverse of toOperand/toRight below — rebuilds a Rule from the raw
  // {left, op, right} shape a saved strategy's spec stores on disk.
  const ruleFromSpec = (item: { left: any; op: string; right: any }): Rule => {
    const left = item.left
    const right = item.right
    const ind = indicators.find((i) => i.id === left.id)
    const rightIsIndicator = right.kind === 'indicator'
    const rightInd = rightIsIndicator ? indicators.find((i) => i.id === right.id) : undefined
    return {
      indicator: left.id,
      indParams: left.params || {},
      output: left.output || ind?.outputs[0] || left.id,
      op: item.op,
      rightKind: right.kind,
      value: right.kind === 'value' ? right.value : 0,
      field: right.kind === 'price' ? right.field : 'close',
      rightIndicator: rightIsIndicator ? right.id : (ind?.id || 'ema'),
      rightIndParams: rightIsIndicator ? (right.params || {}) : {},
      rightOutput: rightIsIndicator ? (right.output || rightInd?.outputs[0] || right.id) : (ind?.outputs[0] || 'ema'),
    }
  }

  const toOperand = (rule: Rule) => ({ kind: 'indicator', id: rule.indicator, params: rule.indParams, output: rule.output })
  const toRight = (rule: Rule) => {
    if (rule.rightKind === 'value') return { kind: 'value', value: rule.value }
    if (rule.rightKind === 'indicator') return { kind: 'indicator', id: rule.rightIndicator, params: rule.rightIndParams, output: rule.rightOutput }
    return { kind: 'price', field: rule.field }
  }

  const buildSpec = (long: Rule[], short: Rule[], stop: number | null, target: number | null,
                      flat: number | null, oneTrade: boolean,
                      trailD: number | null = trailDist, trailR: number | null = trailActivateR,
                      trailF: 'close' | 'hl' = trailRef,
                      entryS: number | null = entryStart, entryE: number | null = entryEnd) => ({
    long_rules: long.map((r) => ({ left: toOperand(r), op: r.op, right: toRight(r) })),
    long_logic: 'AND',
    short_rules: short.map((r) => ({ left: toOperand(r), op: r.op, right: toRight(r) })),
    short_logic: 'AND',
    entry_start_hour_utc: entryS,
    entry_end_hour_utc: entryE,
    bracket: {
      stop_mode: stopMode, stop_dist: stop, stop_atr_mult: stopAtrMult, stop_atr_n: stopAtrN,
      target_mode: targetMode, target_dist: target, target_atr_mult: targetAtrMult, target_atr_n: targetAtrN,
      session_flat_hour_utc: flat,
      trail_dist: trailD, trail_activate_r: trailD != null ? trailR : null, trail_ref: trailF,
    },
    bt: {
      one_trade_per_day: oneTrade,
      size_mode: sizeMode ?? 'fixed',
      size_lots: sizeLots ?? 0.01,
      risk_pct: riskPct ?? 0.005,
      initial_equity: initialEquity ?? 1000,
      slippage_ticks: slippageTicks ?? 1,
    },
  })

  const runPreview = async (long: Rule[], short: Rule[], stop: number | null, target: number | null,
                             flat: number | null, oneTrade: boolean,
                             entryS: number | null = entryStart, entryE: number | null = entryEnd) => {
    setPreviewLoading(true)
    setPreviewError(null)
    try {
      const spec = buildSpec(long, short, stop, target, flat, oneTrade,
                             trailDist, trailActivateR, trailRef, entryS, entryE)
      setPreview(await previewBuilder(spec, timeframe, split, start, end))
    } catch (e) {
      setPreviewError(e instanceof Error ? e.message : String(e))
    } finally {
      setPreviewLoading(false)
    }
  }

  const parseWithAI = async () => {
    setNlLoading(true)
    setNlError(null)
    setNlNotes(null)
    setNlBackend(null)
    try {
      const parsed = await parseStrategyText(nlText)
      const long = parsed.long_rules.length ? parsed.long_rules.map(toRule) : []
      const short = parsed.short_rules.map(toRule)
      const stop = parsed.stop_dist ?? stopDist
      const target = parsed.target_dist ?? targetDist
      const flat = parsed.session_flat_hour_utc ?? sessionFlat
      setLongRules(long)
      setShortRules(short)
      if (parsed.stop_dist != null) setStopDist(parsed.stop_dist)
      if (parsed.target_dist != null) setTargetDist(parsed.target_dist)
      if (parsed.session_flat_hour_utc != null) setSessionFlat(parsed.session_flat_hour_utc)
      setEntryStart(parsed.entry_start_hour_utc)
      setEntryEnd(parsed.entry_end_hour_utc)
      setTrailDist(parsed.trail_dist)
      if (parsed.trail_activate_r != null) setTrailActivateR(parsed.trail_activate_r)
      if (parsed.trail_ref) setTrailRef(parsed.trail_ref)
      setOneTradePerDay(parsed.one_trade_per_day)
      setNlNotes(parsed.notes || null)
      setNlBackend(parsed.backend || null)
      // Plot it immediately so the user can confirm before running. Pass the
      // just-parsed entry window explicitly — React state set above hasn't
      // flushed yet, so buildSpec's closure would still see the old values.
      await runPreview(long, short, stop, target, flat, parsed.one_trade_per_day,
                       parsed.entry_start_hour_utc, parsed.entry_end_hour_utc)
    } catch (e) {
      setNlError(e instanceof Error ? e.message : String(e))
    } finally {
      setNlLoading(false)
    }
  }

  const run = async () => {
    setLoading(true)
    setError(null)
    try {
      const spec = buildSpec(longRules, shortRules, stopDist, targetDist, sessionFlat, oneTradePerDay)
      onRun(await runBuilder(spec, timeframe, split, start, end))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async (asNew = false) => {
    const name = saveName.trim()
    if (!name) {
      setSavedError('Give the strategy a name first.')
      return
    }
    setSaving(true)
    setSavedError(null)
    setSaveMsg(null)
    try {
      const spec = buildSpec(longRules, shortRules, stopDist, targetDist, sessionFlat, oneTradePerDay)
      const record = await saveStrategy(name, spec, timeframe, split, start, end, asNew ? undefined : currentSavedId || undefined)
      setCurrentSavedId(record.id)
      setSaveMsg(asNew || !currentSavedId ? `Saved as "${name}".` : `Updated "${name}".`)
      refreshSavedList()
    } catch (e) {
      setSavedError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  const handleLoad = async (id: string) => {
    setSavedLoading(true)
    setSavedError(null)
    setSaveMsg(null)
    try {
      const record = await fetchSavedStrategy(id)
      const spec = record.spec as any
      setLongRules((spec.long_rules || []).map(ruleFromSpec))
      setShortRules((spec.short_rules || []).map(ruleFromSpec))
      const b = spec.bracket || {}
      setStopMode(b.stop_mode || 'fixed')
      setStopDist(b.stop_dist ?? null)
      setStopAtrMult(b.stop_atr_mult ?? null)
      setStopAtrN(b.stop_atr_n ?? 14)
      setTargetMode(b.target_mode || 'fixed')
      setTargetDist(b.target_dist ?? null)
      setTargetAtrMult(b.target_atr_mult ?? null)
      setTargetAtrN(b.target_atr_n ?? 14)
      setSessionFlat(b.session_flat_hour_utc ?? null)
      setEntryStart(spec.entry_start_hour_utc ?? null)
      setEntryEnd(spec.entry_end_hour_utc ?? null)
      setTrailDist(b.trail_dist ?? null)
      setTrailActivateR(b.trail_activate_r ?? 1)
      setTrailRef(b.trail_ref || 'close')
      setOneTradePerDay(!!(spec.bt || {}).one_trade_per_day)
      setCurrentSavedId(record.id)
      setSaveName(record.name)
      setSaveMsg(`Loaded "${record.name}".`)
    } catch (e) {
      setSavedError(e instanceof Error ? e.message : String(e))
    } finally {
      setSavedLoading(false)
    }
  }

  const handleDelete = async (id: string, name: string) => {
    if (!window.confirm(`Delete saved strategy "${name}"? This can't be undone.`)) return
    try {
      await deleteSavedStrategy(id)
      if (id === currentSavedId) setCurrentSavedId(null)
      refreshSavedList()
    } catch (e) {
      setSavedError(e instanceof Error ? e.message : String(e))
    }
  }

  if (!indicators.length) return <p className="muted">Loading indicators…</p>

  return (
    <div>
      <div className="rule-builder nl-builder">
        <div className="rule-head"><span>Describe your strategy</span></div>
        <p className="muted" style={{ marginTop: -6, marginBottom: 10 }}>
          Write it in plain English — AI translates it into the rules below for you to review before running.
        </p>
        <textarea
          className="nl-textarea"
          rows={3}
          placeholder="e.g. Go long when price closes above the 20 EMA and RSI(14) is below 40. Go short on the opposite. $5 stop, $10 target, flat by 8pm UTC."
          value={nlText}
          onChange={(e) => setNlText(e.target.value)}
        />
        <button className="ghost-btn" disabled={nlLoading || !nlText.trim()} onClick={parseWithAI}>
          <Sparkles size={14} /> {nlLoading ? 'Parsing…' : 'Parse with AI'}
        </button>
        {nlError && <p className="error">{nlError}</p>}
        {nlBackend && <p className="muted" style={{ marginTop: 8 }}>Parsed via: <strong>{nlBackend}</strong></p>}
        {nlNotes && <p className="muted" style={{ marginTop: 4 }}>AI notes: {nlNotes}</p>}
      </div>

      <div className="rule-builder">
        <div className="rule-head"><span>Save this strategy</span></div>
        <p className="muted" style={{ marginTop: -6, marginBottom: 10 }}>
          Persists the rules, bracket, and trailing-stop settings above to disk — reload it later or on another
          run without rebuilding it.
        </p>
        <div className="param-grid" style={{ alignItems: 'end' }}>
          <label className="param-field" style={{ minWidth: 220 }}>
            Name
            <input
              type="text"
              placeholder="e.g. My EMA/RSI cross"
              value={saveName}
              onChange={(e) => setSaveName(e.target.value)}
            />
          </label>
          <button className="ghost-btn" disabled={saving} onClick={() => handleSave(false)}>
            <Save size={14} /> {saving ? 'Saving…' : currentSavedId ? 'Update saved' : 'Save strategy'}
          </button>
          {currentSavedId && (
            <button className="ghost-btn" disabled={saving} onClick={() => handleSave(true)}>
              <Save size={14} /> Save as new
            </button>
          )}
        </div>
        {saveMsg && <p className="muted" style={{ marginTop: 8 }}>{saveMsg}</p>}
        {savedError && <p className="error">{savedError}</p>}

        {savedList.length > 0 && (
          <div style={{ marginTop: 14 }}>
            <div className="rule-head"><span>Your saved strategies ({savedList.length})</span></div>
            <div className="saved-strategy-list">
              {savedList.map((s) => (
                <div key={s.id} className={s.id === currentSavedId ? 'saved-strategy-row active' : 'saved-strategy-row'}>
                  <div className="saved-strategy-info">
                    <strong>{s.name}</strong>
                    <span className="muted">
                      {s.timeframe} · {s.split || 'in_sample'} · updated {new Date(s.updated_at).toLocaleString()}
                    </span>
                  </div>
                  <div className="saved-strategy-actions">
                    <button className="icon-btn" title="Load" disabled={savedLoading} onClick={() => handleLoad(s.id)}>
                      <FolderOpen size={14} />
                    </button>
                    <button className="icon-btn danger" title="Delete" onClick={() => handleDelete(s.id, s.name)}>
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
      <div className="rule-builder">
        <div className="rule-head"><span>Long entry when ALL match</span></div>
        {longRules.map((rule, i) => (
          <RuleRow
            key={`l-${i}`}
            rule={rule}
            indicators={indicators}
            onChange={(nr) => setLongRules(longRules.map((x, j) => (j === i ? nr : x)))}
            onRemove={() => setLongRules(longRules.filter((_, j) => j !== i))}
          />
        ))}
        <button className="ghost-btn" onClick={() => setLongRules([...longRules, defaultRule(indicators)])}>
          <Plus size={14} /> Long rule
        </button>
        <div className="rule-divider"><span>AND</span></div>
        <div className="rule-head exit"><span>Short entry when ALL match</span></div>
        {shortRules.map((rule, i) => (
          <RuleRow
            key={`s-${i}`}
            rule={rule}
            indicators={indicators}
            onChange={(nr) => setShortRules(shortRules.map((x, j) => (j === i ? nr : x)))}
            onRemove={() => setShortRules(shortRules.filter((_, j) => j !== i))}
          />
        ))}
        <button className="ghost-btn" onClick={() => setShortRules([...shortRules, defaultRule(indicators)])}>
          <Plus size={14} /> Short rule
        </button>
        <div className="param-grid" style={{ marginTop: 16 }}>
          <label className="param-field">Stop mode
            <select value={stopMode} onChange={(e) => setStopMode(e.target.value as 'fixed' | 'atr')}>
              <option value="fixed">Fixed $</option>
              <option value="atr">ATR multiple</option>
            </select>
          </label>
          {stopMode === 'fixed' ? (
            <label className="param-field">Stop dist ($)<input type="number" value={stopDist ?? ''} onChange={(e) => setStopDist(e.target.value === '' ? null : Number(e.target.value))} /></label>
          ) : (
            <label className="param-field">Stop = ATR(<input type="number" style={{ width: 40, display: 'inline' }} value={stopAtrN} onChange={(e) => setStopAtrN(Number(e.target.value) || 14)} />) x
              <input type="number" step="0.5" value={stopAtrMult ?? ''} onChange={(e) => setStopAtrMult(e.target.value === '' ? null : Number(e.target.value))} />
            </label>
          )}
          <label className="param-field">Target mode
            <select value={targetMode} onChange={(e) => setTargetMode(e.target.value as 'fixed' | 'atr')}>
              <option value="fixed">Fixed $</option>
              <option value="atr">ATR multiple</option>
            </select>
          </label>
          {targetMode === 'fixed' ? (
            <label className="param-field">Target dist ($)<input type="number" value={targetDist ?? ''} onChange={(e) => setTargetDist(e.target.value === '' ? null : Number(e.target.value))} /></label>
          ) : (
            <label className="param-field">Target = ATR(<input type="number" style={{ width: 40, display: 'inline' }} value={targetAtrN} onChange={(e) => setTargetAtrN(Number(e.target.value) || 14)} />) x
              <input type="number" step="0.5" value={targetAtrMult ?? ''} onChange={(e) => setTargetAtrMult(e.target.value === '' ? null : Number(e.target.value))} />
            </label>
          )}
          <label className="param-field">Session flat (UTC)<input type="number" value={sessionFlat ?? ''} onChange={(e) => setSessionFlat(e.target.value === '' ? null : Number(e.target.value))} /></label>
          <label className="param-field" title="New entries only fire at/after this UTC hour. Blank = no restriction.">Entry from (UTC h)<input type="number" min={0} max={23} value={entryStart ?? ''} onChange={(e) => setEntryStart(e.target.value === '' ? null : Number(e.target.value))} /></label>
          <label className="param-field" title="New entries only fire before this UTC hour (exclusive). Blank = no restriction. Set 'from' > 'to' for a window that wraps midnight.">Entry to (UTC h)<input type="number" min={0} max={24} value={entryEnd ?? ''} onChange={(e) => setEntryEnd(e.target.value === '' ? null : Number(e.target.value))} /></label>
          <label className="param-field">One trade / day<input type="checkbox" checked={oneTradePerDay} onChange={(e) => setOneTradePerDay(e.target.checked)} /></label>
        </div>
        <div className="rule-divider"><span>TRAILING STOP (optional)</span></div>
        <p className="muted" style={{ marginTop: -4, marginBottom: 10 }}>
          Once a trade is {trailActivateR ?? '…'}R in profit, ratchet the stop to this distance behind the
          running extreme instead of leaving it fixed — lets winners run past the target above.
          Leave "Trail dist" blank to disable and use only the fixed stop/target.
        </p>
        <div className="param-grid">
          <label className="param-field">Trail dist ($)<input type="number" value={trailDist ?? ''} onChange={(e) => setTrailDist(e.target.value === '' ? null : Number(e.target.value))} /></label>
          <label className="param-field">Activate at (R)<input type="number" step="0.1" disabled={trailDist == null} value={trailActivateR ?? ''} onChange={(e) => setTrailActivateR(e.target.value === '' ? null : Number(e.target.value))} /></label>
          <label className="param-field">Trail reference
            <select disabled={trailDist == null} value={trailRef} onChange={(e) => setTrailRef(e.target.value as 'close' | 'hl')}>
              <option value="close">Close</option>
              <option value="hl">High/Low</option>
            </select>
          </label>
        </div>
      </div>
      <div className="head-actions" style={{ marginTop: 16 }}>
        <button
          className="secondary-btn"
          disabled={previewLoading || (!longRules.length && !shortRules.length)}
          onClick={() => runPreview(longRules, shortRules, stopDist, targetDist, sessionFlat, oneTradePerDay)}
        >
          <Eye size={15} /> {previewLoading ? 'Plotting…' : 'Preview on chart'}
        </button>
        <button className="primary-btn" disabled={loading} onClick={run}>
          <Play size={15} fill="currentColor" /> {loading ? 'Running custom strategy…' : 'Run custom strategy'}
        </button>
      </div>
      {error && <p className="error">{error}</p>}

      <div className="rule-builder" style={{ marginTop: 16 }}>
        <div className="rule-head"><span>Confirm before running</span></div>
        <p className="muted" style={{ marginTop: -6, marginBottom: 10 }}>
          Price, the indicators your rules reference, and where long/short would fire — over {split.replace('_', ' ')}, {timeframe}.
        </p>
        {previewError && <p className="error">{previewError}</p>}
        {preview && (
          <>
            <p className="muted" style={{ marginBottom: 10 }}>
              {preview.n_bars.toLocaleString()} bars — {preview.n_long_signals.toLocaleString()} long signal(s),{' '}
              {preview.n_short_signals.toLocaleString()} short signal(s) in this window.
            </p>
            <PreviewChart
              ohlc={preview.ohlc}
              indicators={preview.indicators}
              longMarkers={preview.long_markers}
              shortMarkers={preview.short_markers}
            />
          </>
        )}
        {!preview && !previewError && !previewLoading && (
          <p className="muted">Parse a description or click "Preview on chart" to see it plotted here.</p>
        )}
      </div>
    </div>
  )
}

function RuleRow({
  rule, indicators, onChange, onRemove,
}: {
  rule: Rule
  indicators: IndicatorInfo[]
  onChange: (r: Rule) => void
  onRemove: () => void
}) {
  const ind = indicators.find((i) => i.id === rule.indicator)
  return (
    <div className="rule-row live">
      <select
        value={rule.indicator}
        onChange={(e) => {
          const next = indicators.find((i) => i.id === e.target.value)
          onChange({
            ...rule,
            indicator: e.target.value,
            output: next?.outputs[0] || rule.output,
            indParams: Object.fromEntries((next?.params || []).map((p) => [p.name, p.default])),
          })
        }}
      >
        {indicators.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
      </select>
      <div className="rule-right-indicator">
        {(ind?.params || []).map((p) => (
          <input
            key={p.name}
            type="number"
            value={rule.indParams[p.name] ?? p.default}
            onChange={(e) => onChange({ ...rule, indParams: { ...rule.indParams, [p.name]: Number(e.target.value) } })}
          />
        ))}
      </div>
      {(ind?.outputs?.length ?? 0) > 1 && (
        <select value={rule.output} onChange={(e) => onChange({ ...rule, output: e.target.value })}>
          {ind!.outputs.map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      )}
      <select value={rule.op} onChange={(e) => onChange({ ...rule, op: e.target.value })}>
        {OPS.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
      <select value={rule.rightKind} onChange={(e) => onChange({ ...rule, rightKind: e.target.value as Rule['rightKind'] })}>
        <option value="value">value</option>
        <option value="price">price</option>
        <option value="indicator">indicator</option>
      </select>
      {rule.rightKind === 'value' && (
        <input type="number" value={rule.value} onChange={(e) => onChange({ ...rule, value: Number(e.target.value) })} />
      )}
      {rule.rightKind === 'price' && (
        <select value={rule.field} onChange={(e) => onChange({ ...rule, field: e.target.value })}>
          {['open', 'high', 'low', 'close'].map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
      )}
      {rule.rightKind === 'indicator' && (
        <div className="rule-right-indicator">
          <select
            value={rule.rightIndicator}
            onChange={(e) => {
              const next = indicators.find((i) => i.id === e.target.value)
              onChange({
                ...rule,
                rightIndicator: e.target.value,
                rightOutput: next?.outputs[0] || rule.rightOutput,
                rightIndParams: Object.fromEntries((next?.params || []).map((p) => [p.name, p.default])),
              })
            }}
          >
            {indicators.map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
          </select>
          {(indicators.find((i) => i.id === rule.rightIndicator)?.params || []).map((p) => (
            <input
              key={p.name}
              type="number"
              value={rule.rightIndParams[p.name] ?? p.default}
              onChange={(e) => onChange({ ...rule, rightIndParams: { ...rule.rightIndParams, [p.name]: Number(e.target.value) } })}
            />
          ))}
          {(indicators.find((i) => i.id === rule.rightIndicator)?.outputs?.length ?? 0) > 1 && (
            <select value={rule.rightOutput} onChange={(e) => onChange({ ...rule, rightOutput: e.target.value })}>
              {indicators.find((i) => i.id === rule.rightIndicator)!.outputs.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          )}
        </div>
      )}
      <button className="remove-rule" aria-label="Remove rule" onClick={onRemove}><X size={14} /></button>
    </div>
  )
}

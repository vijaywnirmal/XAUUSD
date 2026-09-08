export interface ParamSpec {
  name: string
  type: 'int' | 'float' | 'select' | 'bool'
  default: unknown
  min?: number
  max?: number
  step?: number
  options?: string[]
  help?: string
}

export interface StrategyInfo {
  id: string
  name: string
  category: 'intraday' | 'daily-portfolio'
  timeframe: string
  description: string
  notes?: string | null
  params: ParamSpec[]
}

export interface RunConfig {
  timeframe?: string
  split?: string
  start?: string | null
  end?: string | null
  allow_oos?: boolean
  size_mode?: string
  size_lots?: number
  risk_pct?: number
  initial_equity?: number
  slippage_ticks?: number
}

export interface SuccessBarRow {
  metric: string
  value: number | string
  op: string
  threshold: number
  pass: 'PASS' | 'FAIL' | 'N/A'
}

export interface BacktestResult {
  run_id: string
  category: string
  strategy: { id: string; name: string }
  params: Record<string, unknown>
  run_config: RunConfig
  metrics: Record<string, unknown>
  success_bar: SuccessBarRow[]
  success_bar_all_pass: boolean
  monte_carlo: Record<string, unknown>
  n_bars: number
  trades: Record<string, unknown>[]
  equity: { ts: string; equity: number }[]
  ohlc: { ts: string; open: number; high: number; low: number; close: number }[]
  extra?: Record<string, unknown>
  error?: string
  strategy_id?: string
}

export interface IndicatorInfo {
  id: string
  name: string
  params: { name: string; type: string; default: number; min?: number; max?: number }[]
  outputs: string[]
}

async function readError(res: Response): Promise<string> {
  const text = await res.text()
  try {
    const json = JSON.parse(text) as { detail?: unknown }
    if (typeof json.detail === 'string') return json.detail
    if (json.detail != null) return JSON.stringify(json.detail)
  } catch {
    /* ignore */
  }
  return text || `${res.status} ${res.statusText}`
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) throw new Error(await readError(res))
  return res.json() as Promise<T>
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await readError(res))
  return res.json() as Promise<T>
}

export function fetchStrategies() {
  return getJson<StrategyInfo[]>('/api/strategies')
}

export function fetchIndicators() {
  return getJson<IndicatorInfo[]>('/api/indicators')
}

export function runBacktest(strategy_id: string, params: Record<string, unknown>, run_config: RunConfig) {
  return postJson<BacktestResult>('/api/backtest', { strategy_id, params, run_config })
}

export function runCompare(runs: { strategy_id: string; params: Record<string, unknown>; run_config: RunConfig }[]) {
  return postJson<{ runs: BacktestResult[] }>('/api/backtest/compare', { runs })
}

export function runBuilder(spec: unknown, timeframe: string, split: string, start?: string | null, end?: string | null) {
  return postJson<BacktestResult>('/api/strategy-builder/backtest', { timeframe, split, start, end, spec })
}

export interface ParsedRule {
  indicator: string
  indParams: Record<string, number>
  output: string
  op: string
  rightKind: 'value' | 'price' | 'indicator'
  value: number
  field: string
  rightIndicator?: string
  rightIndParams?: Record<string, number>
  rightOutput?: string
}

export interface ParsedStrategy {
  long_rules: ParsedRule[]
  short_rules: ParsedRule[]
  stop_dist: number | null
  target_dist: number | null
  session_flat_hour_utc: number | null
  entry_start_hour_utc: number | null
  entry_end_hour_utc: number | null
  trail_dist: number | null
  trail_activate_r: number | null
  trail_ref: 'close' | 'hl'
  one_trade_per_day: boolean
  notes: string
  backend: string
}

export function parseStrategyText(text: string) {
  return postJson<ParsedStrategy>('/api/strategy-builder/parse', { text })
}

export interface BuilderPreview {
  ohlc: { ts: string; open: number; high: number; low: number; close: number }[]
  indicators: Record<string, (number | null)[]>
  long_markers: string[]
  short_markers: string[]
  n_bars: number
  n_long_signals: number
  n_short_signals: number
}

export function previewBuilder(spec: unknown, timeframe: string, split: string, start?: string | null, end?: string | null) {
  return postJson<BuilderPreview>('/api/strategy-builder/preview', { timeframe, split, start, end, spec })
}

export interface RunDetailTrade {
  side: number
  entry_ts: string
  exit_ts: string
  entry_mid: number
  exit_mid: number
  net_pnl: number
  exit_reason: string
  stop_lvl: number | null
  tgt_lvl: number | null
}

export interface RunDetail {
  candles: { time: number; open: number; high: number; low: number; close: number }[]
  trades: RunDetailTrade[]
  window_start: string
  window_end: string
  n_candles: number
  n_trades_in_window: number
}

export function fetchRunDetail(runId: string, days = 30) {
  return getJson<RunDetail>(`/api/run/${runId}/detail?days=${days}`)
}

export function exportUrl(runId: string, fmt: 'csv' | 'json' | 'pdf') {
  return `/api/export/${runId}.${fmt}`
}

export interface SavedStrategySummary {
  id: string
  name: string
  timeframe: string
  split: string | null
  start: string | null
  end: string | null
  created_at: string
  updated_at: string
}

export interface SavedStrategy extends SavedStrategySummary {
  spec: Record<string, unknown>
}

async function deleteJson(path: string): Promise<void> {
  const res = await fetch(path, { method: 'DELETE' })
  if (!res.ok) throw new Error(await readError(res))
}

export function listSavedStrategies() {
  return getJson<SavedStrategySummary[]>('/api/saved-strategies')
}

export function fetchSavedStrategy(id: string) {
  return getJson<SavedStrategy>(`/api/saved-strategies/${id}`)
}

export function saveStrategy(
  name: string,
  spec: unknown,
  timeframe: string,
  split: string,
  start?: string | null,
  end?: string | null,
  id?: string,
) {
  return postJson<SavedStrategy>('/api/saved-strategies', { name, spec, timeframe, split, start, end, id })
}

export function deleteSavedStrategy(id: string) {
  return deleteJson(`/api/saved-strategies/${id}`)
}

export function defaultsFrom(params: ParamSpec[]) {
  const out: Record<string, unknown> = {}
  for (const p of params) out[p.name] = p.default
  return out
}

// ---------------------------------------------------------------- live bot
export interface LiveBotStatus {
  running: boolean
  detail?: string
  ts?: string
  mode?: string
  symbol?: string
  age_seconds?: number | null
  account?: {
    login?: string | null; broker?: string | null; server?: string | null
    balance?: number | null; currency?: string | null
    trade_allowed?: boolean | null; is_live?: boolean
  }
  now_utc?: string
  price?: number
  spread?: number
  box?: { high: number; low: number; width: number; bars: number } | null
  state?: string
  armed_today?: boolean
  day_done?: boolean
  has_pending?: boolean
  trades_today?: number
  realised_today?: number
  kill_switch?: boolean
  position?: { side: string; entry: number; sl: number; unrealised: number } | null
}

export interface LiveBotDecision {
  ts: string
  intent?: string
  event?: string
  status?: string
  [k: string]: unknown
}

export interface LiveBotTradeRow {
  date: string; mode: string; side: string
  box_high: number | null; box_low: number | null; box_width: number | null
  entry_time_utc: string; entry_px: number | null; entry_spread: number | null
  stop_px: number | null; exit_time_utc: string; exit_px: number | null; exit_reason: string
  gross_pnl: number | null; cost: number | null; net_pnl: number | null
  slippage_vs_box: number | null; notes: string
}

export interface LiveBotTrades {
  rows: LiveBotTradeRow[]
  summary: {
    n: number; win_rate: number | null; exp_net: number | null; exp_gross: number | null
    cum_net: number; pf: number | null; avg_entry_spread: number | null
    avg_slippage: number | null; effective_cost: number | null; breakeven_spread: number
    edge_intact: boolean; backtest_gross: number
  } | null
}

export function fetchLiveBotStatus() {
  return getJson<LiveBotStatus>('/api/livebot/status')
}
export function fetchLiveBotDecisions(limit = 40) {
  return getJson<LiveBotDecision[]>(`/api/livebot/decisions?limit=${limit}`)
}
export function fetchLiveBotTrades() {
  return getJson<LiveBotTrades>('/api/livebot/trades')
}

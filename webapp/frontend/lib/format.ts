export function fmtNum(v: unknown, digits = 2): string {
  if (v === null || v === undefined || v === 'N/A') return '—'
  if (typeof v === 'number') {
    if (!Number.isFinite(v)) return v > 0 ? '∞' : '-∞'
    const abs = Math.abs(v)
    if (abs >= 1000) return v.toFixed(1)
    if (abs >= 1) return v.toFixed(digits)
    return v.toFixed(4)
  }
  return String(v)
}

export function fmtPct(v: unknown): string {
  if (typeof v !== 'number' || !Number.isFinite(v)) return '—'
  const sign = v > 0 ? '+' : ''
  return `${sign}${v.toFixed(2)}%`
}

export function fmtUsd(v: unknown): string {
  if (typeof v !== 'number' || !Number.isFinite(v)) return '—'
  const sign = v > 0 ? '+' : ''
  return `${sign}$${v.toFixed(2)}`
}

export function fmtTs(v: unknown): string {
  if (v == null) return '—'
  return String(v).replace('T', ' ').slice(0, 19)
}

export function metricNum(metrics: Record<string, unknown>, key: string): number | null {
  const v = metrics[key]
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

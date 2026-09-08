'use client'

import type { ParamSpec } from '@/lib/api'

export default function ParamFields({
  params,
  values,
  onChange,
}: {
  params: ParamSpec[]
  values: Record<string, unknown>
  onChange: (name: string, value: unknown) => void
}) {
  if (!params.length) return <p className="muted">This strategy has no tunable parameters.</p>
  return (
    <div className="param-grid">
      {params.map((p) => (
        <label key={p.name} className="param-field" title={p.help || p.name}>
          <span>{p.name}</span>
          {p.type === 'select' ? (
            <select
              value={String(values[p.name] ?? p.default ?? '')}
              onChange={(e) => onChange(p.name, e.target.value)}
            >
              {(p.options || []).map((o) => (
                <option key={o} value={o}>{o}</option>
              ))}
            </select>
          ) : p.type === 'bool' ? (
            <input
              type="checkbox"
              checked={Boolean(values[p.name] ?? p.default)}
              onChange={(e) => onChange(p.name, e.target.checked)}
            />
          ) : (
            <input
              type="number"
              step={p.step ?? (p.type === 'int' ? 1 : 'any')}
              min={p.min}
              max={p.max}
              value={values[p.name] === null || values[p.name] === undefined ? '' : String(values[p.name])}
              onChange={(e) => onChange(p.name, e.target.value === '' ? null : Number(e.target.value))}
            />
          )}
        </label>
      ))}
    </div>
  )
}

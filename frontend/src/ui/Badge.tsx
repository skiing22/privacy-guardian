import type { RiskLevel, ScanStatus } from '../api/scans'

// DESIGN 5.4. Badges always carry words; colour is never the only signal (DESIGN 11).
const BADGE = 'inline-flex items-center rounded-md px-2 py-0.5 caption-4 whitespace-nowrap'

const STATUS: Record<ScanStatus, string> = {
  queued: 'Waiting',
  running: 'Running',
  needs_review: 'Needs review',
  done: 'Done',
  failed: 'Failed',
}

export function StatusBadge({ status }: { status: ScanStatus }) {
  const tone = status === 'needs_review' ? 'text-sign border-sign' : 'text-ink-muted border-rule'
  return <span className={`${BADGE} border ${tone}`}>{STATUS[status]}</span>
}

const RISK: Record<RiskLevel, { label: string; cls: string }> = {
  LOW: { label: 'Low risk', cls: 'bg-risk-low-bg text-risk-low' },
  MEDIUM: { label: 'Medium risk', cls: 'bg-risk-medium-bg text-risk-medium' },
  HIGH: { label: 'High risk', cls: 'bg-risk-high-bg text-risk-high' },
  DIRECT: { label: 'Personal data visible', cls: 'bg-risk-direct-bg text-white' },
}

export function RiskBadge({ level }: { level: RiskLevel }) {
  const r = RISK[level]
  return <span className={`${BADGE} ${r.cls}`}>{r.label}</span>
}

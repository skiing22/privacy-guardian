import type { AuditItem, VerifyOut } from '../../api/admin'
import { typeName } from '../../ui/TypeLabel'

/** Plain words for the audit log (DESIGN 12 S6, 13). Never raw values, never file names. */

export const ACTION_WORDS: Record<string, string> = {
  keep: 'Keep',
  generalize: 'Generalize',
  mask: 'Mask',
  pseudonymize: 'Replace with token',
  redact: 'Remove',
}

const RISK: Record<string, string> = {
  LOW: 'low risk',
  MEDIUM: 'medium risk',
  HIGH: 'high risk',
  DIRECT: 'personal data visible',
}

export type DetailPart = { text: string; mono?: boolean }

function num(d: Record<string, unknown>, k: string): number {
  const v = d[k]
  return typeof v === 'number' ? v : 0
}
function str(d: Record<string, unknown>, k: string): string {
  const v = d[k]
  return typeof v === 'string' ? v : ''
}
const short = (id: string) => id.split('-')[0] ?? id
const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`

/** Each audit event's details as plain words; tokens are marked to render in mono. */
export function details(item: AuditItem): DetailPart[] {
  const d = item.details
  switch (item.event) {
    case 'scan_completed':
      return [{ text: `scan ${short(str(d, 'scan'))}, ${RISK[str(d, 'risk')] ?? str(d, 'risk')}` }]
    case 'review': {
      const answers = Array.isArray(d['answers']) ? d['answers'].length : 0
      return [{ text: `scan ${short(str(d, 'scan'))}, ${plural(answers, 'answer')}` }]
    }
    case 'reidentify':
      return [{ text: str(d, 'token'), mono: true }, { text: `, reason: ${str(d, 'reason')}` }]
    case 'reidentify_denied':
      return [{ text: str(d, 'token'), mono: true }, { text: `, asked by a ${str(d, 'role')}` }]
    case 'rules_changed': {
      const rules = (d['rules'] ?? {}) as Record<string, string>
      const parts = Object.entries(rules).map(([t, a]) => `${typeName(t)}: ${ACTION_WORDS[a] ?? a}`)
      return [{ text: parts.length ? parts.join(', ') : 'all types automatic' }]
    }
    case 'beliefs_reset':
      return [{ text: `learning for ${plural(num(d, 'count'), 'type')} cleared` }]
    case 'retention': {
      const bits = [
        num(d, 'scans') && plural(num(d, 'scans'), 'scan'),
        num(d, 'sessions') && plural(num(d, 'sessions'), 'session'),
        num(d, 'vault') && plural(num(d, 'vault'), 'stored value'),
        num(d, 'files') && plural(num(d, 'files'), 'file'),
      ].filter(Boolean)
      return [{ text: bits.length ? `${bits.join(', ')} deleted` : 'nothing to delete' }]
    }
    case 'user_created':
      return [{ text: `user ${num(d, 'user_id')}, ${str(d, 'role')}` }]
    case 'user_disabled':
      return [{ text: `user ${num(d, 'user_id')}` }]
    case 'anchor_saved':
      return [{ text: `at record ${num(d, 'seq')}` }]
    default:
      return [{ text: '' }]
  }
}

/** Verify result in one sentence (DESIGN 12 S6, PRD 12). */
export function verifySentence(v: VerifyOut, anchorTime?: string): string {
  if (v.ok) {
    const base = `All ${v.checked.toLocaleString('en-IN')} records check out`
    return v.anchor
      ? `${base} and match the anchor saved on ${anchorTime ?? ''}.`
      : `${base}. No anchor saved yet.`
  }
  const k = v.first_bad_seq ?? 0
  const r = v.reason ?? ''
  if (r.startsWith('payload changed') || r.startsWith('mac mismatch'))
    return `Record ${k} was changed after it was saved.`
  if (r.startsWith('chain broken')) return `A record was removed or added before record ${k}.`
  if (r.startsWith('sequence gap')) return `Records are missing or out of order at record ${k}.`
  if (r.startsWith('unknown key'))
    return `Record ${k} was signed with a key this server does not have.`
  if (r.includes('shorter than anchor'))
    return `The log ends before the saved anchor at record ${k}: records were deleted.`
  if (r.includes('does not match anchor'))
    return `The log does not match the anchor saved at record ${k}: it was rewritten.`
  return `The log failed its check at record ${k}.`
}

/** Index of the record the verify points at, if that record is a single bad row. */
export function badRow(v: VerifyOut | undefined): number | null {
  if (!v || v.ok || v.first_bad_seq === null) return null
  const r = v.reason ?? ''
  return r.includes('anchor') ? null : v.first_bad_seq
}

import type { Verdict } from '../../api/scan'

/**
 * P15.3: unsent answers survive a session expiry (the user logs in again and comes back).
 * Only item numbers and verdicts are kept, never document text. Per tab, and storage can
 * be missing or full, so every call is guarded and failures just mean "nothing saved".
 */
const key = (scanId: string) => `pg-answers:${scanId}`

export function loadAnswers(scanId: string): Record<number, Verdict> {
  try {
    const raw = sessionStorage.getItem(key(scanId))
    if (!raw) return {}
    const data: unknown = JSON.parse(raw)
    if (typeof data !== 'object' || data === null) return {}
    const out: Record<number, Verdict> = {}
    for (const [k, v] of Object.entries(data)) {
      if (/^\d+$/.test(k) && (v === 'protect' || v === 'keep' || v === 'not_pii'))
        out[Number(k)] = v
    }
    return out
  } catch {
    return {}
  }
}

export function saveAnswers(scanId: string, answers: Record<number, Verdict>): void {
  try {
    sessionStorage.setItem(key(scanId), JSON.stringify(answers))
  } catch {
    /* storage unavailable: answers stay in memory only */
  }
}

export function clearAnswers(scanId: string): void {
  try {
    sessionStorage.removeItem(key(scanId))
  } catch {
    /* nothing to clear */
  }
}

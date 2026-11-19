/** One scan: status (polled), answers, retry, downloads (API.md 4.7, 4.8, 4.10, 4.11). */
import type { components } from './schema'
import { api } from './client'

export type ScanStatusOut = components['schemas']['ScanStatusOut']
export type ReviewItem = components['schemas']['ReviewItem']
export type Risk = components['schemas']['Risk']
export type Verdict = 'protect' | 'keep' | 'not_pii'
export type Answer = { index: number; verdict: Verdict }

export function getScan(id: string) {
  return api<ScanStatusOut>(`/api/v1/scans/${encodeURIComponent(id)}`)
}

export function sendAnswers(id: string, answers: Answer[]) {
  return api<{ id: string; status: string }>(`/api/v1/scans/${encodeURIComponent(id)}/answers`, {
    method: 'POST',
    body: JSON.stringify({ answers }),
  })
}

export function retryScan(id: string) {
  return api<{ id: string; status: string }>(`/api/v1/scans/${encodeURIComponent(id)}/retry`, {
    method: 'POST',
  })
}

export function downloadUrl(id: string, kind: 'cleaned' | 'report'): string {
  return `/api/v1/scans/${encodeURIComponent(id)}/download?kind=${kind}`
}

export function getHealth() {
  return fetch('/health', { credentials: 'same-origin' })
    .then((r) => r.json() as Promise<{ model_ready?: boolean }>)
    .catch(() => ({ model_ready: undefined }))
}

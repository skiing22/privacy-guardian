/** Scan list, delete and upload (API.md 4.5, 4.6, 4.12). */
import type { components } from './schema'
import { api, ApiError, type ApiErrorBody } from './client'

export type ScanStatus = components['schemas']['ScanListItem']['status']
export type ScanListItem = components['schemas']['ScanListItem']
export type ScanList = components['schemas']['ScanList']
export type ScanAccepted = components['schemas']['ScanAccepted']
export type RiskLevel = NonNullable<ScanListItem['risk_level']>

export const scanKeys = {
  all: ['scans'] as const,
  list: (status?: ScanStatus) => ['scans', 'list', status ?? 'all'] as const,
  one: (id: string) => ['scans', 'one', id] as const,
}

export const OPEN_STATUSES: ReadonlySet<ScanStatus> = new Set(['queued', 'running'])

export function listScans(opts: { status?: ScanStatus; cursor?: string | null; limit?: number }) {
  const q = new URLSearchParams()
  if (opts.status) q.set('status', opts.status)
  if (opts.cursor) q.set('cursor', opts.cursor)
  q.set('limit', String(opts.limit ?? 50))
  return api<ScanList>(`/api/v1/scans?${q.toString()}`)
}

export function deleteScan(id: string): Promise<undefined> {
  return api<undefined>(`/api/v1/scans/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

/**
 * Upload with real progress. fetch cannot report upload progress, XMLHttpRequest can.
 * Same rules as `api`: same-origin cookie, the browser adds the Origin header, every
 * non-2xx becomes an ApiError with the server's error body.
 */
export function startScan(
  input: { file: File } | { text: string },
  onProgress?: (fraction: number) => void,
): Promise<ScanAccepted> {
  const form = new FormData()
  if ('file' in input) form.append('file', input.file, input.file.name)
  else form.append('text', input.text)
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/v1/scans')
    xhr.withCredentials = false // same origin: the cookie goes anyway
    xhr.responseType = 'text'
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total)
    }
    xhr.onerror = () => reject(new ApiError(0, OFFLINE))
    xhr.onload = () => {
      let data: unknown
      try {
        data = JSON.parse(xhr.responseText)
      } catch {
        data = undefined
      }
      if (xhr.status >= 200 && xhr.status < 300) return resolve(data as ScanAccepted)
      const body = (data as { error?: ApiErrorBody } | undefined)?.error
      reject(new ApiError(xhr.status, body && body.code ? body : OFFLINE))
    }
    xhr.send(form)
  })
}

const OFFLINE: ApiErrorBody = {
  code: 'internal',
  message: 'Service unavailable. Try again shortly.',
  field: null,
}

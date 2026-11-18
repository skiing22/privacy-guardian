/**
 * Thin, typed fetch wrapper for the same-origin API (API.md 2).
 * Every non-2xx response becomes an ApiError carrying the API's error body.
 * Request/response types come from the generated OpenAPI schema (npm run gen:api).
 */

export type ApiErrorBody = {
  code: string
  message: string
  field: string | null
  request_id?: string
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly field: string | null
  readonly requestId: string | undefined

  constructor(status: number, body: ApiErrorBody) {
    super(body.message)
    this.name = 'ApiError'
    this.status = status
    this.code = body.code
    this.field = body.field
    this.requestId = body.request_id
  }
}

const FALLBACK: ApiErrorBody = {
  code: 'internal',
  message: 'Service unavailable. Try again shortly.',
  field: null,
}

function isErrorBody(x: unknown): x is { error: ApiErrorBody } {
  if (typeof x !== 'object' || x === null || !('error' in x)) return false
  const e = (x as { error: unknown }).error
  return typeof e === 'object' && e !== null && 'code' in e && 'message' in e
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body !== undefined && !(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  let res: Response
  try {
    res = await fetch(path, { ...init, headers, credentials: 'same-origin' })
  } catch {
    throw new ApiError(0, FALLBACK)
  }
  if (res.status === 204) return undefined as T
  const data: unknown = await res.json().catch(() => undefined)
  if (!res.ok) throw new ApiError(res.status, isErrorBody(data) ? data.error : FALLBACK)
  return data as T
}

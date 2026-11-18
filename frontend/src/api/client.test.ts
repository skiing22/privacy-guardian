import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError } from './client'

afterEach(() => vi.unstubAllGlobals())

describe('api client', () => {
  it('maps the API error body', async () => {
    const body = {
      error: { code: 'file_too_large', message: 'File too large (max 10 MB).', field: 'file' },
    }
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status: 413 })),
    )
    await expect(api('/api/v1/scans')).rejects.toMatchObject({
      status: 413,
      code: 'file_too_large',
      field: 'file',
    })
  })

  it('turns a network failure into a safe message', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))
    const err = await api('/health').catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).message).toBe('Service unavailable. Try again shortly.')
  })
})

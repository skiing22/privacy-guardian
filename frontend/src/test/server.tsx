import { QueryClientProvider } from '@tanstack/react-query'
import { render } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { vi } from 'vitest'
import { createQueryClient } from '../app/queryClient'
import { routes } from '../app/routes'

type Reply = { status: number; body?: unknown }
type Handler = (init: RequestInit | undefined) => Reply

export const USER = { id: 1, email: 'asha.rao@example.com', role: 'user' }
export const ADMIN = { id: 2, email: 'boss@example.com', role: 'admin' }
export const err = (
  status: number,
  code: string,
  message: string,
  field: string | null = null,
) => ({
  status,
  body: { error: { code, message, field, request_id: 'r1' } },
})

/** Fake API: "METHOD /path" -> reply. Unknown calls fail the test loudly. */
export function fakeApi(handlers: Record<string, Handler | Reply>) {
  const calls: string[] = []
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const key = `${init?.method ?? 'GET'} ${String(input)}`
    calls.push(key)
    const h = handlers[key]
    if (!h) throw new Error(`unexpected request ${key}`)
    const r = typeof h === 'function' ? h(init) : h
    const body = r.body === undefined ? null : JSON.stringify(r.body)
    return new Response(r.status === 204 ? null : body, { status: r.status })
  })
  vi.stubGlobal('fetch', fetchMock)
  return { calls, fetchMock }
}

export function renderAt(path: string) {
  const client = createQueryClient()
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  return { client, router }
}

/**
 * Session API (API.md 4.2 to 4.4). The session itself lives in an HttpOnly cookie the
 * browser sends for us; JavaScript never sees or stores it (ARCHITECTURE 8.1).
 */
import type { components } from './schema'
import { api, ApiError } from './client'

export type Me = components['schemas']['Me']

/** `ended` = we had a session and the server ended it (expired, logged out elsewhere). */
export type Session = { user: Me | null; ended: boolean }

export const SESSION_KEY = ['session'] as const

/** A 401 that means "you are not logged in" (not "wrong password"). */
export function isSessionError(e: unknown): boolean {
  return (
    e instanceof ApiError &&
    e.status === 401 &&
    (e.code === 'auth_required' || e.code === 'session_expired')
  )
}

export async function fetchSession(): Promise<Session> {
  try {
    return { user: await api<Me>('/api/v1/auth/me'), ended: false }
  } catch (e) {
    if (isSessionError(e)) return { user: null, ended: false }
    throw e
  }
}

export function login(email: string, password: string): Promise<undefined> {
  return api<undefined>('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
}

export function logout(): Promise<undefined> {
  return api<undefined>('/api/v1/auth/logout', { method: 'POST' })
}

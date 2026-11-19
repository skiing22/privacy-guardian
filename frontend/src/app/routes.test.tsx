import { screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeApi, renderAt, USER } from '../test/server'

afterEach(() => vi.unstubAllGlobals())

describe('routes', () => {
  it('redirects / to scans and marks the current nav link', async () => {
    fakeApi({ 'GET /api/v1/auth/me': { status: 200, body: USER } })
    renderAt('/')
    expect(await screen.findByRole('heading', { name: 'Scans' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Scans' }).getAttribute('aria-current')).toBe('page')
  })

  it('shows the 404 page for unknown paths', async () => {
    fakeApi({ 'GET /api/v1/auth/me': { status: 200, body: USER } })
    renderAt('/nope')
    expect(await screen.findByRole('heading', { name: 'This page does not exist.' })).toBeTruthy()
  })

  it('puts the skip link first', async () => {
    fakeApi({ 'GET /api/v1/auth/me': { status: 200, body: USER } })
    renderAt('/scans')
    await screen.findByRole('heading', { name: 'Scans' })
    expect(screen.getAllByRole('link')[0]?.textContent).toBe('Skip to content')
  })
})

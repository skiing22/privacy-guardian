import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ADMIN, err, fakeApi, renderAt, USER } from '../../test/server'

afterEach(() => vi.unstubAllGlobals())

const ME = 'GET /api/v1/auth/me'
const LOGIN = 'POST /api/v1/auth/login'
const LOGOUT = 'POST /api/v1/auth/logout'
const anon = err(401, 'auth_required', 'Please log in.')

function fill(email: string, password: string) {
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: email } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: password } })
  fireEvent.click(screen.getByRole('button', { name: 'Log in' }))
}

describe('protected routes', () => {
  it('sends a logged out visitor to login and keeps where they were going', async () => {
    fakeApi({ [ME]: anon })
    const { router } = renderAt('/scans/42?view=clean')
    await screen.findByRole('heading', { name: 'Log in' })
    expect(router.state.location.pathname).toBe('/login')
    expect(router.state.location.search).toBe('?next=%2Fscans%2F42%3Fview%3Dclean')
  })

  it('logs in and returns to the page asked for', async () => {
    let loggedIn = false
    const { calls } = fakeApi({
      [ME]: () => (loggedIn ? { status: 200, body: USER } : anon),
      [LOGIN]: (init) => {
        expect(JSON.parse(String(init?.body))).toEqual({
          email: 'asha.rao@example.com',
          password: 'correct horse 1',
        })
        loggedIn = true
        return { status: 204 }
      },
    })
    const { router } = renderAt('/login?next=%2Fscans%2Fnew')
    fill(' asha.rao@example.com ', 'correct horse 1')
    await screen.findByRole('heading', { name: 'New scan' })
    expect(router.state.location.pathname).toBe('/scans/new')
    expect(calls).toContain(LOGIN)
  })

  it('never redirects off site after login', async () => {
    fakeApi({ [ME]: { status: 200, body: USER } })
    const { router } = renderAt('/login?next=https%3A%2F%2Fevil.example')
    await waitFor(() => expect(router.state.location.pathname).toBe('/scans'))
  })

  it('shows one shared message for a wrong email or password', async () => {
    fakeApi({ [ME]: anon, [LOGIN]: err(401, 'auth_failed', 'Wrong email or password.') })
    renderAt('/login')
    fill('asha.rao@example.com', 'wrong password')
    expect((await screen.findByRole('alert')).textContent).toBe('Wrong email or password.')
    expect((screen.getByLabelText('Password') as HTMLInputElement).value).toBe('')
    expect(document.activeElement).toBe(screen.getByLabelText('Password'))
  })

  it('shows the wait time when there were too many tries', async () => {
    fakeApi({ [ME]: anon, [LOGIN]: err(429, 'rate_limited', 'Too many tries. Wait 60 seconds.') })
    renderAt('/login')
    fill('asha.rao@example.com', 'wrong password')
    expect((await screen.findByRole('alert')).textContent).toBe('Too many tries. Wait 60 seconds.')
  })

  it('checks the email before calling the server', async () => {
    const { calls } = fakeApi({ [ME]: anon })
    renderAt('/login')
    await screen.findByLabelText('Email')
    fill('not an email', 'x')
    expect(await screen.findByText('Enter an email address like name@example.com.')).toBeTruthy()
    expect(screen.getByLabelText('Email').getAttribute('aria-invalid')).toBe('true')
    expect(calls).not.toContain(LOGIN)
  })

  it('a normal user sees no admin links and gets the forbidden page', async () => {
    fakeApi({ [ME]: { status: 200, body: USER } })
    renderAt('/admin/rules')
    await screen.findByRole('heading', { name: 'Only admins can do this.' })
    expect(screen.queryByRole('link', { name: 'Rules & vault' })).toBeNull()
    expect(screen.queryByRole('link', { name: 'Audit log' })).toBeNull()
  })

  it('an admin sees the admin pages and links', async () => {
    fakeApi({ [ME]: { status: 200, body: ADMIN } })
    renderAt('/admin/audit')
    await screen.findByRole('heading', { name: 'Audit log' })
    expect(screen.getByRole('link', { name: 'Rules & vault' })).toBeTruthy()
  })

  it('a 401 anywhere ends the session and asks to log in again', async () => {
    fakeApi({ [ME]: { status: 200, body: USER } })
    const { client, router } = renderAt('/scans')
    await screen.findByRole('heading', { name: 'Scans' })
    // any other request now answers 401 (session expired on the server)
    await client
      .fetchQuery({
        queryKey: ['scans'],
        queryFn: async () => {
          const { api } = await import('../../api/client')
          fakeApi({ 'GET /api/v1/scans': err(401, 'session_expired', 'Please log in again.') })
          return api('/api/v1/scans')
        },
      })
      .catch(() => undefined)
    expect(await screen.findByText('Please log in again.')).toBeTruthy()
    expect(router.state.location.search).toBe('?next=%2Fscans')
    expect(client.getQueryData(['scans'])).toBeUndefined()
  })

  it('logs out, forgets cached data and goes to login', async () => {
    const { calls } = fakeApi({ [ME]: { status: 200, body: USER }, [LOGOUT]: { status: 204 } })
    const { client, router } = renderAt('/scans')
    client.setQueryData(['scans'], ['private'])
    fireEvent.click(
      await screen.findByRole('button', { name: `AR Account menu for ${USER.email}` }),
    )
    expect(screen.getByText('User')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Log out' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/login'))
    expect(calls).toContain(LOGOUT)
    expect(client.getQueryData(['scans'])).toBeUndefined()
  })

  it('shows a clear message when the server is down', async () => {
    fakeApi({ [ME]: err(503, 'storage_unavailable', 'Service unavailable. Try again shortly.') })
    renderAt('/scans')
    expect((await screen.findByRole('alert', {}, { timeout: 4000 })).textContent).toBe(
      'Service unavailable. Try again shortly.',
    )
  })

  it('keeps privacy and 404 pages public', async () => {
    const { calls } = fakeApi({ [ME]: anon })
    const { router } = renderAt('/privacy')
    await screen.findByRole('heading', { name: 'Privacy and terms' })
    expect(router.state.location.pathname).toBe('/privacy')
    expect(calls.every((c) => c === ME)).toBe(true)
  })
})

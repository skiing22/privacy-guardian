import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { formatStarted } from '../lib/format'
import { err, fakeApi, renderAt, USER } from '../test/server'
import { fakeXhr } from '../test/xhr'
import { fileProblem } from './NewScan'

const ME = 'GET /api/v1/auth/me'
const REVIEW = 'GET /api/v1/scans?status=needs_review&limit=100'
const ALL = 'GET /api/v1/scans?limit=50'
const me = { status: 200, body: USER }

const scan = (id: string, name: string, status: string, risk: string | null = null) => ({
  id: `00000000-0000-4000-8000-00000000000${id}`,
  filename: name,
  format: 'txt',
  status,
  risk_level: risk,
  created_at: '2026-11-19T10:00:00.000Z',
  expires_at: '2026-11-26T10:00:00.000Z',
})
const list = (...items: unknown[]) => ({ status: 200, body: { items, next_cursor: null } })

function rows(): string[] {
  const table = screen.getAllByRole('table')[0]
  if (!table) return []
  return within(table)
    .getAllByRole('row')
    .slice(1)
    .map((r) => within(r).getAllByRole('cell')[0]?.textContent ?? '')
}

describe('S2 scans', () => {
  it('lists scans that need review first, then newest', async () => {
    const waiting = scan('2', 'employees.csv', 'needs_review')
    fakeApi({
      [ME]: me,
      [REVIEW]: list(waiting),
      [ALL]: list(scan('1', 'notes.txt', 'done', 'LOW'), waiting, scan('3', 'old.pdf', 'failed')),
    })
    renderAt('/scans')
    await screen.findAllByText('notes.txt')
    expect(rows()).toEqual(['employees.csv', 'notes.txt', 'old.pdf'])
    expect(screen.getAllByText('Needs review')[0]?.className).toContain('text-sign')
    expect(screen.getAllByText('Low risk').length).toBeGreaterThan(0)
    const link = screen.getAllByRole('link', { name: 'employees.csv' })[0]
    expect(link?.getAttribute('href')).toBe(`/scans/${waiting.id}`)
  })

  it('shows the empty state with one action', async () => {
    fakeApi({ [ME]: me, [REVIEW]: list(), [ALL]: list() })
    const { router } = renderAt('/scans')
    expect(await screen.findByText('No scans yet. Start your first scan.')).toBeTruthy()
    fireEvent.click(screen.getAllByRole('button', { name: 'New scan' })[1] as HTMLElement)
    expect(router.state.location.pathname).toBe('/scans/new')
  })

  it('shows an error with Retry when the list cannot load', async () => {
    let fail = true
    fakeApi({
      [ME]: me,
      [REVIEW]: () => (fail ? err(400, 'invalid_request', 'x') : list()),
      [ALL]: () => (fail ? err(400, 'invalid_request', 'x') : list()),
    })
    renderAt('/scans')
    expect((await screen.findByRole('alert')).textContent).toBe('Could not load scans.')
    fail = false
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText('No scans yet. Start your first scan.')).toBeTruthy()
  })

  it('deletes a scan after asking, and says so', async () => {
    const s = scan('1', 'notes.txt', 'done', 'LOW')
    let deleted = false
    const { calls } = fakeApi({
      [ME]: me,
      [REVIEW]: list(),
      [ALL]: () => (deleted ? list() : list(s)),
      [`DELETE /api/v1/scans/${s.id}`]: () => ((deleted = true), { status: 204 }),
    })
    renderAt('/scans')
    const [trigger] = await screen.findAllByRole('button', { name: 'Delete notes.txt' })
    fireEvent.click(trigger as HTMLElement)
    const dialog = screen.getByRole('dialog', { name: 'Delete notes.txt?' })
    expect(document.activeElement?.textContent).toBe('Cancel') // safe choice focused first
    fireEvent.click(within(dialog).getByRole('button', { name: 'Delete scan' }))
    expect(await screen.findByText('Deleted notes.txt')).toBeTruthy()
    expect(await screen.findByText('No scans yet. Start your first scan.')).toBeTruthy()
    expect(calls).toContain(`DELETE /api/v1/scans/${s.id}`)
  })

  it('Escape closes the dialog without deleting', async () => {
    const s = scan('1', 'notes.txt', 'done')
    const { calls } = fakeApi({ [ME]: me, [REVIEW]: list(), [ALL]: list(s) })
    renderAt('/scans')
    const [del] = await screen.findAllByRole('button', { name: 'Delete notes.txt' })
    fireEvent.click(del as HTMLElement)
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(calls.some((c) => c.startsWith('DELETE'))).toBe(false)
  })

  it('cannot delete a scan that is still running', async () => {
    fakeApi({ [ME]: me, [REVIEW]: list(), [ALL]: list(scan('1', 'big.pdf', 'running')) })
    renderAt('/scans')
    const [btn] = await screen.findAllByRole('button', { name: 'Delete big.pdf' })
    expect((btn as HTMLButtonElement).disabled).toBe(true)
  })

  it('loads more scans with the cursor', async () => {
    fakeApi({
      [ME]: me,
      [REVIEW]: list(),
      [ALL]: { status: 200, body: { items: [scan('1', 'a.txt', 'done')], next_cursor: 'abc' } },
      'GET /api/v1/scans?cursor=abc&limit=50': list(scan('2', 'b.txt', 'done')),
    })
    renderAt('/scans')
    fireEvent.click(await screen.findByRole('button', { name: 'Load more scans' }))
    await screen.findAllByText('b.txt')
    expect(rows()).toEqual(['a.txt', 'b.txt'])
    expect(screen.queryByRole('button', { name: 'Load more scans' })).toBeNull()
  })
})

describe('S3 new scan', () => {
  const file = (name: string, size = 10) => new File(['x'.repeat(size)], name)

  it('checks files before upload', () => {
    expect(fileProblem(file('a.exe'))).toBe('Only TXT, PDF, DOCX, CSV.')
    expect(fileProblem(file('a.PDF'))).toBeNull()
    expect(fileProblem(file('a.txt', 0))).toBe('This file is empty.')
    expect(fileProblem(new File([new ArrayBuffer(10 * 1024 * 1024 + 1)], 'big.txt'))).toBe(
      'File too large (max 10 MB).',
    )
  })

  it('keeps Start scan disabled until there is text or a file', async () => {
    fakeApi({ [ME]: me })
    renderAt('/scans/new')
    const start = await screen.findByRole('button', { name: 'Start scan' })
    expect((start as HTMLButtonElement).disabled).toBe(true)
    fireEvent.change(screen.getByLabelText('Or paste text'), { target: { value: '   ' } })
    expect((start as HTMLButtonElement).disabled).toBe(true)
    fireEvent.change(screen.getByLabelText('Or paste text'), {
      target: { value: 'Rahul 98470 12345' },
    })
    expect((start as HTMLButtonElement).disabled).toBe(false)
  })

  it('pastes text, uploads and opens the scan', async () => {
    fakeApi({ [ME]: me })
    const { sent } = fakeXhr({ status: 202, body: { id: 'abc-1', status: 'queued' } })
    const { router } = renderAt('/scans/new')
    fireEvent.change(await screen.findByLabelText('Or paste text'), {
      target: { value: 'Rahul 98470 12345' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Start scan' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/scans/abc-1'))
    expect(sent[0]?.get('text')).toBe('Rahul 98470 12345')
    expect(sent[0]?.get('file')).toBeNull()
  })

  it('a chosen file wins over text, and can be removed', async () => {
    fakeApi({ [ME]: me })
    const { sent } = fakeXhr({ status: 202, body: { id: 'f-1', status: 'queued' } })
    const { container, router } = renderAt('/scans/new')
    await screen.findByLabelText('Or paste text')
    const input = container.querySelector('input[type=file]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [file('notes.txt')] } })
    expect(screen.getByText('notes.txt')).toBeTruthy()
    expect((screen.getByLabelText('Or paste text') as HTMLTextAreaElement).disabled).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Remove file' }))
    expect((screen.getByLabelText('Or paste text') as HTMLTextAreaElement).disabled).toBe(false)
    fireEvent.change(input, { target: { files: [file('notes.txt')] } })
    fireEvent.click(screen.getByRole('button', { name: 'Start scan' }))
    await waitFor(() => expect(router.state.location.pathname).toBe('/scans/f-1'))
    expect((sent[0]?.get('file') as File).name).toBe('notes.txt')
  })

  it('refuses a wrong file type at once, without uploading', async () => {
    fakeApi({ [ME]: me })
    const { sent } = fakeXhr({ status: 500, body: {} })
    const { container } = renderAt('/scans/new')
    await screen.findByLabelText('Or paste text')
    const input = container.querySelector('input[type=file]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [file('virus.exe')] } })
    expect(screen.getByRole('alert').textContent).toBe('Only TXT, PDF, DOCX, CSV.')
    expect((screen.getByRole('button', { name: 'Start scan' }) as HTMLButtonElement).disabled).toBe(
      true,
    )
    expect(sent).toHaveLength(0)
  })

  it('shows server errors where they belong', async () => {
    fakeApi({ [ME]: me })
    fakeXhr(
      err(422, 'invalid_request', 'Text is too long (max 200,000 characters).', 'text') as never,
    )
    renderAt('/scans/new')
    fireEvent.change(await screen.findByLabelText('Or paste text'), { target: { value: 'hello' } })
    fireEvent.click(screen.getByRole('button', { name: 'Start scan' }))
    expect(await screen.findByText('Text is too long (max 200,000 characters).')).toBeTruthy()
    expect(document.activeElement).toBe(screen.getByLabelText('Or paste text'))
  })

  it('shows the wait time when there are too many scans', async () => {
    fakeApi({ [ME]: me })
    fakeXhr(err(429, 'rate_limited', 'Too many tries. Wait 30 seconds.') as never)
    renderAt('/scans/new')
    fireEvent.change(await screen.findByLabelText('Or paste text'), { target: { value: 'hello' } })
    fireEvent.click(screen.getByRole('button', { name: 'Start scan' }))
    expect((await screen.findByRole('alert')).textContent).toBe('Too many tries. Wait 30 seconds.')
    expect((screen.getByRole('button', { name: 'Start scan' }) as HTMLButtonElement).disabled).toBe(
      false,
    )
  })
})

describe('format', () => {
  const now = new Date(2026, 10, 20, 12, 0)
  it('says today, yesterday, or the date', () => {
    expect(formatStarted(new Date(2026, 10, 20, 9, 5).toISOString(), now)).toBe('Today, 09:05')
    expect(formatStarted(new Date(2026, 10, 19, 23, 40).toISOString(), now)).toBe(
      'Yesterday, 23:40',
    )
    expect(formatStarted(new Date(2026, 10, 2, 14, 0).toISOString(), now)).toBe('2 Nov, 14:00')
    expect(formatStarted(new Date(2025, 0, 3, 14, 0).toISOString(), now)).toBe('3 Jan 2025, 14:00')
  })
})

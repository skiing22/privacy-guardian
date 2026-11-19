import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { clueWords, matchSentence } from '../features/scan/words'
import { ignoreKey } from '../features/review/keys'
import { err, fakeApi, renderAt, USER } from '../test/server'

const ID = '3f2a9c1e-0000-4000-8000-000000000001'
const ME = 'GET /api/v1/auth/me'
const GET = `GET /api/v1/scans/${ID}`
const ANSWERS = `POST /api/v1/scans/${ID}/answers`
const RETRY = `POST /api/v1/scans/${ID}/retry`
const me = { status: 200, body: USER }

const base = {
  id: ID,
  filename: 'patient_note.txt',
  format: 'txt',
  status: 'running',
  step: 2,
  step_label: 'Finding personal data',
  round: 1,
  max_rounds: 3,
  created_at: '2026-11-19T10:00:00.000Z',
  updated_at: '2026-11-19T10:00:01.000Z',
  finished_at: null,
  expires_at: '2026-11-26T10:00:00.000Z',
  review: null,
  risk: null,
  error: null,
}
const ok = (over: Record<string, unknown>) => ({ status: 200, body: { ...base, ...over } })

const item = (index: number, text: string, type = 'PERSON', family = 'identity', score = 0.58) => ({
  index,
  pii_type: type,
  family,
  score,
  reason: 'low confidence',
  context: { before: 'send the documents to ', text, after: ', Bhopal 462003' },
})
const paused = ok({
  status: 'needs_review',
  step: 3,
  updated_at: '2026-11-19T10:00:05.000Z',
  review: {
    items: [
      item(4, 'Priya'),
      item(7, '22, Nehru Nagar', 'ADDRESS', 'contact', 0.61),
      item(9, 'Kochi', 'LOCATION', 'contact'),
    ],
  },
})

const key = (k: string, target: EventTarget = document.body) =>
  act(() => {
    target.dispatchEvent(new KeyboardEvent('keydown', { key: k, bubbles: true }))
  })

describe('S4 running', () => {
  it('shows numbered steps with the current one and the leak-check round', async () => {
    fakeApi({ [ME]: me, [GET]: ok({ step: 5, round: 2, step_label: 'Checking for leaks' }) })
    renderAt(`/scans/${ID}`)
    const steps = within(await screen.findByRole('list', { name: 'Progress' })).getAllByRole(
      'listitem',
    )
    expect(steps.map((s) => s.textContent)).toEqual([
      '1Done: Reading file',
      '2Done: Finding personal data',
      '3Done: Combining results',
      '4Done: Choosing what to hide',
      '5Now: Checking for leaks, round 2 of 3',
    ])
    expect(screen.getByText('Step 5 of 5, checking for leaks, round 2 of 3')).toBeTruthy()
  })

  it('polls while running and stops once done', async () => {
    let n = 0
    const { calls } = fakeApi({
      [ME]: me,
      [GET]: () =>
        ++n < 3
          ? ok({ step: n + 1 })
          : ok({
              status: 'done',
              step: 5,
              finished_at: 'x',
              risk: { level: 'LOW', est_matches: 1750, clues: ['gender'], unresolved_leaks: 0 },
            }),
    })
    renderAt(`/scans/${ID}`)
    expect(await screen.findByText(/About 1,700 people match/, {}, { timeout: 5000 })).toBeTruthy()
    const after = calls.filter((c) => c === GET).length
    await new Promise((r) => setTimeout(r, 1300))
    expect(calls.filter((c) => c === GET).length).toBe(after) // no more polling
  }, 10000)

  it('says the model is being prepared while queued', async () => {
    fakeApi({ [ME]: me, [GET]: ok({ status: 'queued', step: 0 }) })
    vi.stubGlobal('fetch', wrapHealth(globalThis.fetch, false))
    renderAt(`/scans/${ID}`)
    expect(
      await screen.findByText('Preparing the model, about 30 seconds, only the first time.'),
    ).toBeTruthy()
  })
})

function wrapHealth(inner: typeof fetch, ready: boolean): typeof fetch {
  return (async (input: RequestInfo | URL, init?: RequestInit) =>
    String(input) === '/health'
      ? new Response(JSON.stringify({ model_ready: ready }), { status: 503 })
      : inner(input, init)) as typeof fetch
}

describe('S4 review', () => {
  it('answers everything by keyboard and submits the right payload', async () => {
    let sent: unknown = null
    fakeApi({
      [ME]: me,
      [GET]: () => (sent ? ok({ status: 'queued', step: 3 }) : paused),
      [ANSWERS]: (init) => (
        (sent = JSON.parse(String(init?.body))),
        { status: 202, body: { id: ID, status: 'queued' } }
      ),
    })
    renderAt(`/scans/${ID}`)
    expect(await screen.findByRole('heading', { name: 'Needs your answer: 1 of 3' })).toBeTruthy()
    expect(screen.getByText('Is this personal data? Name, 58% sure.')).toBeTruthy()
    expect(screen.getByText('Item 1 of 3, name, 58% sure')).toBeTruthy() // live region
    expect(screen.getByLabelText('Name, needs your answer').textContent).toBe('Priya')
    // short context: nothing was cut, so no dots
    expect(screen.getByText(/send the documents to/).textContent).toBe(
      'send the documents to Priya, Bhopal 462003',
    )
    expect(screen.queryByRole('button', { name: 'Submit answers' })).toBeNull()

    key('1')
    expect(screen.getByRole('heading', { name: 'Needs your answer: 2 of 3' })).toBeTruthy()
    key('3')
    key('2')
    const submit = await screen.findByRole('button', { name: 'Submit answers' })
    expect(document.activeElement).toBe(submit)
    fireEvent.click(submit)
    await waitFor(() =>
      expect(sent).toEqual({
        answers: [
          { index: 4, verdict: 'protect' },
          { index: 7, verdict: 'not_pii' },
          { index: 9, verdict: 'keep' },
        ],
      }),
    )
    expect(await screen.findByText('Waiting to start.')).toBeTruthy() // polling resumed
    expect(sessionStorage.getItem(`pg-answers:${ID}`)).toBeNull()
  })

  it('arrows move, Z undoes the last answer, and keys are ignored while typing', async () => {
    fakeApi({ [ME]: me, [GET]: paused })
    renderAt(`/scans/${ID}`)
    await screen.findByRole('heading', { name: 'Needs your answer: 1 of 3' })
    key('ArrowDown')
    key('ArrowDown')
    expect(screen.getByRole('heading', { name: 'Needs your answer: 3 of 3' })).toBeTruthy()
    key('ArrowUp')
    key('1')
    expect(screen.getByText('1 of 3 answered')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Undo' })).toBeTruthy()
    key('z')
    expect(screen.getByText('0 of 3 answered')).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Needs your answer: 2 of 3' })).toBeTruthy()

    const input = document.createElement('input')
    document.body.appendChild(input)
    key('1', input)
    expect(screen.getByText('0 of 3 answered')).toBeTruthy()
    input.remove()
  })

  it('the item list jumps to an item and shows each answer', async () => {
    fakeApi({ [ME]: me, [GET]: paused })
    renderAt(`/scans/${ID}`)
    const list = await screen.findByRole('list', { name: 'Items to review' })
    fireEvent.click(within(list).getByRole('button', { name: /Place: Kochi/ }))
    expect(screen.getByRole('heading', { name: 'Needs your answer: 3 of 3' })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /Keep visible/ }))
    expect(within(list).getByRole('button', { name: /Place: Kochi/ }).textContent).toContain(
      'Keep visible',
    )
  })

  it('keeps unsent answers when the session ends, and restores them after login', async () => {
    fakeApi({
      [ME]: me,
      [GET]: paused,
      [ANSWERS]: err(401, 'session_expired', 'Please log in again.'),
    })
    const first = renderAt(`/scans/${ID}`)
    await screen.findByRole('heading', { name: 'Needs your answer: 1 of 3' })
    key('1')
    key('1')
    key('3')
    fireEvent.click(await screen.findByRole('button', { name: 'Submit answers' }))
    await waitFor(() => expect(first.router.state.location.pathname).toBe('/login'))
    expect(JSON.parse(sessionStorage.getItem(`pg-answers:${ID}`) ?? '{}')).toEqual({
      4: 'protect',
      7: 'protect',
      9: 'not_pii',
    })
    first.client.clear()

    fakeApi({ [ME]: me, [GET]: paused })
    renderAt(`/scans/${ID}`)
    expect(await screen.findAllByText('3 of 3 answered')).toBeTruthy()
    sessionStorage.clear()
  })

  it('shows the PRD message when answers cannot be saved', async () => {
    fakeApi({
      [ME]: me,
      [GET]: paused,
      [ANSWERS]: err(422, 'invalid_answers', 'Answer every item once.'),
    })
    renderAt(`/scans/${ID}`)
    await screen.findByRole('heading', { name: 'Needs your answer: 1 of 3' })
    key('1')
    key('1')
    key('1')
    fireEvent.click(await screen.findByRole('button', { name: 'Submit answers' }))
    expect((await screen.findByRole('alert')).textContent).toBe(
      'Your answers could not be saved. Retry.',
    )
    sessionStorage.clear()
  })
})

describe('S4 failed, done, missing', () => {
  it('shows the failed step and retries', async () => {
    let retried = false
    fakeApi({
      [ME]: me,
      [GET]: () =>
        retried
          ? ok({ status: 'queued', step: 0 })
          : ok({
              status: 'failed',
              step: 1,
              error: {
                code: 'pdf_no_text',
                message: 'This PDF has no text (scanned image). Not supported yet.',
                step: 1,
              },
            }),
      [RETRY]: () => ((retried = true), { status: 202, body: { id: ID, status: 'queued' } }),
    })
    renderAt(`/scans/${ID}`)
    expect((await screen.findByRole('alert')).textContent).toContain('Scan failed at step 1.')
    const steps = within(screen.getByRole('list', { name: 'Progress' })).getAllByRole('listitem')
    expect(steps[0]?.textContent).toContain('Failed: Reading file')
    fireEvent.click(screen.getByRole('button', { name: 'Retry scan' }))
    expect(await screen.findByText('Waiting to start.')).toBeTruthy()
  })

  it('done: risk banner and downloads, PDF says text', async () => {
    fakeApi({
      [ME]: me,
      [GET]: ok({
        status: 'done',
        format: 'pdf',
        step: 5,
        finished_at: 'x',
        risk: { level: 'HIGH', est_matches: 3.2, clues: ['dob', 'pin'], unresolved_leaks: 1 },
      }),
    })
    renderAt(`/scans/${ID}`)
    expect(await screen.findByText('About 3 people match what is left in this file.')).toBeTruthy()
    expect(screen.getByText('High risk')).toBeTruthy()
    expect(screen.getByText('Visible clues: date of birth, PIN code.')).toBeTruthy()
    expect(screen.getByText('Do not share yet. Protect more items in the list below.')).toBeTruthy()
    expect(screen.getByText('1 item could not be removed after 3 rounds.')).toBeTruthy()
    const dl = screen.getByRole('link', { name: 'Download cleaned text (.txt)' })
    expect(dl.getAttribute('href')).toBe(`/api/v1/scans/${ID}/download?kind=cleaned`)
    expect(screen.getByText('PDFs are returned as text.')).toBeTruthy()
  })

  it('a missing scan says so plainly', async () => {
    fakeApi({ [ME]: me, [GET]: err(404, 'not_found', 'Not found.') })
    renderAt(`/scans/${ID}`)
    expect(await screen.findByRole('heading', { name: 'This scan does not exist.' })).toBeTruthy()
  })
})

describe('words', () => {
  it('rounds the match count and never says k', () => {
    expect(matchSentence(1750)).toBe('About 1,700 people match what is left in this file.')
    expect(matchSentence(1.2)).toBe('What is left in this file may point to one person.')
    expect(matchSentence(48.6)).toBe('About 48 people match what is left in this file.')
    expect(matchSentence(7.04e8, ['gender'])).toBe(
      'About 70 crore people match what is left in this file.',
    )
    expect(matchSentence(356_000, ['city'])).toBe(
      'About 3.5 lakh people match what is left in this file.',
    )
    expect(matchSentence(1.4e9, [])).toBe('No clues left in this file point to a person.')
    expect(clueWords(['gender', 'age_range', 'birth_year'])).toBe('gender, age range, birth year')
  })

  it('ignores keys while typing or with modifiers', () => {
    const area = document.createElement('textarea')
    expect(ignoreKey(new KeyboardEvent('keydown', { key: '1' }))).toBe(false)
    expect(
      ignoreKey(Object.assign(new KeyboardEvent('keydown', { key: '1', ctrlKey: true }))),
    ).toBe(true)
    const e = new KeyboardEvent('keydown', { key: '1', bubbles: true })
    area.addEventListener('keydown', (ev) => expect(ignoreKey(ev)).toBe(true))
    document.body.appendChild(area)
    area.dispatchEvent(e)
    area.remove()
  })
})

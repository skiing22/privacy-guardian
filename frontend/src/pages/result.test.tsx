import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { fakeApi, renderAt, USER } from '../test/server'

const ID = '3f2a9c1e-0000-4000-8000-0000000000aa'
const ME = 'GET /api/v1/auth/me'
const GET = `GET /api/v1/scans/${ID}`
const RESULT = `GET /api/v1/scans/${ID}/result`
const me = { status: 200, body: USER }

const status = (over: Record<string, unknown> = {}) => ({
  status: 200,
  body: {
    id: ID,
    filename: 'note.txt',
    format: 'txt',
    status: 'done',
    step: 5,
    step_label: 'Checking for leaks',
    round: 1,
    max_rounds: 3,
    created_at: 'x',
    updated_at: 'x',
    finished_at: 'x',
    expires_at: 'x',
    review: null,
    error: null,
    risk: { level: 'LOW', est_matches: 1750, clues: ['gender'], unresolved_leaks: 0 },
    ...over,
  },
})

// "😀 Rahul Sharma met Rahul Sharma. Call 98470 12345. Age 34."
// code points: 😀=0, space=1, Rahul Sharma 2-14, ...
const TEXT = '😀 Rahul Sharma met Rahul Sharma. Call 98470 12345. Age 34.'
const item = (
  idx: number,
  start: number,
  end: number,
  type: string,
  family: string,
  action: string,
  label: string,
  output: string,
  token: string | null = null,
) => ({
  idx,
  round: 1,
  start,
  end,
  pii_type: type,
  family,
  score: 0.97,
  sources: ['rules', 'ner'],
  action,
  action_label: label,
  reason: 'utility',
  reason_text: 'Best balance of privacy and usefulness for this type.',
  token,
  output,
})
const ITEMS = [
  item(
    0,
    2,
    14,
    'PERSON',
    'identity',
    'pseudonymize',
    'Replace with token',
    'PERSON_c97ab2',
    'PERSON_c97ab2',
  ),
  item(
    1,
    19,
    31,
    'PERSON',
    'identity',
    'pseudonymize',
    'Replace with token',
    'PERSON_c97ab2',
    'PERSON_c97ab2',
  ),
  item(2, 38, 49, 'PHONE', 'contact', 'mask', 'Mask', '98*** ***45'),
  item(3, 55, 57, 'AGE', 'identity', 'redact', 'Remove', '[REDACTED]'),
]
const SEGMENTS = [
  { text: '😀 ', item_idx: null },
  { text: 'PERSON_c97ab2', item_idx: 0 },
  { text: ' met ', item_idx: null },
  { text: 'PERSON_c97ab2', item_idx: 1 },
  { text: '. Call ', item_idx: null },
  { text: '98*** ***45', item_idx: 2 },
  { text: '. Age ', item_idx: null },
  { text: '[REDACTED]', item_idx: 3 },
  { text: '.', item_idx: null },
]
const result = {
  status: 200,
  body: {
    id: ID,
    rounds: 1,
    risk: null,
    original_text: TEXT,
    items: ITEMS,
    cleaned_segments: SEGMENTS,
  },
}

function wide(on: boolean) {
  vi.stubGlobal('matchMedia', (q: string) => ({
    matches: q.includes('min-width: 1024px') ? on : false,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  }))
}
const key = (k: string) =>
  act(
    () => void document.body.dispatchEvent(new KeyboardEvent('keydown', { key: k, bubbles: true })),
  )

describe('S4 result', () => {
  it('cleaned view shows each result the DESIGN 5.3 way', async () => {
    wide(false)
    fakeApi({ [ME]: me, [GET]: status(), [RESULT]: result })
    renderAt(`/scans/${ID}`)
    const sheet = await screen.findByRole('article', { name: 'Cleaned document' })
    expect(sheet.textContent).toBe(
      '😀 PERSON_c97ab2 met PERSON_c97ab2. Call 98*** ***45. Age Removed.',
    )
    const tokens = within(sheet).getAllByRole('button', {
      name: /replaced with token PERSON_c97ab2/,
    })
    expect(tokens).toHaveLength(2)
    expect(tokens[0]?.className).toContain('font-mono')
    expect(
      within(sheet).getByRole('button', { name: 'Phone, masked as 98*** ***45' }).className,
    ).toContain('underline')
    const bar = within(sheet).getByRole('button', { name: 'Age, removed' })
    expect(bar.className).toContain('bg-ink')
    expect(bar.getAttribute('style')).toContain('width: 4ch') // min width, original was "34"
  })

  it('original view marks exactly the right text, even after an emoji', async () => {
    wide(false)
    fakeApi({ [ME]: me, [GET]: status(), [RESULT]: result })
    renderAt(`/scans/${ID}`)
    await screen.findByRole('article', { name: 'Cleaned document' })
    key('o')
    const sheet = screen.getByRole('article', { name: 'Original document' })
    expect(sheet.textContent).toBe(TEXT)
    const marks = within(sheet)
      .getAllByRole('button')
      .map((b) => b.childNodes[0]?.textContent)
    expect(marks).toEqual(['Rahul Sharma', 'Rahul Sharma', '98470 12345', '34'])
  })

  it('hovering a token outlines every occurrence', async () => {
    wide(false)
    fakeApi({ [ME]: me, [GET]: status(), [RESULT]: result })
    renderAt(`/scans/${ID}`)
    const sheet = await screen.findByRole('article', { name: 'Cleaned document' })
    const [a, b] = within(sheet).getAllByRole('button', { name: /PERSON_c97ab2/ })
    fireEvent.mouseEnter(a as HTMLElement)
    expect(b?.className).toContain('ring-2')
    fireEvent.mouseLeave(a as HTMLElement)
    expect(b?.className).not.toContain('ring-2')
  })

  it('item list: values, reasons, and selection both ways', async () => {
    wide(false)
    fakeApi({ [ME]: me, [GET]: status(), [RESULT]: result })
    renderAt(`/scans/${ID}`)
    const list = await screen.findByRole('list', { name: 'Items' })
    expect(screen.getByRole('heading', { name: '4 items' })).toBeTruthy()
    const rows = within(list).getAllByRole('button')
    expect(rows[2]?.textContent).toContain('98470 12345')
    expect(rows[2]?.textContent).toContain('Found by rules and the model, 97% sure.')
    fireEvent.click(rows[2] as HTMLElement)
    expect(
      screen
        .getByRole('button', { name: 'Phone, masked as 98*** ***45' })
        .getAttribute('aria-pressed'),
    ).toBe('true')
    key('ArrowDown')
    expect(rows[3]?.getAttribute('aria-pressed')).toBe('true')
    fireEvent.click(
      screen.getAllByRole('button', { name: /replaced with token/ })[0] as HTMLElement,
    )
    expect(rows[0]?.getAttribute('aria-pressed')).toBe('true')
  })

  it('compare shows both sheets on wide screens only', async () => {
    wide(true)
    fakeApi({ [ME]: me, [GET]: status(), [RESULT]: result })
    renderAt(`/scans/${ID}`)
    await screen.findByRole('article', { name: 'Cleaned document' })
    key('b')
    expect(screen.getByRole('article', { name: 'Original document' })).toBeTruthy()
    expect(screen.getByRole('article', { name: 'Cleaned document' })).toBeTruthy()
    expect(screen.getByRole('radio', { name: 'Compare' }).getAttribute('aria-checked')).toBe('true')
  })

  it('no compare option on narrow screens', async () => {
    wide(false)
    fakeApi({ [ME]: me, [GET]: status(), [RESULT]: result })
    renderAt(`/scans/${ID}`)
    await screen.findByRole('article', { name: 'Cleaned document' })
    expect(screen.queryByRole('radio', { name: 'Compare' })).toBeNull()
    key('b')
    expect(screen.queryByRole('article', { name: 'Original document' })).toBeNull()
  })

  it('says when nothing was found', async () => {
    wide(false)
    fakeApi({
      [ME]: me,
      [GET]: status({ risk: { level: 'LOW', est_matches: 1.4e9, clues: [], unresolved_leaks: 0 } }),
      [RESULT]: {
        status: 200,
        body: {
          id: ID,
          rounds: 1,
          risk: null,
          original_text: 'name,phone\n',
          items: [],
          cleaned_segments: [{ text: 'name,phone\n', item_idx: null }],
        },
      },
    })
    renderAt(`/scans/${ID}`)
    expect(await screen.findByText('No personal data found.')).toBeTruthy()
    expect(screen.getByText('No clues left in this file point to a person.')).toBeTruthy()
  })

  it('plays the redaction pass only when the scan finishes while watching', async () => {
    wide(false)
    let done = false
    fakeApi({
      [ME]: me,
      [GET]: () => (done ? status() : status({ status: 'running', risk: null, finished_at: null })),
      [RESULT]: result,
    })
    renderAt(`/scans/${ID}`)
    await screen.findByRole('list', { name: 'Progress' })
    done = true
    const sheet = await screen.findByRole(
      'article',
      { name: 'Cleaned document' },
      { timeout: 3000 },
    )
    const first = within(sheet).getAllByRole('button')[0]
    expect(first?.className).toContain('animate-[redact')
    await waitFor(() => expect(first?.className).not.toContain('animate-[redact'), {
      timeout: 2500,
    })
  })

  it('opening a finished scan shows the result at once, no animation', async () => {
    wide(false)
    fakeApi({ [ME]: me, [GET]: status(), [RESULT]: result })
    renderAt(`/scans/${ID}`)
    const sheet = await screen.findByRole('article', { name: 'Cleaned document' })
    expect(within(sheet).getAllByRole('button')[0]?.className).not.toContain('animate-')
  })
})

import { act, fireEvent, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { VerifyOut } from '../api/admin'
import { verifySentence } from '../features/admin/words'
import { ADMIN, err, fakeApi, renderAt, USER } from '../test/server'

const ME = 'GET /api/v1/auth/me'
const RULES = 'GET /api/v1/admin/rules'
const PUT = 'PUT /api/v1/admin/rules'
const REVEAL = 'POST /api/v1/admin/reveal'
const RESET = 'POST /api/v1/admin/beliefs/reset'
const AUDIT = 'GET /api/v1/admin/audit?limit=50'
const VERIFY = 'POST /api/v1/admin/audit/verify'
const ANCHOR = 'POST /api/v1/admin/audit/anchor'
const admin = { status: 200, body: ADMIN }

const rule = (t: string, family: string, allowed: string[], action: string | null = null) => ({
  pii_type: t,
  family,
  action,
  allowed_actions: allowed,
  updated_at: null,
})
const RULE_LIST = {
  status: 200,
  body: {
    rules: [
      rule('PERSON', 'identity', ['keep', 'pseudonymize', 'redact']),
      rule('AGE', 'identity', ['keep', 'generalize', 'redact']),
      rule('PHONE', 'contact', ['keep', 'mask', 'pseudonymize', 'redact'], 'mask'),
      rule('AADHAAR', 'id', ['keep', 'mask', 'pseudonymize', 'redact']),
      rule('DATE', 'other', ['keep', 'generalize', 'redact']),
    ],
  },
}

describe('S5 rules and vault', () => {
  it('normal users cannot open the admin pages', async () => {
    const { calls } = fakeApi({ [ME]: { status: 200, body: USER } })
    renderAt('/admin/rules')
    expect(await screen.findByRole('heading', { name: 'Only admins can do this.' })).toBeTruthy()
    expect(calls).not.toContain(RULES) // no admin request is even sent
  })

  it('groups rules by family, offers only allowed actions, saves the full set', async () => {
    let body: unknown = null
    fakeApi({
      [ME]: admin,
      [RULES]: RULE_LIST,
      [PUT]: (init) => {
        body = JSON.parse(String(init?.body))
        return RULE_LIST
      },
    })
    renderAt('/admin/rules')
    const group = await screen.findByRole('group', { name: 'Who someone is' })
    const age = within(group).getByLabelText('Age') as HTMLSelectElement
    expect([...age.options].map((o) => o.text)).toEqual([
      'Automatic',
      'Keep',
      'Generalize',
      'Remove',
    ])
    expect((screen.getByLabelText('Phone') as HTMLSelectElement).value).toBe('mask')
    expect(
      screen.getByText('1 of 5 types have a fixed action. The rest use automatic choice.'),
    ).toBeTruthy()
    const save = screen.getByRole('button', { name: 'Save rules' }) as HTMLButtonElement
    expect(save.disabled).toBe(true) // nothing changed yet
    fireEvent.change(age, { target: { value: 'generalize' } })
    fireEvent.click(save)
    expect(await screen.findByText('Rules saved')).toBeTruthy()
    expect(body).toEqual({
      rules: [
        { pii_type: 'PERSON', action: null },
        { pii_type: 'AGE', action: 'generalize' },
        { pii_type: 'PHONE', action: 'mask' },
        { pii_type: 'AADHAAR', action: null },
        { pii_type: 'DATE', action: null },
      ],
    })
  })

  it('show a real value: checks, confirms, shows, hides and forgets', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const { calls } = fakeApi({
      [ME]: admin,
      [RULES]: RULE_LIST,
      [REVEAL]: {
        status: 200,
        body: { token: 'PERSON_c97ab2', pii_type: 'PERSON', value: 'Arjun Nair', logged_as: 214 },
      },
    })
    const { client } = renderAt('/admin/rules')
    const tokenField = await screen.findByLabelText('Token')
    fireEvent.click(screen.getByRole('button', { name: 'Show value' }))
    expect(screen.getByText('Enter a token like PERSON_c97ab2.')).toBeTruthy()
    fireEvent.change(tokenField, { target: { value: 'PERSON_c97ab2' } })
    fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'short' } })
    fireEvent.click(screen.getByRole('button', { name: 'Show value' }))
    expect(screen.getByText('Reason must be at least 10 characters.')).toBeTruthy()
    expect(calls).not.toContain(REVEAL)

    fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'court order 2026/77' } })
    fireEvent.click(screen.getByRole('button', { name: 'Show value' }))
    const dialog = screen.getByRole('dialog', { name: 'Show the real value of PERSON_c97ab2?' })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Show value' }))
    expect(await screen.findByText('Arjun Nair')).toBeTruthy()
    expect(screen.getByText('Value shown and logged as record 214.')).toBeTruthy()
    // the value is in no cache
    expect(
      JSON.stringify(
        client
          .getQueryCache()
          .getAll()
          .map((q) => q.state.data),
      ),
    ).not.toContain('Arjun')
    expect(
      JSON.stringify(
        client
          .getMutationCache()
          .getAll()
          .map((m) => m.state.data),
      ),
    ).not.toContain('Arjun')

    await act(async () => void (await vi.advanceTimersByTimeAsync(61_000)))
    expect(screen.queryByText('Arjun Nair')).toBeNull() // hid itself
    vi.useRealTimers()
  })

  it('hiding pauses while the pointer is on the value', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    fakeApi({
      [ME]: admin,
      [RULES]: RULE_LIST,
      [REVEAL]: {
        status: 200,
        body: { token: 'PERSON_c97ab2', pii_type: 'PERSON', value: 'Arjun Nair', logged_as: 1 },
      },
    })
    renderAt('/admin/rules')
    fireEvent.change(await screen.findByLabelText('Token'), { target: { value: 'PERSON_c97ab2' } })
    fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'court order 2026/77' } })
    fireEvent.click(screen.getByRole('button', { name: 'Show value' }))
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Show value' }))
    const box = await screen.findByRole('region', { name: 'Real value' })
    fireEvent.mouseEnter(box)
    await act(async () => void (await vi.advanceTimersByTimeAsync(90_000)))
    expect(screen.getByText('Arjun Nair')).toBeTruthy()
    expect(screen.getByText('Hiding paused')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Hide' }))
    expect(screen.queryByText('Arjun Nair')).toBeNull()
    vi.useRealTimers()
  })

  it('maps reveal errors to the PRD wording', async () => {
    fakeApi({
      [ME]: admin,
      [RULES]: RULE_LIST,
      [REVEAL]: err(404, 'unknown_token', 'Unknown token.', 'token'),
    })
    renderAt('/admin/rules')
    fireEvent.change(await screen.findByLabelText('Token'), { target: { value: 'PERSON_000000' } })
    fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'court order 2026/77' } })
    fireEvent.click(screen.getByRole('button', { name: 'Show value' }))
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Show value' }))
    expect(await screen.findByText('Unknown token.')).toBeTruthy()
  })

  it('reset learning asks first', async () => {
    const { calls } = fakeApi({ [ME]: admin, [RULES]: RULE_LIST, [RESET]: { status: 204 } })
    renderAt('/admin/rules')
    fireEvent.click(await screen.findByRole('button', { name: 'Reset learning' }))
    const dialog = screen.getByRole('dialog', { name: 'Reset what the tool has learned?' })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Reset learning' }))
    expect(await screen.findByText('Learning reset')).toBeTruthy()
    expect(calls).toContain(RESET)
  })
})

const entry = (
  seq: number,
  event: string,
  label: string,
  details: Record<string, unknown>,
  actor: { type: string; id: number | null; email: string | null } = {
    type: 'user',
    id: 2,
    email: 'boss@example.com',
  },
) => ({
  seq,
  ts: '2026-11-19T10:00:00.000Z',
  actor,
  event,
  event_label: label,
  details,
})
const AUDIT_PAGE = {
  status: 200,
  body: {
    items: [
      entry(3, 'reidentify', 'Real value shown', {
        token: 'PERSON_c97ab2',
        reason: 'court order 2026/77',
      }),
      entry(2, 'scan_completed', 'Scan finished', {
        scan: '3f2a9c1e-aaaa',
        risk: 'LOW',
        rounds: 1,
      }),
      entry(
        1,
        'retention',
        'Old data deleted',
        { scans: 2, sessions: 0, vault: 1, files: 0 },
        { type: 'system', id: null, email: null },
      ),
    ],
    next_before_seq: 1,
  },
}

describe('S6 audit log', () => {
  it('shows events in plain words with tokens in mono', async () => {
    fakeApi({ [ME]: admin, [AUDIT]: AUDIT_PAGE })
    renderAt('/admin/audit')
    const table = await screen.findByRole('table')
    const rows = within(table).getAllByRole('row').slice(1)
    expect(rows[0]?.textContent).toContain('PERSON_c97ab2, reason: court order 2026/77')
    expect(within(rows[0] as HTMLElement).getByText('PERSON_c97ab2').className).toContain(
      'font-mono',
    )
    expect(rows[1]?.textContent).toContain('scan 3f2a9c1e, low risk')
    expect(rows[2]?.textContent).toContain('System')
    expect(rows[2]?.textContent).toContain('2 scans, 1 stored value deleted')
  })

  it('verify ok names the anchor', async () => {
    fakeApi({
      [ME]: admin,
      [AUDIT]: AUDIT_PAGE,
      [VERIFY]: {
        status: 200,
        body: {
          ok: true,
          checked: 214,
          first_bad_seq: null,
          reason: null,
          anchor: { seq: 200, saved_at: '2026-11-19T10:00:00.000Z' },
        },
      },
    })
    renderAt('/admin/audit')
    await screen.findByRole('table')
    fireEvent.click(screen.getByRole('button', { name: 'Verify log' }))
    expect((await screen.findByText(/All 214 records check out/)).textContent).toMatch(
      /^All 214 records check out and match the anchor saved on .+\.$/,
    )
  })

  it('verify finds tampering, loads older pages and outlines the row', async () => {
    fakeApi({
      [ME]: admin,
      [AUDIT]: AUDIT_PAGE,
      'GET /api/v1/admin/audit?limit=50&before_seq=1': {
        status: 200,
        body: {
          items: [entry(0, 'user_created', 'User added', { user_id: 2, role: 'admin' })],
          next_before_seq: null,
        },
      },
      [VERIFY]: {
        status: 200,
        body: { ok: false, checked: 4, first_bad_seq: 0, reason: 'payload changed', anchor: null },
      },
    })
    renderAt('/admin/audit')
    await screen.findByRole('table')
    fireEvent.click(screen.getByRole('button', { name: 'Verify log' }))
    expect(await screen.findByText('Record 0 was changed after it was saved.')).toBeTruthy()
    const row = await screen.findByRole('row', { name: 'Record 0, changed after it was saved' })
    expect(row.className).toContain('outline-risk-high')
  })

  it('save anchor shows the code to keep off the server', async () => {
    fakeApi({
      [ME]: admin,
      [AUDIT]: AUDIT_PAGE,
      [ANCHOR]: { status: 200, body: { seq: 4, mac_prefix: '3f9a0c1d2e3f4a5b', saved_at: 'x' } },
    })
    renderAt('/admin/audit')
    await screen.findByRole('table')
    fireEvent.click(screen.getByRole('button', { name: 'Save anchor' }))
    expect(await screen.findByText('3f9a0c1d2e3f4a5b')).toBeTruthy()
    await waitFor(() => expect(screen.getByText(/Anchor saved at record 4/)).toBeTruthy())
  })

  it('empty log', async () => {
    fakeApi({ [ME]: admin, [AUDIT]: { status: 200, body: { items: [], next_before_seq: null } } })
    renderAt('/admin/audit')
    expect(await screen.findByText('No events yet.')).toBeTruthy()
  })
})

describe('verify words', () => {
  const v = (reason: string, seq = 7): VerifyOut => ({
    ok: false,
    checked: 9,
    first_bad_seq: seq,
    reason,
    anchor: null,
  })
  it('covers every reason the server gives', () => {
    expect(verifySentence(v('mac mismatch (record edited)'))).toBe(
      'Record 7 was changed after it was saved.',
    )
    expect(verifySentence(v('chain broken (record removed or inserted)'))).toBe(
      'A record was removed or added before record 7.',
    )
    expect(verifySentence(v('log is shorter than anchor (truncated)'))).toBe(
      'The log ends before the saved anchor at record 7: records were deleted.',
    )
    expect(verifySentence(v('does not match anchor (chain rewritten)'))).toBe(
      'The log does not match the anchor saved at record 7: it was rewritten.',
    )
    expect(
      verifySentence({ ok: true, checked: 3, first_bad_seq: null, reason: null, anchor: null }),
    ).toBe('All 3 records check out. No anchor saved yet.')
  })
})

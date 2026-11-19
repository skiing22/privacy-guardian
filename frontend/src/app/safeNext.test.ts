import { describe, expect, it } from 'vitest'
import { loginPath, safeNext } from './safeNext'

describe('safeNext (no open redirect)', () => {
  it.each([
    ['/scans/42?view=clean#item-3', '/scans/42?view=clean#item-3'],
    ['/admin/audit', '/admin/audit'],
  ])('keeps app paths: %s', (input, out) => expect(safeNext(input)).toBe(out))

  it.each([
    null,
    '',
    'https://evil.example',
    '//evil.example/scans',
    '/\\evil.example',
    'javascript:alert(1)',
    '/login',
    '/login?next=/scans',
    'scans',
  ])('refuses %s', (input) => expect(safeNext(input)).toBe('/scans'))

  it('builds the login link', () => {
    expect(loginPath('/scans/7?x=1')).toBe('/login?next=%2Fscans%2F7%3Fx%3D1')
  })
})

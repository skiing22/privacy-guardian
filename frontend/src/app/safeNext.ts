/**
 * Where to go after login. Only paths inside this app are allowed, so a crafted link
 * like /login?next=https://evil.example cannot send a user off site (open redirect).
 */
const FALLBACK = '/scans'

export function safeNext(next: string | null | undefined): string {
  if (!next || !next.startsWith('/')) return FALLBACK
  if (next.startsWith('//') || next.startsWith('/\\')) return FALLBACK
  // The URL parser is the judge: anything that resolves off this origin is refused.
  const base = 'http://app.invalid'
  let url: URL
  try {
    url = new URL(next, base)
  } catch {
    return FALLBACK
  }
  if (url.origin !== base) return FALLBACK
  if (url.pathname === '/login') return FALLBACK
  return url.pathname + url.search + url.hash
}

export function loginPath(current: string): string {
  return `/login?next=${encodeURIComponent(safeNext(current))}`
}

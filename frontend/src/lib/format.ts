/** Dates and sizes in plain words (DESIGN 3.2, 13). Times are the viewer's local time. */

const time = new Intl.DateTimeFormat('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false })
const dayMonth = new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short' })
const dayMonthYear = new Intl.DateTimeFormat('en-IN', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
})

function sameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  )
}

/** "Today, 23:40", "Yesterday, 09:05", "12 Nov, 14:00", "3 Jan 2025, 14:00". */
export function formatStarted(iso: string, now: Date = new Date()): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const t = time.format(d)
  if (sameDay(d, now)) return `Today, ${t}`
  const y = new Date(now)
  y.setDate(now.getDate() - 1)
  if (sameDay(d, y)) return `Yesterday, ${t}`
  const day = d.getFullYear() === now.getFullYear() ? dayMonth.format(d) : dayMonthYear.format(d)
  return `${day}, ${t}`
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} bytes`
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

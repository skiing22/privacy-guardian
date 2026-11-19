/**
 * API 4.9: item offsets count Unicode code points (Python string indices). JavaScript
 * strings count UTF-16 units, so an emoji before an item would shift every mark if we
 * used text.slice. Everything here works on code points.
 */
export type Piece<T> = { text: string; item: T | null }

/**
 * Split `text` into plain pieces and item pieces. Items are [start, end) in code points.
 * Overlapping or out-of-range items are skipped (never crash, never duplicate text):
 * joining all pieces always gives back `text` exactly.
 */
export function splitByCodePoints<T extends { start: number; end: number }>(
  text: string,
  items: readonly T[],
): Piece<T>[] {
  const cps = Array.from(text)
  const sorted = [...items].sort((a, b) => a.start - b.start || a.end - b.end)
  const out: Piece<T>[] = []
  let pos = 0
  for (const it of sorted) {
    if (it.start < pos || it.end <= it.start || it.end > cps.length) continue
    if (it.start > pos) out.push({ text: cps.slice(pos, it.start).join(''), item: null })
    out.push({ text: cps.slice(it.start, it.end).join(''), item: it })
    pos = it.end
  }
  if (pos < cps.length) out.push({ text: cps.slice(pos).join(''), item: null })
  return out
}

export function codePointLength(s: string): number {
  return Array.from(s).length
}

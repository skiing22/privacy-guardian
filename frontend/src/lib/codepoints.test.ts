import { describe, expect, it } from 'vitest'
import { splitByCodePoints } from './codepoints'

// Small seeded random generator: the same "random" cases on every run.
function rng(seed: number) {
  return () => {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff
    return seed / 0x7fffffff
  }
}

const ALPHABET = ['a', 'b', ' ', '\n', 'é', '😀', '👍🏽', 'ग', '中']

describe('splitByCodePoints', () => {
  it('marks the right letters after an emoji (API 4.9)', () => {
    const text = '😀👍🏽 Rahul Sharma called'
    // Python offsets: 😀=1, 👍=1, 🏽=1, space=1 -> "Rahul Sharma" starts at 4
    const pieces = splitByCodePoints(text, [{ start: 4, end: 16 }])
    expect(pieces.find((p) => p.item)?.text).toBe('Rahul Sharma')
    expect(text.slice(4, 16)).not.toBe('Rahul Sharma') // the bug this guards against
  })

  it('property: pieces join back to the text, and each item piece is its code-point slice', () => {
    const r = rng(42)
    for (let run = 0; run < 500; run++) {
      const n = Math.floor(r() * 30)
      const cps = Array.from(
        { length: n },
        () => ALPHABET[Math.floor(r() * ALPHABET.length)] ?? 'a',
      )
      const text = cps.join('')
      const len = Array.from(text).length
      const items = Array.from({ length: Math.floor(r() * 6) }, () => {
        const a = Math.floor(r() * (len + 2))
        return { start: a, end: a + Math.floor(r() * 5) }
      })
      const pieces = splitByCodePoints(text, items)
      expect(pieces.map((p) => p.text).join('')).toBe(text)
      for (const p of pieces) {
        if (p.item) expect(p.text).toBe(Array.from(text).slice(p.item.start, p.item.end).join(''))
        expect(p.text.length).toBeGreaterThan(0)
      }
    }
  })

  it('skips overlapping and out-of-range items instead of duplicating text', () => {
    const pieces = splitByCodePoints('abcdef', [
      { start: 0, end: 3 },
      { start: 2, end: 4 },
      { start: 5, end: 99 },
      { start: 4, end: 4 },
    ])
    expect(pieces.map((p) => [p.text, !!p.item])).toEqual([
      ['abc', true],
      ['def', false],
    ])
  })
})

import { useMemo, useState } from 'react'
import type { ResultItem, Segment } from '../../api/scan'
import { codePointLength, splitByCodePoints } from '../../lib/codepoints'
import { typeName, type Family } from '../../ui/TypeLabel'
import { SheetItem } from './SheetItem'

// DESIGN 4.4: the sheet fits 72 characters of Body 7 plus 48 px padding; paper on the desk.
const SHEET =
  'rounded-sm bg-paper shadow-sheet p-6 sm:p-12 body-7 text-ink whitespace-pre-wrap break-words max-w-[calc(72ch+96px)]'

const FILL: Record<Family, string> = {
  identity: 'bg-hl-identity',
  contact: 'bg-hl-contact',
  id: 'bg-hl-id',
  other: 'bg-hl-other',
}
const LINE: Record<Family, string> = {
  identity: 'decoration-hl-identity',
  contact: 'decoration-hl-contact',
  id: 'decoration-hl-id',
  other: 'decoration-rule-strong',
}

type Common = {
  items: Map<number, ResultItem>
  selected: number | null
  onSelect: (idx: number) => void
}

// ---------------------------------------------------------------- original

export function OriginalSheet({ text, items, selected, onSelect }: Common & { text: string }) {
  // Only round 1 items have offsets in the original text (API 4.9).
  const pieces = useMemo(
    () =>
      splitByCodePoints(
        text,
        [...items.values()].filter((i) => i.round === 1),
      ),
    [text, items],
  )
  return (
    <article aria-label="Original document" className={SHEET}>
      {pieces.map((p, k) =>
        p.item ? (
          <SheetItem
            key={k}
            id={`o-${p.item.idx}`}
            item={p.item}
            selected={selected === p.item.idx}
            onSelect={onSelect}
            label={`${typeName(p.item.pii_type)}: ${p.text}. ${p.item.action_label}`}
            className={`${FILL[p.item.family]}`}
          >
            {p.text}
          </SheetItem>
        ) : (
          <span key={k}>{p.text}</span>
        ),
      )}
    </article>
  )
}

// ---------------------------------------------------------------- cleaned

type CleanedProps = Common & { segments: Segment[]; animate: boolean }

const STAGGER_MS = 30
const MAX_DELAY_MS = 1000 // + 500 ms animation = the 1.5 s cap (DESIGN 9)

export function CleanedSheet({ segments, items, selected, onSelect, animate }: CleanedProps) {
  const [hoverToken, setHoverToken] = useState<string | null>(null)
  let order = 0
  return (
    <article aria-label="Cleaned document" className={SHEET}>
      {segments.map((s, k) => {
        const item = s.item_idx === null ? undefined : items.get(s.item_idx)
        if (!item) return <span key={k}>{s.text}</span>
        const delay = animate ? Math.min(order++ * STAGGER_MS, MAX_DELAY_MS) : 0
        const style = animate ? { animationDelay: `${delay}ms` } : undefined
        const motion = animate ? 'motion-safe:animate-[redact_500ms_var(--ease-base)_both]' : ''
        const name = typeName(item.pii_type)
        const common = {
          id: `c-${item.idx}`,
          item,
          selected: selected === item.idx,
          onSelect,
          style,
        }
        switch (item.action) {
          case 'pseudonymize': {
            const same = hoverToken !== null && hoverToken === item.token
            return (
              <SheetItem
                key={k}
                {...common}
                label={`${name}, replaced with token ${s.text}`}
                onHover={(h) => setHoverToken(h ? item.token : null)}
                className={`font-mono text-[0.9em] ${FILL[item.family]} ${same ? 'ring-2 ring-sign' : ''} ${motion}`}
              >
                {s.text}
              </SheetItem>
            )
          }
          case 'mask':
            return (
              <SheetItem
                key={k}
                {...common}
                label={`${name}, masked as ${s.text}`}
                className={`underline decoration-[3px] underline-offset-4 ${LINE[item.family]} ${motion}`}
              >
                {s.text}
              </SheetItem>
            )
          case 'generalize':
            return (
              <SheetItem
                key={k}
                {...common}
                label={`${name}, generalized to ${s.text}`}
                className={`underline decoration-dotted decoration-[3px] underline-offset-4 ${LINE[item.family]} ${motion}`}
              >
                {s.text}
              </SheetItem>
            )
          case 'redact': {
            const width = Math.max(4, Math.min(40, item.end - item.start))
            return (
              <SheetItem
                key={k}
                {...common}
                label={`${name}, removed`}
                className={`inline-block align-middle h-[1.1em] bg-ink ${motion}`}
                style={{ ...style, width: `${width}ch` }}
              >
                <span className="sr-only">Removed</span>
              </SheetItem>
            )
          }
          default: // keep
            return (
              <SheetItem
                key={k}
                {...common}
                label={`${name}, kept visible: ${s.text}`}
                className=""
              >
                {s.text}
              </SheetItem>
            )
        }
      })}
    </article>
  )
}

export function valueOf(text: string, item: ResultItem): string | null {
  if (item.round !== 1) return null
  const cps = Array.from(text)
  return item.end <= cps.length ? cps.slice(item.start, item.end).join('') : null
}

export { codePointLength }

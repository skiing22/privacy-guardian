import type { ResultItem } from '../../api/scan'
import { TypeLabel } from '../../ui/TypeLabel'
import { foundBy } from './words'

/**
 * DESIGN 5.5: facts on line 1 (type, value, action), reason on line 2. Selecting a row
 * selects the item on the sheet. Values are the user's own document, shown to the owner
 * only (API 4.9).
 */
type Props = {
  items: ResultItem[]
  values: Map<number, string | null>
  selected: number | null
  onSelect: (idx: number) => void
}

export function ItemList({ items, values, selected, onSelect }: Props) {
  if (items.length === 0) {
    return <p className="body-3 text-ink-muted py-6 text-center">No personal data found.</p>
  }
  return (
    <ul aria-label="Items" className="flex flex-col">
      {items.map((it) => {
        const value = values.get(it.idx)
        const on = selected === it.idx
        return (
          <li key={it.idx}>
            <button
              type="button"
              id={`row-${it.idx}`}
              aria-pressed={on}
              onClick={() => onSelect(it.idx)}
              className={[
                'w-full text-left flex flex-col gap-1 px-3 py-3 border-b border-rule',
                'transition-colors duration-200 ease-base hover:bg-desk scroll-mt-28',
                'focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-sign',
                on ? 'bg-sign-soft outline-2 -outline-offset-2 outline-sign' : '',
              ].join(' ')}
            >
              <span className="flex items-baseline gap-3 flex-wrap">
                <TypeLabel piiType={it.pii_type} family={it.family} />
                <span className="title-3 text-ink break-all">
                  {value ?? <span className="text-ink-muted">Found in the leak check</span>}
                </span>
                <span className="body-6 text-ink ml-auto">{it.action_label}</span>
              </span>
              <span className="body-6 text-ink-muted">
                {foundBy(it.sources, it.score)} {it.reason_text}
              </span>
            </button>
          </li>
        )
      })}
    </ul>
  )
}

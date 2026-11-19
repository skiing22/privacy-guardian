import type { KeyboardEvent, ReactNode } from 'react'
import type { ResultItem } from '../../api/scan'
import { typeName } from '../../ui/TypeLabel'

/**
 * One item on a sheet (DESIGN 5.2, 11): focusable in reading order, a type label above it
 * on hover or focus, Enter or click selects it. States: focus ring, selected outline.
 */
type Props = {
  id: string
  item: ResultItem
  selected: boolean
  label: string
  className: string
  onSelect: (idx: number) => void
  onHover?: ((hovering: boolean) => void) | undefined
  children: ReactNode
  /** DESIGN 5.3 Keep: original text, plain, so no marker padding either. */
  plain?: boolean
  style?: React.CSSProperties | undefined
}

export function SheetItem({
  id,
  item,
  selected,
  label,
  className,
  onSelect,
  onHover,
  children,
  plain = false,
  style,
}: Props) {
  function onKey(e: KeyboardEvent) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      onSelect(item.idx)
    } else if (e.key === 'Escape') {
      ;(e.currentTarget as HTMLElement).blur()
    }
  }
  return (
    <span
      id={id}
      role="button"
      tabIndex={0}
      aria-label={label}
      aria-pressed={selected}
      data-idx={item.idx}
      // The hover label is a CSS pseudo-element: it is never copied with the document
      // text and never read twice by screen readers (the aria-label already says it).
      data-label={`${typeName(item.pii_type)}, ${Math.round(item.score * 100)}% sure`}
      onClick={() => onSelect(item.idx)}
      onKeyDown={onKey}
      onMouseEnter={() => onHover?.(true)}
      onMouseLeave={() => onHover?.(false)}
      onFocus={() => onHover?.(true)}
      onBlur={() => onHover?.(false)}
      style={style}
      className={[
        'relative cursor-pointer rounded-sm box-decoration-clone scroll-mt-28',
        plain ? '' : 'px-0.5',
        'after:pointer-events-none after:absolute after:left-0 after:bottom-full after:mb-1 after:z-10',
        'after:hidden after:whitespace-nowrap after:rounded-sm after:bg-ink after:px-1.5 after:py-0.5',
        'after:caption-4 after:text-white after:font-sans after:content-[attr(data-label)]',
        'hover:after:block focus-visible:after:block',
        'focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-sign',
        selected ? 'outline-2 outline-offset-1 outline-sign' : '',
        className,
      ].join(' ')}
    >
      {children}
    </span>
  )
}

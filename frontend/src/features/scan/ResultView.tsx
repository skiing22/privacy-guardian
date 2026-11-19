import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ResultItem, ScanResult } from '../../api/scan'
import { prefersReducedMotion, useMediaQuery } from '../../lib/useMediaQuery'
import { SegmentedControl } from '../../ui/SegmentedControl'
import { ignoreKey } from '../review/keys'
import { ItemList } from './ItemList'
import { CleanedSheet, OriginalSheet, valueOf } from './Sheets'

/**
 * S4 done (DESIGN 12): view switch, sheet(s), item list. Keyboard (DESIGN 9): O C B switch
 * views, ↑ ↓ select items, Enter jumps to the selected item on the sheet.
 * Compare needs room for two sheets, so it exists only from 1024 px.
 */
type View = 'original' | 'cleaned' | 'compare'

type Props = { result: ScanResult; animate: boolean }

export function ResultView({ result, animate }: Props) {
  const wide = useMediaQuery('(min-width: 1024px)')
  const [view, setView] = useState<View>('cleaned')
  const [selected, setSelected] = useState<number | null>(null)
  const items = useMemo(() => new Map(result.items.map((i) => [i.idx, i])), [result.items])
  const values = useMemo(
    () => new Map(result.items.map((i) => [i.idx, valueOf(result.original_text, i)])),
    [result],
  )
  const shown = view === 'compare' && !wide ? 'cleaned' : view

  const reveal = useCallback(
    (idx: number, focus: boolean) => {
      const prefix = shown === 'original' ? 'o' : 'c'
      const el = document.getElementById(`${prefix}-${idx}`) ?? document.getElementById(`o-${idx}`)
      el?.scrollIntoView?.({
        block: 'center',
        behavior: prefersReducedMotion() ? 'auto' : 'smooth',
      })
      if (focus) el?.focus({ preventScroll: true })
    },
    [shown],
  )

  const select = useCallback(
    (idx: number) => {
      setSelected(idx)
      reveal(idx, false)
      document.getElementById(`row-${idx}`)?.scrollIntoView?.({ block: 'nearest' })
    },
    [reveal],
  )

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (ignoreKey(e)) return
      const k = e.key.toLowerCase()
      const list: ResultItem[] = result.items
      const at = list.findIndex((i) => i.idx === selected)
      if (k === 'o') setView('original')
      else if (k === 'c') setView('cleaned')
      else if (k === 'b' && wide) setView('compare')
      else if (e.key === 'ArrowDown' && list.length) {
        const next = list[Math.min(list.length - 1, at + 1)]
        if (next) select(next.idx)
      } else if (e.key === 'ArrowUp' && list.length) {
        const prev = list[Math.max(0, at - 1)]
        if (prev) select(prev.idx)
      } else if (
        e.key === 'Enter' &&
        selected !== null &&
        !(e.target instanceof HTMLButtonElement)
      ) {
        reveal(selected, true)
      } else return
      e.preventDefault()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [result.items, selected, select, reveal, wide])

  const options = [
    { value: 'original' as const, label: 'Original' },
    { value: 'cleaned' as const, label: 'Cleaned' },
    ...(wide ? [{ value: 'compare' as const, label: 'Compare' }] : []),
  ]

  const cleaned = (
    <CleanedSheet
      segments={result.cleaned_segments}
      items={items}
      selected={selected}
      onSelect={select}
      animate={animate}
    />
  )
  const original = (
    <OriginalSheet
      text={result.original_text}
      items={items}
      selected={selected}
      onSelect={select}
    />
  )

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-4 flex-wrap">
        <SegmentedControl label="View" value={shown} options={options} onChange={setView} />
        <p className="caption-2 text-ink-muted hidden sm:block">
          Keys: O original, C cleaned{wide ? ', B compare' : ''}, ↑ ↓ items, Enter show on page.
        </p>
      </div>

      {shown === 'compare' ? (
        <div className="flex flex-col gap-6">
          <div className="grid grid-cols-2 gap-6 items-start">
            <div className="flex flex-col gap-2 min-w-0">
              <h2 className="title-4 text-ink-muted">Original</h2>
              {original}
            </div>
            <div className="flex flex-col gap-2 min-w-0">
              <h2 className="title-4 text-ink-muted">Cleaned</h2>
              {cleaned}
            </div>
          </div>
          <Panel items={result.items} values={values} selected={selected} onSelect={select} />
        </div>
      ) : (
        <div className="flex flex-col lg:flex-row gap-6 items-start">
          <div className="flex-1 min-w-0 w-full">{shown === 'original' ? original : cleaned}</div>
          <div className="w-full lg:w-[360px] lg:shrink-0 lg:sticky lg:top-28">
            <Panel items={result.items} values={values} selected={selected} onSelect={select} />
          </div>
        </div>
      )}
    </div>
  )
}

function Panel(p: {
  items: ResultItem[]
  values: Map<number, string | null>
  selected: number | null
  onSelect: (idx: number) => void
}) {
  const n = p.items.length
  return (
    <section
      aria-labelledby="items-title"
      className="rounded-lg border border-rule bg-paper flex flex-col lg:max-h-[calc(100dvh-8rem)]"
    >
      <h2 id="items-title" className="title-3 text-ink px-3 py-3 border-b border-rule">
        {n === 1 ? '1 item' : `${n} items`}
      </h2>
      <div className="overflow-y-auto">
        <ItemList items={p.items} values={p.values} selected={p.selected} onSelect={p.onSelect} />
      </div>
    </section>
  )
}

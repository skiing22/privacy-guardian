// DESIGN 5.9: 2-3 options; selected = sign-soft fill + sign text. A radio group, so arrow
// keys move between options like any native radio set.
type Option<T extends string> = { value: T; label: string }

type Props<T extends string> = {
  label: string
  value: T
  options: Option<T>[]
  onChange: (v: T) => void
}

export function SegmentedControl<T extends string>({ label, value, options, onChange }: Props<T>) {
  function onKey(e: React.KeyboardEvent, i: number) {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return
    e.preventDefault()
    e.stopPropagation()
    const step = e.key === 'ArrowRight' ? 1 : -1
    const next = options[(i + step + options.length) % options.length]
    if (next) onChange(next.value)
  }
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="inline-flex rounded-md border border-rule bg-paper p-0.5"
    >
      {options.map((o, i) => {
        const on = o.value === value
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={on}
            tabIndex={on ? 0 : -1}
            onClick={() => onChange(o.value)}
            onKeyDown={(e) => onKey(e, i)}
            className={[
              'h-9 pointer-coarse:min-h-11 px-3 rounded-md button-sm transition-colors duration-200 ease-base',
              'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sign',
              on ? 'bg-sign-soft text-sign' : 'text-ink hover:bg-desk',
            ].join(' ')}
          >
            {o.label}
          </button>
        )
      })}
    </div>
  )
}

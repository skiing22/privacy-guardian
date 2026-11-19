import { WarningCircle } from '@phosphor-icons/react'
import { forwardRef, useId, type InputHTMLAttributes } from 'react'

// DESIGN 7: visible label above, help under, error under its own field with an icon.
type Props = InputHTMLAttributes<HTMLInputElement> & {
  label: string
  help?: string
  error?: string | null
}

export const Field = forwardRef<HTMLInputElement, Props>(function Field(
  { label, help, error, className = '', ...rest },
  ref,
) {
  const id = useId()
  const helpId = help ? `${id}-help` : undefined
  const errorId = error ? `${id}-error` : undefined
  const describedBy = [errorId, helpId].filter(Boolean).join(' ') || undefined
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className="title-4 text-ink">
        {label}
      </label>
      <input
        ref={ref}
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={[
          'h-10 pointer-coarse:min-h-11 rounded-md border bg-paper px-3 body-3 text-ink',
          'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sign',
          error ? 'border-risk-high' : 'border-rule-strong',
          className,
        ].join(' ')}
        {...rest}
      />
      {help && (
        <p id={helpId} className="caption-2 text-ink-muted">
          {help}
        </p>
      )}
      {error && (
        <p id={errorId} className="caption-2 text-risk-high flex items-center gap-2">
          <WarningCircle size={16} aria-hidden />
          {error}
        </p>
      )}
    </div>
  )
})

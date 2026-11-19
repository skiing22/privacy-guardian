import { WarningCircle } from '@phosphor-icons/react'
import { forwardRef, useId, type TextareaHTMLAttributes } from 'react'

// DESIGN 7, same rules as Field: label above, help and error under.
type Props = TextareaHTMLAttributes<HTMLTextAreaElement> & {
  label: string
  help?: string
  error?: string | null
}

export const TextArea = forwardRef<HTMLTextAreaElement, Props>(function TextArea(
  { label, help, error, className = '', ...rest },
  ref,
) {
  const id = useId()
  const helpId = help ? `${id}-help` : undefined
  const errorId = error ? `${id}-error` : undefined
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className="title-4 text-ink">
        {label}
      </label>
      <textarea
        ref={ref}
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={[errorId, helpId].filter(Boolean).join(' ') || undefined}
        className={[
          'rounded-md border bg-paper px-3 py-2 body-7 text-ink resize-y',
          'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sign',
          'disabled:opacity-40',
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

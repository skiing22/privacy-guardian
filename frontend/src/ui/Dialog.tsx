import { useEffect, useId, useRef, type ReactNode } from 'react'
import { Button } from './Button'

/**
 * DESIGN 5.9 / 11: only for actions with consequences. The title asks the question, the
 * main button repeats the action. Focus is trapped inside and returns to the trigger.
 */
type Props = {
  open: boolean
  title: string
  children?: ReactNode
  confirmLabel: string
  confirmBusyLabel?: string
  busy?: boolean
  danger?: boolean
  onConfirm: () => void
  onClose: () => void
}

const FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), textarea, select'

export function Dialog(p: Props) {
  const box = useRef<HTMLDivElement>(null)
  const titleId = useId()
  const descId = useId()

  useEffect(() => {
    if (!p.open) return
    const back = document.activeElement as HTMLElement | null
    const first = box.current?.querySelectorAll<HTMLElement>(FOCUSABLE)[0]
    first?.focus()
    return () => back?.focus()
  }, [p.open])

  if (!p.open) return null

  function onKey(e: React.KeyboardEvent) {
    if (e.key === 'Escape' && !p.busy) {
      e.stopPropagation()
      p.onClose()
      return
    }
    if (e.key !== 'Tab' || !box.current) return
    const items = Array.from(box.current.querySelectorAll<HTMLElement>(FOCUSABLE))
    const first = items[0]
    const last = items[items.length - 1]
    if (!first || !last) return
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault()
      first.focus()
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/30 px-4">
      <div
        ref={box}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={p.children ? descId : undefined}
        onKeyDown={onKey}
        className="w-full max-w-[440px] rounded-lg border border-rule bg-paper p-6 shadow-dialog flex flex-col gap-4 motion-safe:animate-[rise_500ms_var(--ease-base)]"
      >
        <h2 id={titleId} className="heading-6 text-ink text-balance">
          {p.title}
        </h2>
        {p.children && (
          <div id={descId} className="body-3 text-ink-muted">
            {p.children}
          </div>
        )}
        <div className="flex flex-col-reverse sm:flex-row sm:justify-end gap-2 pt-2">
          <Button variant="secondary" onClick={p.onClose} disabled={p.busy}>
            Cancel
          </Button>
          <Button
            variant={p.danger ? 'danger' : 'primary'}
            onClick={p.onConfirm}
            loading={p.busy}
            loadingLabel={p.confirmBusyLabel}
          >
            {p.confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  )
}

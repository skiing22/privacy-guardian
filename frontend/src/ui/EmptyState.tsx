import type { ReactNode } from 'react'

// DESIGN 5.9: centred, one sentence + one action, no illustration.
export function EmptyState({ text, action }: { text: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-4 py-16 px-4 text-center">
      <p className="body-3 text-ink-muted text-balance">{text}</p>
      {action}
    </div>
  )
}

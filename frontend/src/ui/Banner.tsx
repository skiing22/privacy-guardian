import { CheckCircle, Info, WarningCircle } from '@phosphor-icons/react'
import type { ReactNode } from 'react'
import { forwardRef } from 'react'

// DESIGN 5.9: icon + one sentence (+ optional action). Errors are announced at once.
type Tone = 'info' | 'error' | 'success'

const TONES: Record<Tone, string> = {
  info: 'bg-sign-soft text-ink border-sign',
  error: 'bg-risk-high-bg text-risk-high border-risk-high',
  success: 'bg-risk-low-bg text-risk-low border-risk-low',
}
const ICONS = { info: Info, error: WarningCircle, success: CheckCircle }

export const Banner = forwardRef<HTMLDivElement, { tone: Tone; children: ReactNode }>(
  function Banner({ tone, children }, ref) {
    const Icon = ICONS[tone]
    return (
      <div
        ref={ref}
        tabIndex={-1}
        role={tone === 'error' ? 'alert' : 'status'}
        className={`flex items-start gap-2 rounded-md border px-3 py-2 body-6 focus:outline-none ${TONES[tone]}`}
      >
        <Icon size={20} aria-hidden className="shrink-0" />
        <span>{children}</span>
      </div>
    )
  },
)

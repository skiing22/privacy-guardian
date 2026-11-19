import type { ButtonHTMLAttributes } from 'react'

// DESIGN 5.1: one button family. Loading swaps the label for the action in progress and
// disables the button. No spinners, no arrows.
type Variant = 'primary' | 'secondary' | 'text' | 'danger'

const BASE =
  'inline-flex items-center justify-center gap-2 rounded-md button-md transition-colors duration-200 ease-base ' +
  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sign ' +
  'active:translate-y-px disabled:opacity-40 disabled:pointer-events-none'

const VARIANTS: Record<Variant, string> = {
  primary: 'h-10 pointer-coarse:min-h-11 px-3 bg-sign text-white hover:bg-sign-hover',
  secondary:
    'h-10 pointer-coarse:min-h-11 px-3 bg-paper text-ink border border-rule-strong hover:bg-desk',
  text: 'px-1 text-sign underline decoration-transparent underline-offset-4 hover:decoration-sign',
  danger:
    'h-10 pointer-coarse:min-h-11 px-3 bg-paper text-risk-high border border-risk-high hover:bg-risk-high-bg',
}

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant
  loading?: boolean
  loadingLabel?: string
}

export function Button({
  variant = 'primary',
  loading = false,
  loadingLabel,
  disabled,
  children,
  className = '',
  type = 'button',
  ...rest
}: Props) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={`${BASE} ${VARIANTS[variant]} ${className}`}
      {...rest}
    >
      {loading && loadingLabel ? loadingLabel : children}
    </button>
  )
}

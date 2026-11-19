import type { ReactNode } from 'react'
import type { Family } from '../../ui/TypeLabel'

// DESIGN 5.2: a highlighter stroke in the family colour; text stays ink (contrast ≥ 12:1).
const FILL: Record<Family, string> = {
  identity: 'bg-hl-identity',
  contact: 'bg-hl-contact',
  id: 'bg-hl-id',
  other: 'bg-hl-other',
}

export function Mark({
  family,
  label,
  children,
}: {
  family: Family
  label: string
  children: ReactNode
}) {
  return (
    <mark
      aria-label={label}
      className={`${FILL[family]} text-ink rounded-sm px-0.5 box-decoration-clone`}
    >
      {children}
    </mark>
  )
}

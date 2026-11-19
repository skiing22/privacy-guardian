import { useEffect, useState } from 'react'

// DESIGN 5.9 / 8: rule-coloured blocks shaped like the content, only after 300 ms, no shimmer.
export function useDelayed(ms = 300): boolean {
  const [show, setShow] = useState(false)
  useEffect(() => {
    const t = setTimeout(() => setShow(true), ms)
    return () => clearTimeout(t)
  }, [ms])
  return show
}

export function Skeleton({ className = '' }: { className?: string }) {
  return <span aria-hidden className={`block rounded-sm bg-rule ${className}`} />
}

import { useEffect, useId, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Me } from '../../api/auth'
import { Button } from '../../ui/Button'
import { useLogout } from './session'

// DESIGN 6: initials button; opens email, role and Log out.
function initials(email: string): string {
  const name = email.split('@')[0] ?? ''
  const parts = name.split(/[._-]+/).filter(Boolean)
  const two = parts.length > 1 ? (parts[0]?.[0] ?? '') + (parts[1]?.[0] ?? '') : name.slice(0, 2)
  return two.toUpperCase() || '?'
}

export function UserMenu({ user }: { user: Me }) {
  const [open, setOpen] = useState(false)
  const id = useId()
  const box = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const logout = useLogout()
  const navigate = useNavigate()

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false)
        trigger.current?.focus()
      }
    }
    const onClick = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onClick)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onClick)
    }
  }, [open])

  return (
    <div ref={box} className="relative">
      <button
        ref={trigger}
        type="button"
        aria-expanded={open}
        aria-controls={id}
        aria-label={`Account menu for ${user.email}`}
        onClick={() => setOpen((o) => !o)}
        className="h-10 w-10 rounded-md bg-sign-soft text-sign title-4 hover:bg-desk focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sign"
      >
        {initials(user.email)}
      </button>
      {open && (
        <div
          id={id}
          className="absolute right-0 top-12 w-64 rounded-lg border border-rule bg-paper p-4 flex flex-col gap-3 shadow-dialog"
        >
          <div>
            <p className="body-6 text-ink break-all">{user.email}</p>
            <p className="caption-2 text-ink-muted">{user.role === 'admin' ? 'Admin' : 'User'}</p>
          </div>
          <Button
            variant="secondary"
            loading={logout.isPending}
            loadingLabel="Logging out"
            onClick={() =>
              logout.mutate(undefined, {
                onSettled: () => navigate('/login', { replace: true }),
              })
            }
          >
            Log out
          </Button>
        </div>
      )}
    </div>
  )
}

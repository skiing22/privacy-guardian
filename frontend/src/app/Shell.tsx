import { List, X } from '@phosphor-icons/react'
import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'

// DESIGN 6. Admin links appear once roles exist (P5/P17); hiding links is never protection.
const LINKS = [{ to: '/scans', label: 'Scans' }]

function linkClass({ isActive }: { isActive: boolean }): string {
  return [
    'title-3 relative px-3 py-2 rounded-md transition-colors duration-200 ease-base',
    isActive
      ? 'text-sign after:absolute after:inset-x-3 after:-bottom-0.5 after:h-0.5 after:bg-sign'
      : 'text-ink hover:bg-desk',
  ].join(' ')
}

export function Shell() {
  const [open, setOpen] = useState(false)
  return (
    <div className="min-h-dvh flex flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-50 focus:bg-paper focus:px-3 focus:py-2 focus:rounded-md"
      >
        Skip to content
      </a>
      <header className="sticky top-4 z-40 flex justify-center px-4">
        <nav
          aria-label="Main"
          className="flex items-center gap-2 rounded-lg border border-rule bg-paper/85 backdrop-blur px-3 py-2"
        >
          <span className="title-3 font-semibold px-2">Privacy Guardian</span>
          <ul className="hidden sm:flex items-center gap-1">
            {LINKS.map((l) => (
              <li key={l.to}>
                <NavLink to={l.to} className={linkClass}>
                  {l.label}
                </NavLink>
              </li>
            ))}
          </ul>
          <button
            type="button"
            className="sm:hidden p-2.5 rounded-md hover:bg-desk"
            aria-expanded={open}
            aria-controls="mobile-menu"
            aria-label={open ? 'Close menu' : 'Open menu'}
            onClick={() => setOpen((o) => !o)}
          >
            {open ? <X size={20} aria-hidden /> : <List size={20} aria-hidden />}
          </button>
        </nav>
      </header>
      {open && (
        <div
          id="mobile-menu"
          className="sm:hidden fixed inset-0 z-30 bg-paper/95 backdrop-blur-xl pt-24 px-4"
        >
          <ul className="flex flex-col gap-2">
            {LINKS.map((l) => (
              <li key={l.to}>
                <NavLink to={l.to} className={linkClass} onClick={() => setOpen(false)}>
                  {l.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      )}
      <main id="main" className="flex-1 w-full max-w-[1280px] mx-auto px-4 sm:px-6 pt-12 pb-16">
        <Outlet />
      </main>
      <footer className="w-full max-w-[1280px] mx-auto px-4 sm:px-6 py-6 border-t border-rule">
        <NavLink to="/privacy" className="caption-2 text-sign hover:underline">
          Privacy and terms
        </NavLink>
      </footer>
    </div>
  )
}

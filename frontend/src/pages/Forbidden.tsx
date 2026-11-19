import { Link } from 'react-router-dom'

// 403 state (PRD 9): plain words, one way back. The server refuses the data anyway.
export function Forbidden() {
  return (
    <section aria-labelledby="page-title">
      <h1 id="page-title" className="heading-5">
        Only admins can do this.
      </h1>
      <p className="body-3 text-ink-muted mt-2 max-w-[65ch]">
        Ask an admin if you need access to rules or the audit log.
      </p>
      <Link to="/scans" className="body-3 text-sign hover:underline mt-4 inline-block">
        Go to your scans
      </Link>
    </section>
  )
}

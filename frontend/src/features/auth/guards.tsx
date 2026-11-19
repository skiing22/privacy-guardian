import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { Banner } from '../../ui/Banner'
import { Button } from '../../ui/Button'
import { loginPath } from '../../app/safeNext'
import { Forbidden } from '../../pages/Forbidden'
import { useSession } from './session'

/**
 * Route guards. They decide what the browser SHOWS; they protect nothing. Every API route
 * checks the session and role again on the server (ARCHITECTURE 8.2).
 */
function Pending() {
  return <div aria-busy="true" className="min-h-40" />
}

export function RequireAuth() {
  const session = useSession()
  const loc = useLocation()
  if (session.isPending) return <Pending />
  if (session.isError) {
    // PRD 12: server down. Nothing is shown that needs a session.
    return (
      <div className="flex flex-col items-start gap-3">
        <Banner tone="error">Service unavailable. Try again shortly.</Banner>
        <Button variant="text" onClick={() => void session.refetch()}>
          Retry
        </Button>
      </div>
    )
  }
  if (!session.data.user) {
    const to = loginPath(loc.pathname + loc.search + loc.hash)
    return <Navigate to={to} replace state={{ ended: session.data.ended }} />
  }
  return <Outlet />
}

export function RequireAdmin() {
  const session = useSession()
  if (session.isPending) return <Pending />
  if (session.data?.user?.role !== 'admin') return <Forbidden />
  return <Outlet />
}

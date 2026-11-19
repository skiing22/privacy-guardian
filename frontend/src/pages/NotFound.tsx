import { Link } from 'react-router-dom'

// S8 (DESIGN 8): plain page with one way back.
export function NotFound() {
  return (
    <section aria-labelledby="page-title">
      <h1 id="page-title" className="heading-5">
        This page does not exist.
      </h1>
      <Link
        to="/scans"
        className="body-3 text-sign hover:underline mt-4 inline-block pointer-coarse:py-2.5"
      >
        Go to your scans
      </Link>
    </section>
  )
}

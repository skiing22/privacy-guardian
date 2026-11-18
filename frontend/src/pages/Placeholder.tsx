// Setup only: each route renders its title until its phase builds it
// (IMPLEMENTATION_PLAN.md P14 to P18). Removed when the last page is built.
type Props = { title: string; phase: string }

export function Placeholder({ title, phase }: Props) {
  return (
    <section aria-labelledby="page-title">
      <h1 id="page-title" className="heading-5">
        {title}
      </h1>
      <p className="body-3 text-ink-muted mt-2">This screen is built in phase {phase}.</p>
    </section>
  )
}

import type { Risk } from '../../api/scan'
import { RiskBadge } from '../../ui/Badge'
import { clueWords, matchSentence } from './words'

/** DESIGN 5.8: sentence first, then the badge; loud only for HIGH and DIRECT. */
const TONE: Record<Risk['level'], string> = {
  LOW: 'border-rule bg-paper',
  MEDIUM: 'border-risk-medium bg-risk-medium-bg',
  HIGH: 'border-risk-high bg-risk-high-bg',
  DIRECT: 'border-risk-direct-bg bg-risk-direct-bg text-white',
}

export function RiskBanner({ risk }: { risk: Risk }) {
  const loud = risk.level === 'DIRECT'
  return (
    <section
      aria-label="Risk"
      className={`rounded-lg border px-6 py-4 flex flex-col gap-2 ${TONE[risk.level]}`}
    >
      <p className="flex flex-wrap items-center gap-3">
        <span className={`title-3 ${loud ? 'text-white' : 'text-ink'}`}>
          {matchSentence(risk.est_matches, risk.clues)}
        </span>
        <RiskBadge level={risk.level} />
      </p>
      {risk.clues.length > 0 && (
        <p className={`body-6 ${loud ? 'text-white' : 'text-ink-muted'}`}>
          Visible clues: {clueWords(risk.clues)}.
        </p>
      )}
      {risk.level === 'HIGH' && (
        <p className="body-6 text-risk-high">
          Do not share yet. Protect more items in the list below.
        </p>
      )}
      {risk.level === 'DIRECT' && (
        <p className="body-6 text-white">Personal data is still visible because of a fixed rule.</p>
      )}
      {risk.unresolved_leaks > 0 && (
        <p className={`body-6 ${loud ? 'text-white' : 'text-risk-high'}`}>
          {risk.unresolved_leaks === 1
            ? '1 item could not be removed after 3 rounds.'
            : `${risk.unresolved_leaks} items could not be removed after 3 rounds.`}
        </p>
      )}
    </section>
  )
}

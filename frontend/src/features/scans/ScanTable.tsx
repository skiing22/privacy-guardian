import { Link } from 'react-router-dom'
import type { ScanListItem } from '../../api/scans'
import { OPEN_STATUSES } from '../../api/scans'
import { formatStarted } from '../../lib/format'
import { RiskBadge, StatusBadge } from '../../ui/Badge'
import { Button } from '../../ui/Button'

/**
 * S2 table (DESIGN 5.9, 10): a real table from 640 px; below that each scan is a stacked
 * block (label: value). The file name is the link that opens S4; the row tints on hover.
 */
type Props = { scans: ScanListItem[]; onDelete: (s: ScanListItem) => void; now?: Date }

const TH = 'title-4 text-ink-muted text-left font-medium px-3 py-2'
const TD = 'px-3 py-0 h-11 body-6 text-ink align-middle'

export function ScanTable({ scans, onDelete, now }: Props) {
  return (
    <>
      <table className="hidden sm:table w-full border-collapse tabular-nums">
        <thead>
          <tr className="border-b border-rule">
            <th scope="col" className={TH}>
              File
            </th>
            <th scope="col" className={TH}>
              Started
            </th>
            <th scope="col" className={TH}>
              Status
            </th>
            <th scope="col" className={TH}>
              Risk
            </th>
            <th scope="col" className={TH}>
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {scans.map((s) => (
            <tr
              key={s.id}
              className="border-b border-rule last:border-b-0 transition-colors duration-200 ease-base hover:bg-desk"
            >
              <td className={`${TD} max-w-[360px]`}>
                <Link
                  to={`/scans/${s.id}`}
                  className="block truncate text-ink hover:text-sign focus-visible:outline-2 focus-visible:outline-sign rounded-sm"
                >
                  {s.filename}
                </Link>
              </td>
              <td className={`${TD} whitespace-nowrap text-ink-muted`}>
                {formatStarted(s.created_at, now)}
              </td>
              <td className={TD}>
                <StatusBadge status={s.status} />
              </td>
              <td className={TD}>
                {s.risk_level ? (
                  <RiskBadge level={s.risk_level} />
                ) : (
                  <span aria-label="No risk yet">—</span>
                )}
              </td>
              <td className={`${TD} text-right`}>
                <DeleteButton scan={s} onDelete={onDelete} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <ul className="sm:hidden flex flex-col">
        {scans.map((s) => (
          <li key={s.id} className="border-b border-rule last:border-b-0 py-3 flex flex-col gap-2">
            <Link
              to={`/scans/${s.id}`}
              className="title-3 text-ink break-all hover:text-sign py-1 pointer-coarse:min-h-11 flex items-center focus-visible:outline-2 focus-visible:outline-sign rounded-sm"
            >
              {s.filename}
            </Link>
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 body-6">
              <dt className="text-ink-muted">Started</dt>
              <dd>{formatStarted(s.created_at, now)}</dd>
              <dt className="text-ink-muted">Status</dt>
              <dd>
                <StatusBadge status={s.status} />
              </dd>
              <dt className="text-ink-muted">Risk</dt>
              <dd>{s.risk_level ? <RiskBadge level={s.risk_level} /> : '—'}</dd>
            </dl>
            <div>
              <DeleteButton scan={s} onDelete={onDelete} />
            </div>
          </li>
        ))}
      </ul>
    </>
  )
}

function DeleteButton({ scan, onDelete }: { scan: ScanListItem; onDelete: Props['onDelete'] }) {
  const running = OPEN_STATUSES.has(scan.status)
  return (
    <Button
      variant="text-danger"
      className="pointer-coarse:min-h-11"
      disabled={running}
      title={running ? 'A running scan cannot be deleted' : undefined}
      aria-label={`Delete ${scan.filename}`}
      onClick={() => onDelete(scan)}
    >
      Delete
    </Button>
  )
}

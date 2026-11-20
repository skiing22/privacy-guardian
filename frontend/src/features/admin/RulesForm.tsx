import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { adminKeys, getRules, putRules, type Action, type RuleOut } from '../../api/admin'
import { ApiError } from '../../api/client'
import { Banner } from '../../ui/Banner'
import { Button } from '../../ui/Button'
import { Skeleton, useDelayed } from '../../ui/Skeleton'
import { useToast } from '../../ui/Toast'
import { TypeLabel, type Family } from '../../ui/TypeLabel'
import { ACTION_WORDS } from './words'

/**
 * DESIGN 7 "Fixed rules": one select per type, grouped by family, Automatic by default.
 * Only actions the server allows for the type are offered (it checks again on save).
 */
const FAMILIES: { family: Family; title: string }[] = [
  { family: 'identity', title: 'Who someone is' },
  { family: 'contact', title: 'How to reach or find them' },
  { family: 'id', title: 'Government and financial IDs' },
  { family: 'other', title: 'Dates and the rest' },
]
const AUTO = ''

export function RulesForm() {
  const qc = useQueryClient()
  const toast = useToast()
  const rules = useQuery({ queryKey: adminKeys.rules, queryFn: getRules })
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const showSkeleton = useDelayed()

  const current = useMemo(() => {
    const out: Record<string, string> = {}
    for (const r of rules.data?.rules ?? []) out[r.pii_type] = draft[r.pii_type] ?? r.action ?? AUTO
    return out
  }, [rules.data, draft])
  const dirty = (rules.data?.rules ?? []).some((r) => (r.action ?? AUTO) !== current[r.pii_type])
  const fixedCount = Object.values(current).filter((v) => v !== AUTO).length

  const save = useMutation({
    mutationFn: () =>
      putRules(
        (rules.data?.rules ?? []).map((r) => ({
          pii_type: r.pii_type,
          action: (current[r.pii_type] || null) as Action | null,
        })),
      ),
    onSuccess: (data) => {
      qc.setQueryData(adminKeys.rules, data)
      setDraft({})
      setError(null)
      toast('Rules saved')
    },
    onError: (e) =>
      setError(e instanceof ApiError ? e.message : 'Could not save the rules. Try again.'),
  })

  if (rules.isError)
    return (
      <div className="flex flex-col items-start gap-3">
        <Banner tone="error">Could not load the rules.</Banner>
        <Button variant="text" onClick={() => void rules.refetch()}>
          Retry
        </Button>
      </div>
    )
  if (!rules.data)
    return (
      <div aria-busy="true" aria-label="Loading rules" className="flex flex-col gap-3">
        {showSkeleton &&
          [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-10 w-full max-w-[480px]" />)}
      </div>
    )

  const byFamily = (f: Family): RuleOut[] => rules.data.rules.filter((r) => r.family === f)

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        save.mutate()
      }}
      className="flex flex-col gap-6"
    >
      <p className="body-6 text-ink-muted">
        {fixedCount === 0
          ? 'No fixed rules. All types use automatic choice.'
          : `${fixedCount} of ${rules.data.rules.length} types have a fixed action. The rest use automatic choice.`}
      </p>
      {error && <Banner tone="error">{error}</Banner>}
      {FAMILIES.map(({ family, title }) => (
        <fieldset key={family} className="flex flex-col gap-2">
          <legend className="title-4 text-ink-muted mb-2">{title}</legend>
          {byFamily(family).map((r) => {
            const id = `rule-${r.pii_type}`
            return (
              <div
                key={r.pii_type}
                className="grid grid-cols-1 sm:grid-cols-[180px_1fr] items-center gap-2"
              >
                <label htmlFor={id}>
                  <TypeLabel piiType={r.pii_type} family={r.family} />
                </label>
                <select
                  id={id}
                  value={current[r.pii_type]}
                  onChange={(e) => setDraft((d) => ({ ...d, [r.pii_type]: e.target.value }))}
                  className="h-10 pointer-coarse:min-h-11 max-w-[320px] rounded-md border border-rule-strong bg-paper px-3 body-6 text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sign"
                >
                  <option value={AUTO}>Automatic</option>
                  {r.allowed_actions.map((a) => (
                    <option key={a} value={a}>
                      {ACTION_WORDS[a] ?? a}
                    </option>
                  ))}
                </select>
              </div>
            )
          })}
        </fieldset>
      ))}
      <div>
        <Button
          type="submit"
          disabled={!dirty}
          loading={save.isPending}
          loadingLabel="Saving rules"
        >
          Save rules
        </Button>
      </div>
    </form>
  )
}

/** Admin endpoints (API.md 4.13 to 4.19). Every one is checked for role admin on the server. */
import type { components } from './schema'
import { api } from './client'

export type RulesOut = components['schemas']['RulesOut']
export type RuleOut = components['schemas']['RuleOut']
export type Action = NonNullable<RuleOut['action']>
export type RevealOut = components['schemas']['RevealOut']
export type AuditPage = components['schemas']['AuditPage']
export type AuditItem = components['schemas']['AuditItem']
export type VerifyOut = components['schemas']['VerifyOut']
export type AnchorOut = components['schemas']['AnchorOut']

export const adminKeys = {
  rules: ['admin', 'rules'] as const,
  audit: ['admin', 'audit'] as const,
}

export const getRules = () => api<RulesOut>('/api/v1/admin/rules')

export const putRules = (rules: { pii_type: string; action: Action | null }[]) =>
  api<RulesOut>('/api/v1/admin/rules', { method: 'PUT', body: JSON.stringify({ rules }) })

/** Never cached: the value lives only in the reveal form's state (see RevealForm). */
export const reveal = (token: string, reason: string) =>
  api<RevealOut>('/api/v1/admin/reveal', {
    method: 'POST',
    body: JSON.stringify({ token, reason }),
  })

export const resetBeliefs = () =>
  api<undefined>('/api/v1/admin/beliefs/reset', {
    method: 'POST',
    body: JSON.stringify({ confirm: true }),
  })

export const auditPage = (beforeSeq: number | null, limit = 50) => {
  const q = new URLSearchParams({ limit: String(limit) })
  if (beforeSeq !== null) q.set('before_seq', String(beforeSeq))
  return api<AuditPage>(`/api/v1/admin/audit?${q.toString()}`)
}

export const verifyLog = () => api<VerifyOut>('/api/v1/admin/audit/verify', { method: 'POST' })
export const saveAnchor = () => api<AnchorOut>('/api/v1/admin/audit/anchor', { method: 'POST' })

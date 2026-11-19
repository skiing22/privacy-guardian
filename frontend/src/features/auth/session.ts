import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchSession, login, logout, SESSION_KEY, type Session } from '../../api/auth'

export function useSession() {
  return useQuery({ queryKey: SESSION_KEY, queryFn: fetchSession, staleTime: 60_000 })
}

export function useLogin() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { email: string; password: string }) => login(v.email, v.password),
    onSuccess: async () => {
      qc.removeQueries({ predicate: (q) => q.queryKey[0] !== SESSION_KEY[0] })
      qc.setQueryData<Session>(SESSION_KEY, await fetchSession())
    },
  })
}

export function useLogout() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: logout,
    // Even if the request fails, forget everything locally: the user asked to leave.
    onSettled: () => {
      qc.clear()
      qc.setQueryData<Session>(SESSION_KEY, { user: null, ended: false })
    },
  })
}

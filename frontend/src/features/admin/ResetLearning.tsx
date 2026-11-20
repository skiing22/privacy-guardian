import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { resetBeliefs } from '../../api/admin'
import { Banner } from '../../ui/Banner'
import { Button } from '../../ui/Button'
import { Dialog } from '../../ui/Dialog'
import { useToast } from '../../ui/Toast'

/** DESIGN 5.1 danger action, asked in a dialog first (DESIGN 5.9). */
export function ResetLearning() {
  const [open, setOpen] = useState(false)
  const toast = useToast()
  const reset = useMutation({
    mutationFn: resetBeliefs,
    onSuccess: () => {
      setOpen(false)
      toast('Learning reset')
    },
    onError: () => setOpen(false),
  })
  return (
    <div className="flex flex-col items-start gap-3">
      <p className="body-6 text-ink-muted max-w-[65ch]">
        Review answers teach the tool which types it finds reliably. Resetting forgets all of that
        and starts again from the defaults.
      </p>
      {reset.isError && <Banner tone="error">Could not reset learning. Try again.</Banner>}
      <Button variant="danger" onClick={() => setOpen(true)}>
        Reset learning
      </Button>
      <Dialog
        open={open}
        title="Reset what the tool has learned?"
        confirmLabel="Reset learning"
        confirmBusyLabel="Resetting learning"
        busy={reset.isPending}
        danger
        onConfirm={() => reset.mutate()}
        onClose={() => setOpen(false)}
      >
        Every type goes back to its default. This is saved in the audit log.
      </Dialog>
    </div>
  )
}

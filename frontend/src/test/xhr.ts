import { vi } from 'vitest'

/** Stand-in XMLHttpRequest: records the request, reports progress, answers as told. */
export type XhrReply = { status: number; body: unknown }

export function fakeXhr(reply: XhrReply | ((form: FormData) => XhrReply)) {
  const sent: FormData[] = []
  class FakeXHR {
    upload: {
      onprogress: ((e: { lengthComputable: boolean; loaded: number; total: number }) => void) | null
    } = {
      onprogress: null,
    }
    status = 0
    responseText = ''
    responseType = ''
    withCredentials = false
    onload: (() => void) | null = null
    onerror: (() => void) | null = null
    method = ''
    url = ''
    open(method: string, url: string) {
      this.method = method
      this.url = url
    }
    send(form: FormData) {
      sent.push(form)
      const r = typeof reply === 'function' ? reply(form) : reply
      queueMicrotask(() => {
        this.upload.onprogress?.({ lengthComputable: true, loaded: 50, total: 100 })
        this.upload.onprogress?.({ lengthComputable: true, loaded: 100, total: 100 })
        this.status = r.status
        this.responseText = JSON.stringify(r.body)
        this.onload?.()
      })
    }
  }
  vi.stubGlobal('XMLHttpRequest', FakeXHR)
  return { sent }
}

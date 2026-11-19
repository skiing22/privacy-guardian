import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

// Testing Library only cleans up by itself when Vitest globals are on; they are off here.
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

import { render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { routes } from './routes'

function at(path: string) {
  render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [path] })} />)
}

describe('routes', () => {
  it('redirects / to scans and marks the current nav link', async () => {
    at('/')
    expect(await screen.findByRole('heading', { name: 'Scans' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Scans' }).getAttribute('aria-current')).toBe('page')
  })

  it('shows the 404 page for unknown paths', () => {
    at('/nope')
    expect(screen.getByRole('heading', { name: 'This page does not exist.' })).toBeTruthy()
  })

  it('puts the skip link first', () => {
    at('/scans')
    expect(screen.getAllByRole('link')[0]?.textContent).toBe('Skip to content')
  })
})

import { QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import { queryClient } from './app/queryClient'
import { routes } from './app/routes'
import './styles/index.css'
import { ToastProvider } from './ui/Toast'

const root = document.getElementById('root')
if (!root) throw new Error('root element missing')

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <RouterProvider router={createBrowserRouter(routes)} />
      </ToastProvider>
    </QueryClientProvider>
  </StrictMode>,
)

import { Navigate, type RouteObject } from 'react-router-dom'
import { NotFound } from '../pages/NotFound'
import { Placeholder } from '../pages/Placeholder'
import { Shell } from './Shell'

// ARCHITECTURE 4: every URL is real and shareable. `/` becomes the landing page S0 in M7.
export const routes: RouteObject[] = [
  { path: '/login', element: <Placeholder title="Log in" phase="P14" /> },
  {
    element: <Shell />,
    children: [
      { index: true, element: <Navigate to="/scans" replace /> },
      { path: 'scans', element: <Placeholder title="Scans" phase="P14" /> },
      { path: 'scans/new', element: <Placeholder title="New scan" phase="P14" /> },
      { path: 'scans/:id', element: <Placeholder title="Scan" phase="P15" /> },
      { path: 'admin/rules', element: <Placeholder title="Rules and vault" phase="P17" /> },
      { path: 'admin/audit', element: <Placeholder title="Audit log" phase="P17" /> },
      { path: 'privacy', element: <Placeholder title="Privacy and terms" phase="P18" /> },
      { path: '*', element: <NotFound /> },
    ],
  },
]

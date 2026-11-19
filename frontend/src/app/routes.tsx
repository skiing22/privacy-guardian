import { Navigate, type RouteObject } from 'react-router-dom'
import { RequireAdmin, RequireAuth } from '../features/auth/guards'
import { Login } from '../pages/Login'
import { NotFound } from '../pages/NotFound'
import { Placeholder } from '../pages/Placeholder'
import { Shell } from './Shell'

// ARCHITECTURE 4: every URL is real and shareable. `/` becomes the landing page S0 in M7.
// Public: login, privacy, 404. Everything else needs a session; /admin needs role admin.
export const routes: RouteObject[] = [
  { path: '/login', element: <Login /> },
  {
    element: <Shell />,
    children: [
      { path: 'privacy', element: <Placeholder title="Privacy and terms" phase="P18" /> },
      {
        element: <RequireAuth />,
        children: [
          { index: true, element: <Navigate to="/scans" replace /> },
          { path: 'scans', element: <Placeholder title="Scans" phase="P14" /> },
          { path: 'scans/new', element: <Placeholder title="New scan" phase="P14" /> },
          { path: 'scans/:id', element: <Placeholder title="Scan" phase="P15" /> },
          {
            path: 'admin',
            element: <RequireAdmin />,
            children: [
              { path: 'rules', element: <Placeholder title="Rules and vault" phase="P17" /> },
              { path: 'audit', element: <Placeholder title="Audit log" phase="P17" /> },
            ],
          },
        ],
      },
      { path: '*', element: <NotFound /> },
    ],
  },
]

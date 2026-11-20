import { Navigate, type RouteObject } from 'react-router-dom'
import { RequireAdmin, RequireAuth } from '../features/auth/guards'
import { AdminAudit } from '../pages/AdminAudit'
import { AdminRules } from '../pages/AdminRules'
import { Login } from '../pages/Login'
import { NewScan } from '../pages/NewScan'
import { NotFound } from '../pages/NotFound'
import { Placeholder } from '../pages/Placeholder'
import { Scan } from '../pages/Scan'
import { Scans } from '../pages/Scans'
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
          { path: 'scans', element: <Scans /> },
          { path: 'scans/new', element: <NewScan /> },
          { path: 'scans/:id', element: <Scan /> },
          {
            path: 'admin',
            element: <RequireAdmin />,
            children: [
              { path: 'rules', element: <AdminRules /> },
              { path: 'audit', element: <AdminAudit /> },
            ],
          },
        ],
      },
      { path: '*', element: <NotFound /> },
    ],
  },
]

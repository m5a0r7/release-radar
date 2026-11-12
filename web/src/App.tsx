import { BrowserRouter, Navigate, Route, Routes } from 'react-router'

import { AppShell } from './components/AppShell'
import { ConnectPage } from './pages/ConnectPage'
import { DashboardPage, OverviewRedirect, ProjectIndex } from './pages/DashboardPage'
import { LoginPage } from './pages/LoginPage'
import { ProjectsPage } from './pages/ProjectsPage'
import { SettingsPage } from './pages/SettingsPage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<AppShell />}>
          <Route index element={<OverviewRedirect />} />
          <Route path="projects" element={<ProjectsPage />} />
          <Route path="projects/new" element={<ConnectPage />} />
          <Route path="p/:slug" element={<ProjectIndex />} />
          <Route path="p/:slug/:release" element={<DashboardPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

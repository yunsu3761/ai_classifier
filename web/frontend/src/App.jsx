import React from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Layout from './components/Layout.jsx'
import DataSourcePage from './pages/DataSourcePage.jsx'
import SettingsPage from './pages/SettingsPage.jsx'
import ExecutionPage from './pages/ExecutionPage.jsx'
import ResultsPage from './pages/ResultsPage.jsx'

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<DataSourcePage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/execution" element={<ExecutionPage />} />
          <Route path="/results" element={<ResultsPage />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  )
}

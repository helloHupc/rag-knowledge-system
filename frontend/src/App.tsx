import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Layout } from './components/Layout'
import { DocumentsPage } from './pages/DocumentsPage'
import { ChunkingPage } from './pages/ChunkingPage'
import { RetrievalPage } from './pages/RetrievalPage'
import { EvaluationPage } from './pages/EvaluationPage'
import { SettingsPage } from './pages/SettingsPage'
import { ApiEndpointsPage } from './pages/ApiEndpointsPage'
import './App.css'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<DocumentsPage />} />
          <Route path="/chunking" element={<ChunkingPage />} />
          <Route path="/retrieval" element={<RetrievalPage />} />
          <Route path="/evaluation" element={<EvaluationPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/api-endpoints" element={<ApiEndpointsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

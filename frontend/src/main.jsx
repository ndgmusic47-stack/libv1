import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.jsx'
import { ProjectProvider } from './context/ProjectContext'
import './styles/index.css'

// Load or generate sessionId at the root so ProjectProvider can initialize
let sessionId = localStorage.getItem('session_id')
if (!sessionId) {
  sessionId = crypto.randomUUID()
  localStorage.setItem('session_id', sessionId)
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <ProjectProvider sessionId={sessionId}>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </ProjectProvider>
)

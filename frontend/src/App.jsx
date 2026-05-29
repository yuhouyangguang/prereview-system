import React from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './contexts/AuthContext'
import Layout from './components/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import ProjectList from './pages/ProjectList'
import ProjectCreate from './pages/ProjectCreate'
import ProjectDetail from './pages/ProjectDetail'
import ProjectEdit from './pages/ProjectEdit'
import MaterialVerification from './pages/MaterialVerification'
import ApprovalQueue from './pages/ApprovalQueue'
import LeaderQueue from './pages/LeaderQueue'
import BranchParams from './pages/BranchParams'
import LeaderStats from './pages/LeaderStats'
import KnowledgeBase from './pages/KnowledgeBase'

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh' }}><div className="spinner" style={{ width: 48, height: 48, borderWidth: 4 }} /></div>
  if (!user) return <Navigate to="/login" replace />
  return <Layout>{children}</Layout>
}

function AppRoutes() {
  const { user } = useAuth()
  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/dashboard" replace /> : <Login />} />
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
      <Route path="/projects" element={<ProtectedRoute><ProjectList /></ProtectedRoute>} />
      <Route path="/all-projects" element={<ProtectedRoute><ProjectList showAll /></ProtectedRoute>} />
      <Route path="/projects/create" element={<ProtectedRoute><ProjectCreate /></ProtectedRoute>} />
      <Route path="/projects/:id" element={<ProtectedRoute><ProjectDetail /></ProtectedRoute>} />
      <Route path="/projects/:id/edit" element={<ProtectedRoute><ProjectEdit /></ProtectedRoute>} />
      <Route path="/projects/:id/materials" element={<ProtectedRoute><MaterialVerification /></ProtectedRoute>} />
      <Route path="/approval-queue" element={<ProtectedRoute><ApprovalQueue /></ProtectedRoute>} />
      <Route path="/leader-queue" element={<ProtectedRoute><LeaderQueue /></ProtectedRoute>} />
      <Route path="/branch-params" element={<ProtectedRoute><BranchParams /></ProtectedRoute>} />
      <Route path="/leader-stats" element={<ProtectedRoute><LeaderStats /></ProtectedRoute>} />
      <Route path="/knowledge-base" element={<ProtectedRoute><KnowledgeBase /></ProtectedRoute>} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  )
}

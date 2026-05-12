import type { ReactNode } from "react";
import { Navigate, NavLink, Route, Routes, useNavigate } from "react-router-dom";

import Approvals from "./pages/Approvals";
import Login from "./pages/Login";
import Providers from "./pages/Providers";
import RunDetail from "./pages/RunDetail";
import Runs from "./pages/Runs";
import Workflows from "./pages/Workflows";

function ProtectedRoute({ children }: { children: ReactNode }) {
  if (!localStorage.getItem("token")) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

function Layout({ children }: { children: ReactNode }) {
  const navigate = useNavigate();

  function logout() {
    localStorage.removeItem("token");
    navigate("/login");
  }

  return (
    <div className="min-h-screen bg-slate-100 text-slate-950">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div>
            <p className="text-sm uppercase tracking-wide text-slate-500">Internal Dashboard</p>
            <h1 className="text-xl font-semibold">Workflow Platform</h1>
          </div>
          <nav className="flex items-center gap-3 text-sm">
            <NavLink className={({ isActive }) => (isActive ? "nav-link-active" : "nav-link")} to="/runs">
              Runs
            </NavLink>
            <NavLink className={({ isActive }) => (isActive ? "nav-link-active" : "nav-link")} to="/workflows">
              Workflows
            </NavLink>
            <NavLink className={({ isActive }) => (isActive ? "nav-link-active" : "nav-link")} to="/approvals">
              Approvals
            </NavLink>
            <NavLink className={({ isActive }) => (isActive ? "nav-link-active" : "nav-link")} to="/providers">
              Providers
            </NavLink>
            <button className="btn-secondary" onClick={logout}>
              Logout
            </button>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-6">{children}</main>
    </div>
  );
}

function ProtectedPage({ children }: { children: ReactNode }) {
  return (
    <ProtectedRoute>
      <Layout>{children}</Layout>
    </ProtectedRoute>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/runs" element={<ProtectedPage><Runs /></ProtectedPage>} />
      <Route path="/runs/:id" element={<ProtectedPage><RunDetail /></ProtectedPage>} />
      <Route path="/workflows" element={<ProtectedPage><Workflows /></ProtectedPage>} />
      <Route path="/approvals" element={<ProtectedPage><Approvals /></ProtectedPage>} />
      <Route path="/providers" element={<ProtectedPage><Providers /></ProtectedPage>} />
      <Route path="/" element={<Navigate to="/runs" replace />} />
    </Routes>
  );
}

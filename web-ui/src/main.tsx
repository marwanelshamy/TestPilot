import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import { Layout } from "./components/ui";
import { ExecutionPage } from "./pages/ExecutionPage";
import { LoginPage } from "./pages/LoginPage";
import { ProjectPage } from "./pages/ProjectPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { TestPage } from "./pages/TestPage";
import "./styles.css";

function Protected({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  return user ? <Layout>{children}</Layout> : <Navigate to="/login" replace />;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/projects" element={<Protected><ProjectsPage /></Protected>} />
      <Route path="/projects/:id" element={<Protected><ProjectPage /></Protected>} />
      <Route path="/tests/:id" element={<Protected><TestPage /></Protected>} />
      <Route path="/executions/:id" element={<Protected><ExecutionPage /></Protected>} />
      <Route path="*" element={<Navigate to="/projects" replace />} />
    </Routes>
  );
}

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(
    <StrictMode>
      <AuthProvider>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </AuthProvider>
    </StrictMode>,
  );
}

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import Layout from "./components/Layout";
import { ProtectedRoute } from "./components/ProtectedRoute";
import AdminPage from "./pages/AdminPage";
import ChatPage from "./pages/ChatPage";
import HomePage from "./pages/HomePage";
import IvrSimulatorPage from "./pages/IvrSimulatorPage";
import LiveVoicePage from "./pages/LiveVoicePage";
import LoginPage from "./pages/LoginPage";
import OfficerPage from "./pages/OfficerPage";
import ProfilePage from "./pages/ProfilePage";
import RegisterPage from "./pages/RegisterPage";
import "./styles.css";

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<HomePage />} />
        <Route path="dashboard" element={<ProtectedRoute roles={["farmer"]}><HomePage /></ProtectedRoute>} />
        <Route path="assistant" element={<ProtectedRoute roles={["farmer"]}><ChatPage /></ProtectedRoute>} />
        <Route path="voice-live" element={<ProtectedRoute roles={["farmer"]}><LiveVoicePage /></ProtectedRoute>} />
        <Route path="profile" element={<ProtectedRoute roles={["farmer"]}><ProfilePage /></ProtectedRoute>} />
        <Route path="chat" element={<Navigate to="/assistant" replace />} />
        <Route path="disease" element={<Navigate to="/assistant" replace />} />
        <Route path="schemes" element={<Navigate to="/assistant" replace />} />
        <Route path="grievances" element={<Navigate to="/assistant" replace />} />
        <Route path="voice" element={<Navigate to="/voice-live" replace />} />
        <Route
          path="officer"
          element={
            <ProtectedRoute roles={["officer", "admin"]}>
              <OfficerPage />
            </ProtectedRoute>
          }
        />
        <Route path="officer/dashboard" element={<Navigate to="/officer" replace />} />
        <Route path="officer/grievances" element={<Navigate to="/officer" replace />} />
        <Route path="officer/diseases" element={<Navigate to="/officer" replace />} />
        <Route path="officer/analytics" element={<Navigate to="/officer" replace />} />
        <Route
          path="admin"
          element={
            <ProtectedRoute roles={["admin"]}>
              <AdminPage />
            </ProtectedRoute>
          }
        />
        <Route path="admin/dashboard" element={<Navigate to="/admin" replace />} />
        <Route
          path="admin/ivr-simulator"
          element={
            <ProtectedRoute roles={["admin"]}>
              <IvrSimulatorPage />
            </ProtectedRoute>
          }
        />
        <Route path="admin/users" element={<Navigate to="/admin" replace />} />
        <Route path="admin/schemes" element={<Navigate to="/admin" replace />} />
        <Route path="admin/analytics" element={<Navigate to="/admin" replace />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
);

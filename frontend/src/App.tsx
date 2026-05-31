import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { ConfigProvider, App as AntApp } from "antd";
import { AuthProvider } from "./auth/AuthContext";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import ErrorBoundary from "./components/ErrorBoundary";
import AppLayout from "./components/Layout";
import Login from "./pages/Login";
import Register from "./pages/Register";
import UploadPage from "./pages/Upload";
import QueryPage from "./pages/Query";
import ManagePage from "./pages/Manage";
import NotificationsPage from "./pages/Notifications";

export default function App() {
  return (
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: "#2E7D32", // Australian green
          borderRadius: 6,
        },
      }}
    >
      <AntApp>
        <AuthProvider>
          <ErrorBoundary>
          <BrowserRouter>
            <Routes>
              {/* Public routes */}
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />

              {/* Protected routes */}
              <Route
                path="/upload"
                element={
                  <ProtectedRoute>
                    <AppLayout><UploadPage /></AppLayout>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/query"
                element={
                  <ProtectedRoute>
                    <AppLayout><QueryPage /></AppLayout>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/manage"
                element={
                  <ProtectedRoute>
                    <AppLayout><ManagePage /></AppLayout>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/notifications"
                element={
                  <ProtectedRoute>
                    <AppLayout><NotificationsPage /></AppLayout>
                  </ProtectedRoute>
                }
              />

              {/* Default redirect */}
              <Route path="*" element={<Navigate to="/upload" replace />} />
            </Routes>
          </BrowserRouter>
          </ErrorBoundary>
        </AuthProvider>
      </AntApp>
    </ConfigProvider>
  );
}

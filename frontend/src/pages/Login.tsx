import { useState } from "react";
import { Form, Input, Button, Card, Typography, Alert } from "antd";
import { MailOutlined, LockOutlined } from "@ant-design/icons";
import { useNavigate, Link, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

const { Title } = Typography;

export default function Login() {
  const { signIn, error, clearError } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [loading, setLoading] = useState(false);

  const from = (location.state as any)?.from?.pathname || "/upload";

  async function onSubmit(values: { email: string; password: string }) {
    setLoading(true);
    clearError();
    try {
      await signIn(values.email, values.password);
      navigate(from, { replace: true });
    } catch {
      // error is set in context
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      style={{
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        minHeight: "100vh",
        background: "#f0f2f5",
      }}
    >
      <Card style={{ width: 400 }}>
        <Title level={3} style={{ textAlign: "center" }}>
          AussieEcoLens 🦘
        </Title>
        {error && <Alert type="error" message={error} closable style={{ marginBottom: 12 }} />}
        <Form onFinish={onSubmit} layout="vertical">
          <Form.Item name="email" rules={[{ required: true, message: "Enter your email" }]}>
            <Input prefix={<MailOutlined />} placeholder="Email" size="large" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: "Enter your password" }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="Password" size="large" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block size="large">
              Sign In
            </Button>
          </Form.Item>
        </Form>
        <div style={{ textAlign: "center" }}>
          Don't have an account? <Link to="/register">Sign up</Link>
        </div>
      </Card>
    </div>
  );
}

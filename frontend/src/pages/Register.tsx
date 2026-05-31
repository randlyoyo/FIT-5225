import { useState } from "react";
import { Form, Input, Button, Card, Typography, message, Alert } from "antd";
import { MailOutlined, LockOutlined, UserOutlined } from "@ant-design/icons";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

const { Title, Text: AntText } = Typography;

export default function Register() {
  const { signUp, confirmSignUp, error, clearError } = useAuth();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [email, setEmail] = useState("");

  async function onRegister(values: { email: string; password: string; firstName: string; lastName: string }) {
    setLoading(true);
    clearError();
    try {
      await signUp(values.email, values.password, values.firstName, values.lastName);
      setEmail(values.email);
      setConfirming(true);
      message.success("Verification code sent to your email. Please check your inbox.");
    } catch {
      // error is set in context
    } finally {
      setLoading(false);
    }
  }

  async function onConfirm(values: { code: string }) {
    setLoading(true);
    clearError();
    try {
      await confirmSignUp(email, values.code);
      message.success("Email verified! You can now sign in.");
      navigate("/login");
    } catch {
      // error is set in context
    } finally {
      setLoading(false);
    }
  }

  if (confirming) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "100vh", background: "#f0f2f5" }}>
        <Card style={{ width: 420 }}>
          <Title level={3} style={{ textAlign: "center" }}>Verify Your Email</Title>
          <AntText type="secondary">A verification code was sent to <strong>{email}</strong>. Please enter it below.</AntText>
          {error && <Alert type="error" message={error} closable style={{ marginTop: 12 }} />}
          <Form onFinish={onConfirm} layout="vertical" style={{ marginTop: 16 }}>
            <Form.Item name="code" rules={[{ required: true, message: "Enter verification code" }]}>
              <Input placeholder="Verification code" size="large" />
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit" loading={loading} block size="large">
                Verify Email
              </Button>
            </Form.Item>
          </Form>
        </Card>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "100vh", background: "#f0f2f5" }}>
      <Card style={{ width: 420 }}>
        <Title level={3} style={{ textAlign: "center" }}>Join AussieEcoLens 🦘</Title>
        {error && <Alert type="error" message={error} closable style={{ marginBottom: 12 }} />}
        <Form onFinish={onRegister} layout="vertical">
          <Form.Item name="firstName" rules={[{ required: true, message: "Enter your first name" }]}>
            <Input prefix={<UserOutlined />} placeholder="First Name" size="large" />
          </Form.Item>
          <Form.Item name="lastName" rules={[{ required: true, message: "Enter your last name" }]}>
            <Input prefix={<UserOutlined />} placeholder="Last Name" size="large" />
          </Form.Item>
          <Form.Item name="email" rules={[{ required: true, type: "email", message: "Enter a valid email" }]}>
            <Input prefix={<MailOutlined />} placeholder="Email" size="large" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, min: 8, message: "Password min 8 characters" }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="Password" size="large" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block size="large">
              Create Account
            </Button>
          </Form.Item>
        </Form>
        <div style={{ textAlign: "center" }}>
          Already have an account? <Link to="/login">Sign in</Link>
        </div>
      </Card>
    </div>
  );
}

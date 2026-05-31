import React from "react";
import { Layout as AntLayout, Menu, Button, Typography, Avatar } from "antd";
import {
  UploadOutlined,
  SearchOutlined,
  EditOutlined,
  BellOutlined,
  LogoutOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

const { Header, Sider, Content } = AntLayout;
const { Text } = Typography;

const menuItems = [
  { key: "/upload", icon: <UploadOutlined />, label: "Upload" },
  { key: "/query", icon: <SearchOutlined />, label: "Query" },
  { key: "/manage", icon: <EditOutlined />, label: "Manage" },
  { key: "/notifications", icon: <BellOutlined />, label: "Notifications" },
];

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, signOut } = useAuth();

  const handleSignOut = async () => {
    await signOut();
    navigate("/login");
  };

  return (
    <AntLayout style={{ minHeight: "100vh" }}>
      <Sider breakpoint="lg" collapsedWidth="0">
        <div style={{ padding: "16px", textAlign: "center" }}>
          <Text strong style={{ color: "#fff", fontSize: 16 }}>
            🦘 AussieEcoLens
          </Text>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <AntLayout>
        <Header
          style={{
            background: "#fff",
            padding: "0 24px",
            display: "flex",
            justifyContent: "flex-end",
            alignItems: "center",
            gap: 12,
          }}
        >
          <Avatar icon={<UserOutlined />} />
          <Text>{user?.email ?? "User"}</Text>
          <Button icon={<LogoutOutlined />} onClick={handleSignOut}>
            Sign Out
          </Button>
        </Header>
        <Content style={{ margin: 24, padding: 24, background: "#fff", borderRadius: 8 }}>
          {children}
        </Content>
      </AntLayout>
    </AntLayout>
  );
}

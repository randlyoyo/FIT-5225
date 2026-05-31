import { useState, useEffect } from "react";
import {
  Card, Typography, Button, Input, Space, Table, Tag, message,
  Popconfirm, Empty, Spin,
} from "antd";
import { PlusOutlined, DeleteOutlined, ReloadOutlined } from "@ant-design/icons";
import { createSubscription, listSubscriptions, deleteSubscription } from "../api/client";
import type { SubscriptionRecord } from "../types";

const { Title, Text: AntText } = Typography;

export default function NotificationsPage() {
  const [subs, setSubs] = useState<SubscriptionRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [newTag, setNewTag] = useState("");

  useEffect(() => { loadSubs(); }, []);

  async function loadSubs() {
    setLoading(true);
    try {
      const res = await listSubscriptions();
      setSubs(res.subscriptions || []);
    } catch (e: any) {
      message.error("Failed to load subscriptions");
    } finally {
      setLoading(false);
    }
  }

  async function handleSubscribe() {
    if (!newTag.trim()) {
      message.warning("Enter a species tag");
      return;
    }
    setLoading(true);
    try {
      await createSubscription([newTag.trim().toLowerCase()]);
      message.success(`Subscribed to "${newTag.trim()}" — check your email to confirm.`);
      setNewTag("");
      loadSubs();
    } catch (e: any) {
      message.error(e?.response?.data?.error || "Subscribe failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleUnsubscribe(subId: string) {
    setLoading(true);
    try {
      await deleteSubscription(subId);
      message.success("Unsubscribed");
      loadSubs();
    } catch (e: any) {
      message.error("Failed to unsubscribe");
    } finally {
      setLoading(false);
    }
  }

  const columns = [
    {
      title: "Tags",
      dataIndex: "tags",
      render: (tags: string[]) => tags?.map((t) => <Tag color="green" key={t}>{t}</Tag>),
    },
    { title: "Email", dataIndex: "email" },
    {
      title: "Status",
      dataIndex: "status",
      render: (s: string) => <Tag color={s === "active" ? "blue" : "default"}>{s}</Tag>,
    },
    { title: "Created", dataIndex: "createdAt", render: (d: string) => new Date(d).toLocaleDateString() },
    {
      title: "Action",
      key: "action",
      render: (_: any, r: SubscriptionRecord) => (
        <Popconfirm title="Unsubscribe?" onConfirm={() => handleUnsubscribe(r.subscriptionId)}>
          <Button danger icon={<DeleteOutlined />} size="small" />
        </Popconfirm>
      ),
    },
  ];

  return (
    <div>
      <Title level={4}>Notification Subscriptions</Title>
      <AntText type="secondary">
        Subscribe to species tags to receive email notifications when new files with those tags are uploaded.
        You must confirm the subscription via the email sent by AWS SNS.
      </AntText>

      <Card style={{ marginTop: 16, marginBottom: 16 }}>
        <Space>
          <Input
            placeholder="Species tag (e.g. kangaroo)"
            value={newTag}
            onChange={(e) => setNewTag(e.target.value)}
            onPressEnter={handleSubscribe}
            style={{ width: 250 }}
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={handleSubscribe} loading={loading}>
            Subscribe
          </Button>
          <Button icon={<ReloadOutlined />} onClick={loadSubs}>Refresh</Button>
        </Space>
      </Card>

      <Card title="Your Subscriptions">
        {loading ? (
          <div style={{ textAlign: "center", padding: 40 }}><Spin /></div>
        ) : subs.length === 0 ? (
          <Empty description="No subscriptions yet. Subscribe to a tag above." />
        ) : (
          <Table
            columns={columns}
            dataSource={subs}
            rowKey="subscriptionId"
            pagination={false}
            size="small"
          />
        )}
      </Card>
    </div>
  );
}

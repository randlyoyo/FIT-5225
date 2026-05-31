import { useState } from "react";
import {
  Card, Typography, Table, Button, Space, Modal, Input, Select, Tag,
  message, Popconfirm, Empty,
} from "antd";
import { DeleteOutlined, EditOutlined, SearchOutlined } from "@ant-design/icons";
import { queryTags, bulkTagEdit, deleteFiles } from "../api/client";
import type { FileRecord } from "../types";

const { Title, Text: AntText } = Typography;

export default function ManagePage() {
  const [files, setFiles] = useState<FileRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [searchTag, setSearchTag] = useState("");
  const [editModal, setEditModal] = useState(false);
  const [editTags, setEditTags] = useState("");
  const [editOp, setEditOp] = useState<number>(1);

  async function handleSearch() {
    if (!searchTag.trim()) {
      message.warning("Enter a tag to search");
      return;
    }
    setLoading(true);
    try {
      const res = await queryTags({ [searchTag.toLowerCase().trim()]: 1 });
      setFiles(res.files || []);
      setSelected([]);
    } catch (e: any) {
      message.error(e?.response?.data?.error || "Search failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleBulkEdit() {
    if (selected.length === 0) {
      message.warning("Select files first");
      return;
    }
    if (!editTags.trim()) {
      message.warning("Enter tags");
      return;
    }
    const selectedFiles = files.filter((f) => selected.includes(f.fileId));
    const urls = selectedFiles.map((f) => f.fileUrl);
    const tags = editTags.split(",").map((s) => s.trim().toLowerCase()).filter(Boolean);

    setLoading(true);
    try {
      await bulkTagEdit({ urls, tags, operation: editOp });
      message.success(`Tags ${editOp === 1 ? "added" : "removed"} on ${urls.length} file(s)`);
      setEditModal(false);
      handleSearch(); // Refresh
    } catch (e: any) {
      message.error(e?.response?.data?.error || "Edit failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete() {
    if (selected.length === 0) return;
    const selectedFiles = files.filter((f) => selected.includes(f.fileId));
    const urls = selectedFiles.map((f) => f.fileUrl);

    setLoading(true);
    try {
      await deleteFiles(urls);
      message.success(`Deleted ${urls.length} file(s)`);
      setSelected([]);
      handleSearch(); // Refresh
    } catch (e: any) {
      message.error(e?.response?.data?.error || "Delete failed");
    } finally {
      setLoading(false);
    }
  }

  const columns = [
    { title: "Thumbnail", key: "thumb", width: 80, render: (_: any, r: FileRecord) => r.thumbnailUrl ? <img src={r.thumbnailUrl} width={60} alt="" /> : <Tag>N/A</Tag> },
    { title: "Type", dataIndex: "fileType", width: 70, render: (t: string) => <Tag>{t}</Tag> },
    { title: "File URL", dataIndex: "fileUrl", ellipsis: true },
    {
      title: "Tags", dataIndex: "tagCounts", render: (tags: Record<string, number>) =>
        tags ? Object.entries(tags).map(([k, v]) => <Tag key={k}>{k}:{v}</Tag>) : <Tag>none</Tag>,
    },
    { title: "Status", dataIndex: "status", width: 90, render: (s: string) => <Tag color={s === "ready" ? "green" : "orange"}>{s}</Tag> },
  ];

  return (
    <div>
      <Title level={4}>Manage Files</Title>

      <Card style={{ marginBottom: 16 }}>
        <Space>
          <Input.Search
            placeholder="Search by tag (e.g. kangaroo)"
            value={searchTag}
            onChange={(e) => setSearchTag(e.target.value)}
            onSearch={handleSearch}
            enterButton={<SearchOutlined />}
            style={{ width: 300 }}
            loading={loading}
          />
          <Button
            icon={<EditOutlined />}
            disabled={selected.length === 0}
            onClick={() => setEditModal(true)}
          >
            Bulk Edit Tags
          </Button>
          <Popconfirm
            title={`Delete ${selected.length} file(s)?`}
            description="This will remove files from S3 and database."
            onConfirm={handleDelete}
            okText="Delete"
            okType="danger"
          >
            <Button danger icon={<DeleteOutlined />} disabled={selected.length === 0}>
              Delete Selected
            </Button>
          </Popconfirm>
        </Space>
      </Card>

      <Card>
        {files.length === 0 ? (
          <Empty description="Search by tag to find files to manage." />
        ) : (
          <Table
            rowSelection={{
              selectedRowKeys: selected,
              onChange: (keys) => setSelected(keys as string[]),
            }}
            columns={columns}
            dataSource={files}
            rowKey="fileId"
            pagination={{ pageSize: 10 }}
            size="small"
            loading={loading}
            scroll={{ x: 800 }}
          />
        )}
      </Card>

      {/* Bulk Edit Modal */}
      <Modal
        title="Bulk Edit Tags"
        open={editModal}
        onOk={handleBulkEdit}
        onCancel={() => setEditModal(false)}
        confirmLoading={loading}
      >
        <Space direction="vertical" style={{ width: "100%" }}>
          <AntText>Editing {selected.length} file(s)</AntText>
          <Select
            value={editOp}
            onChange={setEditOp}
            style={{ width: 200 }}
            options={[
              { value: 1, label: "Add Tags" },
              { value: 0, label: "Remove Tags" },
            ]}
          />
          <Input
            placeholder="Tags (comma separated, e.g. kangaroo,koala)"
            value={editTags}
            onChange={(e) => setEditTags(e.target.value)}
          />
        </Space>
      </Modal>
    </div>
  );
}

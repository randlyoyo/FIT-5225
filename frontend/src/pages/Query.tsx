import { useState } from "react";
import {
  Card, Form, Input, Button, Tabs, Table, Image, Tag, Typography, Empty,
  Space, InputNumber, message, Spin, Upload,
} from "antd";
import { SearchOutlined, UploadOutlined, LinkOutlined } from "@ant-design/icons";
import { queryTags, querySpecies, queryThumbnail, queryByFile } from "../api/client";
import type { FileRecord } from "../types";

const { Title, Text: AntText } = Typography;

const columns = [
  {
    title: "Preview",
    key: "preview",
    width: 120,
    render: (_: any, r: FileRecord) =>
      r.thumbnailUrl ? (
        <Image
          src={r.thumbnailUrl}
          width={100}
          alt=""
          fallback="data:image/png;base64,iVBORw0KGgo="
          preview={{ src: r.fileUrl || r.thumbnailUrl }}
          style={{ cursor: "pointer" }}
        />
      ) : r.fileType === "video" ? (
        <a href={r.fileUrl} target="_blank" rel="noopener noreferrer">
          <Tag color="blue">▶ Play</Tag>
        </a>
      ) : (
        <Tag>No preview</Tag>
      ),
  },
  { title: "Type", dataIndex: "fileType", width: 80, render: (t: string) => <Tag>{t}</Tag> },
  {
    title: "Tags",
    dataIndex: "tagCounts",
    render: (tags: Record<string, number>) =>
      tags
        ? Object.entries(tags).map(([k, v]) => <Tag key={k}>{k}: {v}</Tag>)
        : <Tag>untagged</Tag>,
  },
  {
    title: "URL",
    dataIndex: "fileUrl",
    ellipsis: true,
    render: (url: string) => (
      <a href={url} target="_blank" rel="noopener noreferrer">
        <LinkOutlined /> Open
      </a>
    ),
  },
  { title: "Status", dataIndex: "status", width: 100, render: (s: string) => <Tag color={s === "ready" ? "green" : "orange"}>{s}</Tag> },
];

export default function QueryPage() {
  const [results, setResults] = useState<FileRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [queryTagsForm] = Form.useForm();
  const [speciesForm] = Form.useForm();
  const [thumbForm] = Form.useForm();
  const [queryFile, setQueryFile] = useState<File | null>(null);
  const [byFileTags, setByFileTags] = useState<Record<string, number> | null>(null);

  async function handleQueryTags(values: { tags: { tag: string; count: number }[] }) {
    setLoading(true);
    try {
      const tags: Record<string, number> = {};
      for (const item of values.tags || []) {
        if (item.tag) tags[item.tag.toLowerCase().trim()] = item.count || 1;
      }
      if (Object.keys(tags).length === 0) {
        message.warning("Add at least one tag");
        return;
      }
      const res = await queryTags(tags);
      setResults(res.files || []);
      setByFileTags(null);
    } catch (e: any) {
      message.error(e?.response?.data?.error || "Query failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleQuerySpecies(values: { species: string }) {
    setLoading(true);
    try {
      const list = values.species.split(",").map((s: string) => s.trim()).filter(Boolean);
      if (list.length === 0) {
        message.warning("Enter at least one species");
        return;
      }
      const res = await querySpecies(list);
      setResults(res.files || []);
      setByFileTags(null);
    } catch (e: any) {
      message.error(e?.response?.data?.error || "Query failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleQueryThumbnail(values: { thumbnailUrl: string }) {
    setLoading(true);
    try {
      const res = await queryThumbnail(values.thumbnailUrl);
      setResults([{
        fileId: res.fileId,
        fileUrl: res.fullSizeUrl,
        thumbnailUrl: values.thumbnailUrl,
        fileType: res.fileType as any,
      } as FileRecord]);
      setByFileTags(null);
    } catch (e: any) {
      message.error(e?.response?.data?.error || "Not found");
      setResults([]);
    } finally {
      setLoading(false);
    }
  }

  async function handleQueryByFile() {
    if (!queryFile) {
      message.warning("Select a file first");
      return;
    }
    setLoading(true);
    try {
      const res = await queryByFile(queryFile);
      setByFileTags(res.queryTags);
      setResults(res.matchingFiles || []);
    } catch (e: any) {
      message.error(e?.response?.data?.error || "Query by file failed");
    } finally {
      setLoading(false);
    }
  }

  const tabItems = [
    {
      key: "tags",
      label: "By Tags",
      children: (
        <Form form={queryTagsForm} onFinish={handleQueryTags} layout="inline" style={{ gap: 8 }}>
          <Form.List name="tags" initialValue={[{ tag: "", count: 1 }]}>
            {(fields, { add, remove }) => (
              <div style={{ display: "flex", flexDirection: "column", gap: 8, width: "100%" }}>
                {fields.map(({ key, name, ...rest }) => (
                  <Space key={key}>
                    <Form.Item {...rest} name={[name, "tag"]} rules={[{ required: true }]}>
                      <Input placeholder="Species (e.g. kangaroo)" />
                    </Form.Item>
                    <Form.Item {...rest} name={[name, "count"]}>
                      <InputNumber min={1} placeholder="Min count" />
                    </Form.Item>
                    {fields.length > 1 && <Button onClick={() => remove(name)} danger size="small">×</Button>}
                  </Space>
                ))}
                <Space>
                  <Button onClick={() => add({ tag: "", count: 1 })} size="small">+ Add Tag</Button>
                  <Button type="primary" htmlType="submit" icon={<SearchOutlined />} loading={loading}>
                    Search
                  </Button>
                </Space>
              </div>
            )}
          </Form.List>
        </Form>
      ),
    },
    {
      key: "species",
      label: "By Species",
      children: (
        <Form form={speciesForm} onFinish={handleQuerySpecies} layout="inline">
          <Space>
            <Form.Item name="species" rules={[{ required: true }]}>
              <Input placeholder="e.g. dingo,koala" style={{ width: 300 }} />
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit" icon={<SearchOutlined />} loading={loading}>
                Search
              </Button>
            </Form.Item>
          </Space>
        </Form>
      ),
    },
    {
      key: "thumbnail",
      label: "By Thumbnail URL",
      children: (
        <Form form={thumbForm} onFinish={handleQueryThumbnail} layout="inline">
          <Space>
            <Form.Item name="thumbnailUrl" rules={[{ required: true, type: "url" }]}>
              <Input placeholder="https://...thumbnail.jpg" style={{ width: 400 }} />
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit" icon={<LinkOutlined />} loading={loading}>
                Find Full Size
              </Button>
            </Form.Item>
          </Space>
        </Form>
      ),
    },
    {
      key: "byFile",
      label: "By File",
      children: (
        <Space direction="vertical" style={{ width: "100%" }}>
          <Upload
            accept="image/*,video/*"
            showUploadList={true}
            maxCount={1}
            beforeUpload={(file) => {
              setQueryFile(file);
              return false;
            }}
            onRemove={() => setQueryFile(null)}
          >
            <Button icon={<UploadOutlined />}>Select Image</Button>
          </Upload>
          <Button type="primary" onClick={handleQueryByFile} loading={loading} disabled={!queryFile}>
            Query by File
          </Button>
          {byFileTags && (
            <div style={{ marginTop: 8 }}>
              <AntText strong>Detected Tags: </AntText>
              {Object.entries(byFileTags).map(([k, v]) => (
                <Tag key={k}>{k}: {v}</Tag>
              ))}
            </div>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Title level={4}>Query Files</Title>
      <Card style={{ marginBottom: 16 }}>
        <Tabs items={tabItems} />
      </Card>

      <Card title={`Results (${results.length})`}>
        {loading ? (
          <div style={{ textAlign: "center", padding: 40 }}><Spin size="large" /></div>
        ) : results.length === 0 ? (
          <Empty description="No results. Try a query above." />
        ) : (
          <Table
            columns={columns}
            dataSource={results}
            rowKey="fileId"
            pagination={{ pageSize: 20 }}
            size="small"
            scroll={{ x: 800 }}
          />
        )}
      </Card>
    </div>
  );
}

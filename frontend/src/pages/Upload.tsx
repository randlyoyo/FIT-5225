import { useState } from "react";
import {
  Card, Upload as AntUpload, Button, Typography, Progress, Alert,
  Descriptions, Tag, Space, message,
} from "antd";
import { InboxOutlined, CheckCircleOutlined, CloseCircleOutlined } from "@ant-design/icons";
import { uploadInit, uploadComplete, uploadToS3 } from "../api/client";
import type { UploadInitResponse } from "../types";

const { Title, Text: AntText } = Typography;
const { Dragger } = AntUpload;

type UploadState =
  | { phase: "idle" }
  | { phase: "hashing" }
  | { phase: "initiating" }
  | { phase: "uploading"; info: UploadInitResponse; progress: number }
  | { phase: "completing"; fileId: string }
  | { phase: "done"; info: UploadInitResponse }
  | { phase: "duplicate"; info: UploadInitResponse }
  | { phase: "error"; message: string };

export default function UploadPage() {
  const [state, setState] = useState<UploadState>({ phase: "idle" });
  const [recentUploads, setRecentUploads] = useState<UploadInitResponse[]>([]);

  /** Compute SHA-256 checksum of a file. Returns { hex, base64 }. */
  async function computeChecksum(file: File): Promise<{ hex: string; base64: string }> {
    const buffer = await file.arrayBuffer();
    let hashBuffer: ArrayBuffer;

    // Try Web Crypto API first (requires HTTPS or localhost)
    if (crypto.subtle) {
      try {
        hashBuffer = await crypto.subtle.digest("SHA-256", buffer);
        const bytes = new Uint8Array(hashBuffer);
        const hex = Array.from(bytes).map((b) => b.toString(16).padStart(2, "0")).join("");
        const base64 = btoa(String.fromCharCode(...bytes));
        return { hex, base64 };
      } catch {
        // Fallback to js-sha256
      }
    }

    // Fallback: js-sha256 (works on HTTP and HTTPS)
    const { sha256 } = await import("js-sha256");
    const bytes = new Uint8Array(buffer);
    const hashBytes = sha256.array(bytes);
    const hex = sha256(bytes);
    const base64 = btoa(String.fromCharCode(...hashBytes));
    return { hex, base64 };
  }

  async function handleUpload(file: File) {
    try {
      setState({ phase: "hashing" });
      const { hex: checksum, base64: checksumB64 } = await computeChecksum(file);
      const fileType = file.type.startsWith("video/") ? "video" : "image";

      setState({ phase: "initiating" });
      const info = await uploadInit(file.name, file.type, fileType, file.size, checksum);

      if (info.duplicate) {
        setState({ phase: "duplicate", info });
        message.info("File already exists in your library (detected by checksum).");
        return;
      }

      setState({ phase: "uploading", info, progress: 0 });
      await uploadToS3(info.uploadUrl, file, file.type, checksumB64, (pct) => {
        setState((s) => s.phase === "uploading" ? { ...s, progress: pct } as any : s);
      });

      setState({ phase: "completing", fileId: info.fileId });
      await uploadComplete(info.fileId, info.objectKey, checksum);

      setState({ phase: "done", info });
      setRecentUploads((prev) => [info, ...prev].slice(0, 5));
      message.success(`${file.name} uploaded successfully!`);

    } catch (err: any) {
      setState({ phase: "error", message: err?.message || "Upload failed" });
    }
  }

  const bgStyle = { background: "#f0f2f5", minHeight: "100%" };

  return (
    <div>
      <Title level={4}>Upload Media</Title>
      <AntText type="secondary">Upload images or videos for automatic species tagging via AI.</AntText>

      <Card style={{ marginTop: 16 }}>
        <Dragger
          accept="image/*,video/*"
          showUploadList={false}
          beforeUpload={(file) => {
            handleUpload(file);
            return false; // Prevent default upload
          }}
          disabled={state.phase !== "idle" && state.phase !== "done" && state.phase !== "error" && state.phase !== "duplicate"}
        >
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p className="ant-upload-text">Click or drag file here to upload</p>
          <p className="ant-upload-hint">Supports images (JPG, PNG) and videos (MP4, MOV)</p>
        </Dragger>
      </Card>

      {/* Upload Progress */}
      {state.phase !== "idle" && (
        <Card style={{ marginTop: 16 }}>
          {state.phase === "hashing" && <AntText>Computing file checksum...</AntText>}
          {state.phase === "initiating" && <AntText>Preparing upload...</AntText>}
          {state.phase === "uploading" && (
            <div>
              <AntText>Uploading to S3...</AntText>
              <Progress percent={state.progress} status="active" />
            </div>
          )}
          {state.phase === "completing" && <AntText>Finalizing upload...</AntText>}
          {state.phase === "done" && (
            <Alert
              type="success"
              message="Upload Complete"
              description={
                <Descriptions column={1} size="small">
                  <Descriptions.Item label="File ID">{state.info.fileId}</Descriptions.Item>
                  <Descriptions.Item label="Status">Processing — ML tagging in progress</Descriptions.Item>
                </Descriptions>
              }
              icon={<CheckCircleOutlined />}
              showIcon
            />
          )}
          {state.phase === "duplicate" && (
            <Alert
              type="warning"
              message="Duplicate File Detected"
              description={`This file is already in your library (checksum match). File ID: ${state.info.existingFileId}`}
              icon={<CheckCircleOutlined />}
              showIcon
            />
          )}
          {state.phase === "error" && (
            <Alert type="error" message="Upload Failed" description={state.message} icon={<CloseCircleOutlined />} showIcon />
          )}
        </Card>
      )}

      {/* Recent Uploads */}
      {recentUploads.length > 0 && (
        <Card title="Recent Uploads" style={{ marginTop: 16 }}>
          {recentUploads.map((u) => (
            <Tag key={u.fileId} color="blue" style={{ marginBottom: 4 }}>
              {u.fileId.slice(0, 8)}...
            </Tag>
          ))}
        </Card>
      )}
    </div>
  );
}

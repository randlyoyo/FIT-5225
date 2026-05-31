/**
 * API client for AussieEcoLens.
 * Handles AWS API Gateway calls with Cognito JWT.
 */
import axios, { AxiosInstance, InternalAxiosRequestConfig } from "axios";
import type {
  UploadInitResponse,
  QueryTagsRequest,
  QuerySpeciesRequest,
  QueryThumbnailRequest,
  BulkTagRequest,
  DeleteRequest,
  SubscriptionRequest,
  QueryResponse,
  QueryByFileResponse,
  FileRecord,
  SubscriptionRecord,
} from "../types";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:3000";
const GCP_BASE = import.meta.env.VITE_GCP_BASE_URL || "http://localhost:8080";

// ==================== Axios instance with JWT interceptor ====================

let getToken: (() => Promise<string | null>) | null = null;

export function setTokenGetter(fn: () => Promise<string | null>) {
  getToken = fn;
}

const api: AxiosInstance = axios.create({ baseURL: API_BASE });

api.interceptors.request.use(async (config: InternalAxiosRequestConfig) => {
  if (getToken) {
    const token = await getToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

// ==================== AWS API ====================

export async function uploadInit(
  filename: string,
  contentType: string,
  fileType: "image" | "video",
  sizeBytes: number,
  checksumSha256: string,
): Promise<UploadInitResponse> {
  const { data } = await api.post("/v1/uploads/init", {
    filename,
    contentType,
    fileType,
    sizeBytes,
    checksumSha256,
  });
  return data;
}

export async function uploadComplete(
  fileId: string,
  objectKey: string,
  checksumSha256: string,
): Promise<{ fileId: string; status: string }> {
  const { data } = await api.post("/v1/uploads/complete", {
    fileId,
    objectKey,
    checksumSha256,
  });
  return data;
}

export async function getFile(fileId: string): Promise<FileRecord> {
  const { data } = await api.get(`/v1/files/${fileId}`);
  return data;
}

export async function queryTags(tags: Record<string, number>): Promise<QueryResponse> {
  const { data } = await api.post("/v1/query/tags", { tags });
  return data;
}

export async function querySpecies(species: string[]): Promise<QueryResponse> {
  const { data } = await api.post("/v1/query/species", { species });
  return data;
}

export async function queryThumbnail(thumbnailUrl: string): Promise<{
  thumbnailUrl: string;
  fullSizeUrl: string;
  fileId: string;
  fileType: string;
}> {
  const { data } = await api.post("/v1/query/thumbnail", { thumbnailUrl });
  return data;
}

export async function bulkTagEdit(req: BulkTagRequest): Promise<{ updated: Array<{ fileId: string; fileUrl: string; status: string }> }> {
  const { data } = await api.post("/v1/tags/bulk", req);
  return data;
}

export async function deleteFiles(urls: string[]): Promise<{ deleted: Array<{ fileId: string; fileUrl: string; status: string }> }> {
  const { data } = await api.post("/v1/files/delete", { urls });
  return data;
}

export async function createSubscription(tags: string[]): Promise<SubscriptionRecord> {
  const { data } = await api.post("/v1/notifications/subscriptions", { tags });
  return data;
}

export async function listSubscriptions(): Promise<{ subscriptions: SubscriptionRecord[] }> {
  const { data } = await api.get("/v1/notifications/subscriptions");
  return data;
}

export async function deleteSubscription(subId: string): Promise<{ status: string }> {
  const { data } = await api.delete(`/v1/notifications/subscriptions/${subId}`);
  return data;
}

// ==================== GCP API (Cloud Run — direct call with JWT) ====================

const gcpApi: AxiosInstance = axios.create({ baseURL: GCP_BASE });

gcpApi.interceptors.request.use(async (config: InternalAxiosRequestConfig) => {
  if (getToken) {
    const token = await getToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

export async function queryByFile(file: File): Promise<QueryByFileResponse> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await gcpApi.post("/v1/query/by-file", form);
  return data;
}

// ==================== S3 Direct Upload ====================

export async function uploadToS3(
  uploadUrl: string,
  file: File,
  contentType: string,
  _checksumBase64: string,
  onProgress?: (pct: number) => void,
): Promise<void> {
  await axios.put(uploadUrl, file, {
    headers: {
      "Content-Type": contentType,
    },
    onUploadProgress: (evt) => {
      if (onProgress && evt.total) {
        onProgress(Math.round((evt.loaded / evt.total) * 100));
      }
    },
  });
}

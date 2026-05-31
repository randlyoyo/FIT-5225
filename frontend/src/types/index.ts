/** Core domain types for AussieEcoLens */

export interface FileRecord {
  fileId: string;
  ownerSub: string;
  ownerEmail: string;
  originalFilename: string;
  fileType: "image" | "video";
  contentType: string;
  sizeBytes: number;
  checksumSha256: string;
  status: "uploading" | "pending" | "processing" | "ready" | "error" | "deleted";
  bucket: string;
  objectKey: string;
  fileUrl: string;
  thumbnailKey?: string;
  thumbnailUrl?: string;
  frameKeys?: string[];
  frameThumbnailKeys?: string[];
  tagCounts: Record<string, number>;
  autoTagCounts?: Record<string, number>;
  manualTagCounts?: Record<string, number>;
  modelVersion?: string;
  createdAt: string;
  updatedAt: string;
  deletedAt?: string;
  errorMessage?: string;
}

export interface UploadInitResponse {
  fileId: string;
  uploadUrl: string;
  objectKey: string;
  expiresIn: number;
  duplicate: boolean;
  existingFileId?: string;
  existingFileUrl?: string;
  message?: string;
}

export interface QueryTagsRequest {
  tags: Record<string, number>;
}

export interface QuerySpeciesRequest {
  species: string[];
}

export interface QueryThumbnailRequest {
  thumbnailUrl: string;
}

export interface BulkTagRequest {
  urls: string[];
  tags: string[];
  operation: number; // 1=add, 0=remove
}

export interface DeleteRequest {
  urls: string[];
}

export interface SubscriptionRequest {
  tags: string[];
}

export interface SubscriptionRecord {
  subscriptionId: string;
  ownerSub: string;
  email: string;
  tags: string[];
  snsSubscriptionArns: Array<{ tag: string; subscriptionArn: string }>;
  status: string;
  createdAt: string;
}

export interface QueryResponse {
  files: FileRecord[];
  count: number;
}

export interface QueryByFileResponse {
  queryTags: Record<string, number>;
  matchingFiles: FileRecord[];
  count: number;
}

export interface ApiError {
  error: string;
}

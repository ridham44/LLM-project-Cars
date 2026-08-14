import { apiPost } from "./api";

export const ACCEPTED_DOCUMENT_TYPES = [".pdf", ".docx", ".txt", ".md", ".html"];

export function isAcceptedDocument(filename) {
  const lower = filename.toLowerCase();
  return ACCEPTED_DOCUMENT_TYPES.some((ext) => lower.endsWith(ext));
}

// Uploads a single document for ingestion. The backend is expected to
// respond with {document_id, status} where status progresses through
// uploading -> parsing -> chunking -> embedding -> indexed; callers that
// want live stage updates should poll /documents/{document_id} once that
// endpoint exists. For now this resolves once the initial upload completes.
export function uploadDocument(file) {
  const formData = new FormData();
  formData.append("file", file);
  return apiPost("/documents/upload", formData);
}

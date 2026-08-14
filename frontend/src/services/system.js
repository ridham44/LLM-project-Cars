import { apiGet } from "./api";

// GET /health now returns real ollama/model/knowledge-base status (see
// backend/api.py) in addition to the original {status:"ok"} shape older
// consumers expect.
export function getSystemStatus() {
  return apiGet("/health");
}

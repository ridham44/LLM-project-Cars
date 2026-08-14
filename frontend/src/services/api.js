const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export class ApiError extends Error {
  constructor(message, { status, detail } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function request(path, options = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: options.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
      ...options,
    });
  } catch (networkError) {
    throw new ApiError("Unable to reach the local research backend.", {
      detail: networkError.message,
    });
  }

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {
      // response had no JSON body
    }
    throw new ApiError(`Request failed (${response.status})`, {
      status: response.status,
      detail,
    });
  }

  if (response.status === 204) return null;
  return response.json();
}

export function apiGet(path) {
  return request(path, { method: "GET" });
}

export function apiPost(path, body) {
  const isFormData = body instanceof FormData;
  return request(path, {
    method: "POST",
    body: isFormData ? body : JSON.stringify(body),
  });
}

export async function checkHealth() {
  try {
    return await apiGet("/health");
  } catch (err) {
    return { status: "unreachable", detail: err.message };
  }
}

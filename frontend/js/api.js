// Thin wrapper around the backend REST API. All URLs are relative, so the app works behind any proxy.

async function request(method, url, body) {
  const response = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  let data = null;
  try { data = await response.json(); } catch { /* non-JSON error page */ }
  if (!response.ok && !(data && data.validation)) {
    throw new Error((data && data.error) || `Request failed (${response.status})`);
  }
  return { ok: response.ok, status: response.status, data };
}

export const api = {
  tasks: () => request("GET", "api/tasks"),
  validate: (payload) => request("POST", "api/validate", payload),
  compare: (payload) => request("POST", "api/compare", payload),
};

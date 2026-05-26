const BASE = process.env.REACT_APP_API_URL || "http://localhost:5000/api";

const get = (url) =>
  fetch(`${BASE}${url}`).then((r) => r.json());

const post = (url, body) =>
  fetch(`${BASE}${url}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => r.json());

const put = (url, body) =>
  fetch(`${BASE}${url}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => r.json());

const del = (url) =>
  fetch(`${BASE}${url}`, { method: "DELETE" }).then((r) => r.json());

// ── Auth ────────────────────────────────────────────────────────────────────
export const login = (email, password) =>
  post("/auth/login", { email, password });

export const signup = (name, email, password) =>
  post("/auth/signup", { name, email, password });

export const forgotPassword = (email) =>
  post("/auth/forgot-password", { email });

export const verifyOtp = (email, otp) =>
  post("/auth/verify-otp", { email, otp });

export const resetPassword = (email, newPassword) =>
  post("/auth/reset-password", { email, new_password: newPassword });

// ── Dashboard ───────────────────────────────────────────────────────────────
export const getDashboardStats = (userId) =>
  get(`/dashboard/stats?user_id=${userId}`);

// ── Upload ──────────────────────────────────────────────────────────────────
export const uploadFile = (file, userId, useClaude = false) => {
  const form = new FormData();
  form.append("file", file);
  form.append("user_id", userId);
  form.append("use_claude", useClaude ? "true" : "false");
  return fetch(`${BASE}/upload`, { method: "POST", body: form }).then((r) =>
    r.json()
  );
};

export const getUploadStatus = (analysisId) =>
  get(`/upload/status/${analysisId}`);

// ── Reports ─────────────────────────────────────────────────────────────────
export const getReports = (userId, filters = {}) => {
  const params = new URLSearchParams({ user_id: userId, ...filters });
  return get(`/reports?${params}`);
};

export const updateBugStatus = (bugId, status) =>
  put(`/reports/bug/${bugId}/status`, { status });

export const getReportsSummary = (userId) =>
  get(`/reports/summary?user_id=${userId}`);

// ── History ─────────────────────────────────────────────────────────────────
export const getHistory = (userId, filters = {}) => {
  const params = new URLSearchParams({ user_id: userId, ...filters });
  return get(`/history?${params}`);
};

export const getHistoryStats = (userId) =>
  get(`/history/stats?user_id=${userId}`);

export const deleteHistory = (historyId) => del(`/history/${historyId}`);

export const toggleStar = (historyId) =>
  put(`/history/${historyId}/star`, {});

// ── Settings ─────────────────────────────────────────────────────────────────
export const getProfile = (userId) =>
  get(`/settings/profile?user_id=${userId}`);

export const updateProfile = (userId, data) =>
  put("/settings/profile", { user_id: userId, ...data });

export const updatePassword = (userId, currentPassword, newPassword) =>
  put("/settings/password", {
    user_id: userId,
    current_password: currentPassword,
    new_password: newPassword,
  });

export const getClaudeMode = (userId) =>
  get(`/settings/claude-mode?user_id=${userId}`);

export const setClaudeMode = (userId, enabled) =>
  put("/settings/claude-mode", { user_id: userId, claude_mode: enabled });

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export class ApiError extends Error {
  constructor(message, status, payload) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

export function getToken() {
  return localStorage.getItem("krishimitra_token");
}

export function setToken(token) {
  if (token) {
    localStorage.setItem("krishimitra_token", token);
  } else {
    localStorage.removeItem("krishimitra_token");
  }
}

async function parseResponse(response) {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  if (contentType.includes("audio") || contentType.includes("octet-stream")) {
    return response.blob();
  }
  return response.text();
}

export async function request(path, options = {}) {
  const token = getToken();
  const headers = new Headers(options.headers || {});

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const isFormData = options.body instanceof FormData;
  if (options.body && !isFormData && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
    body: options.body && !isFormData && typeof options.body !== "string" ? JSON.stringify(options.body) : options.body,
  });

  const payload = await parseResponse(response);

  if (!response.ok) {
    const message = payload?.detail || payload?.message || `Request failed with ${response.status}`;
    throw new ApiError(message, response.status, payload);
  }

  return payload;
}

export const api = {
  login: (data) => request("/auth/login", { method: "POST", body: data }),
  register: (data) => request("/auth/register", { method: "POST", body: data }),
  me: () => request("/auth/me"),
  updateMe: (data) => request("/auth/me", { method: "PUT", body: data }),
  getProfile: () => request("/auth/me/profile"),
  updateProfile: (data) => request("/auth/me/profile", { method: "PUT", body: data }),

  chat: (data) => request("/chat", { method: "POST", body: data }),
  chatHistory: (sessionId) => request(`/chat/history${sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : ""}`),
  chatSessions: () => request("/chat/sessions"),

  schemes: () => request("/scheme/list"),
  checkScheme: (data) => request("/scheme/check", { method: "POST", body: data }),
  schemeHistory: () => request("/scheme/history"),

  createGrievance: (data) => request("/grievance/create", { method: "POST", body: data }),
  trackGrievance: (trackingId) => request(`/grievance/track/${encodeURIComponent(trackingId)}`),
  myGrievances: () => request("/grievance/my"),
  officerGrievances: () => request("/grievance/officer/all"),
  officerStaff: () => request("/grievance/officer/staff"),
  officerGrievance: (id) => request(`/grievance/officer/${id}`),
  officerTrackGrievance: (trackingId) => request(`/grievance/officer/track/${encodeURIComponent(trackingId)}`),
  updateGrievance: (id, data) => request(`/grievance/officer/${id}`, { method: "PUT", body: data }),

  analyzeDisease: (formData) => request("/disease/analyze", { method: "POST", body: formData }),
  diseaseReports: () => request("/disease/reports"),
  officerDiseaseReports: () => request("/officer/disease-reports"),
  officerDashboard: () => request("/officer/dashboard"),
  ivrSessions: () => request("/ivr/sessions"),

  transcribeVoice: (formData) => request("/voice/transcribe", { method: "POST", body: formData }),
  speak: (data) => request("/voice/speak", { method: "POST", body: data }),
  voiceRespond: (formData) => request("/voice/respond", { method: "POST", body: formData }),
  voiceLiveSession: (formData) => request("/voice/live/session", { method: "POST", body: formData }),

  adminAnalytics: () => request("/admin/analytics"),
  adminUsers: () => request("/admin/users"),
  toggleUser: (id) => request(`/admin/users/${id}/toggle-active`, { method: "PUT" }),
  updateUserRole: (id, role) => request(`/admin/users/${id}/role?role=${encodeURIComponent(role)}`, { method: "PUT" }),
  adminSchemes: () => request("/admin/schemes"),
  createAdminScheme: (data) => request("/admin/schemes", { method: "POST", body: data }),
};

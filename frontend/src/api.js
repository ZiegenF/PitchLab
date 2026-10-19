async function request(path, options) {
  const res = await fetch(`/api${path}`, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `${res.status} ${res.statusText}`);
  }
  return res.status === 204 ? null : res.json();
}

const json = (method, body) => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

const upload = (file) => {
  const form = new FormData();
  form.append("file", file);
  return { method: "POST", body: form };
};

export const api = {
  // account
  me: () => request("/auth/me"),
  signup: (body) => request("/auth/signup", json("POST", body)),
  login: (body) => request("/auth/login", json("POST", body)),
  logout: () => request("/auth/logout", { method: "POST" }),
  setPreferences: (body) => request("/me/preferences", json("PUT", body)),
  myDashboard: () => request("/me/dashboard"),
  track: (id) => request(`/me/tracked/${id}`, { method: "PUT" }),
  untrack: (id) => request(`/me/tracked/${id}`, { method: "DELETE" }),
  goals: (id) => request(`/pitchers/${id}/goals`),
  addGoal: (id, body) => request(`/pitchers/${id}/goals`, json("POST", body)),
  deleteGoal: (goalId) => request(`/goals/${goalId}`, { method: "DELETE" }),
  insights: (id) => request(`/pitchers/${id}/insights`),

  statDefinitions: () => request("/stats"),
  pitchers: () => request("/pitchers"),
  createPitcher: (body) => request("/pitchers", json("POST", body)),
  updatePitcher: (id, body) => request(`/pitchers/${id}`, json("PATCH", body)),
  deletePitcher: (id) => request(`/pitchers/${id}`, { method: "DELETE" }),
  uploadPhoto: (id, file) => request(`/pitchers/${id}/photo`, upload(file)),
  deletePhoto: (id) => request(`/pitchers/${id}/photo`, { method: "DELETE" }),
  addGame: (id, body) => request(`/pitchers/${id}/games`, json("POST", body)),
  deleteGame: (id, gameId) => request(`/pitchers/${id}/games/${gameId}`, { method: "DELETE" }),
  dashboard: (id) => request(`/pitchers/${id}`),
  arsenal: (id) => request(`/pitchers/${id}/arsenal`),
  trend: (id) => request(`/pitchers/${id}/trend`),
  games: (id) => request(`/pitchers/${id}/games`),
  pitches: (id, params = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v != null && v !== "")
    );
    return request(`/pitchers/${id}/pitches?${qs}`);
  },
  uploadCsv: (file) => request("/ingest/csv", upload(file)),
};

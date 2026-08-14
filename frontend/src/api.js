// Same-origin ("") in local dev / Docker, where Vite's dev proxy forwards
// API calls to the backend. On Render, frontend and backend are separate
// services on different origins, so the build sets VITE_API_URL to the
// backend service's URL.
const BASE = import.meta.env.VITE_API_URL || "";

function getToken() {
  return localStorage.getItem("gpron_token");
}

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request(method, path, body = null) {
  const opts = {
    method,
    headers: { "Content-Type": "application/json", ...authHeaders() },
  };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(BASE + path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "Request failed");
  return data;
}

export const api = {
  register:      (payload)               => request("POST",  "/auth/register",    payload),
  login:         (payload)               => request("POST",  "/auth/login",       payload),
  googleLogin:   (payload)               => request("POST",  "/auth/google",      payload),
  createOrder:   (payload)               => request("POST",  "/orders",           payload),
  myOrders:      ()                      => request("GET",   "/orders/user"),
  allOrders:     (status)                => request("GET",   status ? `/orders/all?status=${status}` : "/orders/all"),
  updateStatus:  (tracking_id, status)   => request("PATCH", "/orders/status",    { tracking_id, status }),
  track:         (tracking_id)           => request("GET",   `/track/${tracking_id}`),
  subscribe:     (email)                 => request("POST",  "/newsletter/subscribe", { email }),
};

/* ── Auth helpers ── */
export function saveSession(token, user) {
  localStorage.setItem("gpron_token", token);
  localStorage.setItem("gpron_user",  JSON.stringify(user));
}

export function getUser() {
  try { return JSON.parse(localStorage.getItem("gpron_user")); } catch { return null; }
}

export function logout() {
  localStorage.removeItem("gpron_token");
  localStorage.removeItem("gpron_user");
  window.location.href = "/login.html";
}

export function requireAuth(role = null) {
  const user  = getUser();
  const token = getToken();
  if (!user || !token) { window.location.href = "/login.html"; return null; }
  if (role && user.role !== role) {
    window.location.href = user.role === "manager" ? "/manager.html" : "/dashboard.html";
    return null;
  }
  return user;
}

/* ── Normalise an order so cart is always an array ── */
export function normaliseOrder(o) {
  if (!o.cart || !o.cart.length) {
    // Legacy order stored only flat items list
    o.cart = (o.items || []).map(name => ({
      name,
      quantity: 1,
      unit_price: o.price > 0 ? Math.round((o.price - (o.base_fee || 0)) / (o.items?.length || 1)) : 0,
      subtotal:   o.price > 0 ? Math.round((o.price - (o.base_fee || 0)) / (o.items?.length || 1)) : 0,
    }));
  }
  return o;
}

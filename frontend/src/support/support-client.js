// HTTP client for the support chat API. The conversation token lives in
// localStorage and is sent as X-Support-Token; no provider keys ever reach
// the browser.
import { BASE } from "../api.js";

const SESSION_KEY = "gpron_support_session";

export class SupportApiError extends Error {
  constructor(status, detail) {
    super(detail || "Something went wrong. Please try again.");
    this.status = status;
  }
}

export function loadSession() {
  try {
    const raw = JSON.parse(localStorage.getItem(SESSION_KEY));
    return raw && raw.id && raw.token ? raw : null;
  } catch {
    return null;
  }
}

export function saveSession(session) {
  try { localStorage.setItem(SESSION_KEY, JSON.stringify(session)); } catch { /* private mode */ }
}

export function clearSession() {
  try { localStorage.removeItem(SESSION_KEY); } catch { /* ignore */ }
}

export function newClientId() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2, "0")).join("");
}

function loginHeader() {
  const token = localStorage.getItem("gpron_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function errorDetail(data) {
  if (!data) return "";
  if (typeof data.detail === "string") return data.detail;
  // FastAPI validation errors: [{msg: "..."}]
  if (Array.isArray(data.detail) && data.detail[0]?.msg) {
    return data.detail[0].msg.replace(/^Value error, /, "");
  }
  return "";
}

async function request(method, path, { body, session, withLogin = false } = {}) {
  const headers = { ...(withLogin ? loginHeader() : {}) };
  if (session) headers["X-Support-Token"] = session.token;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let res;
  try {
    res = await fetch(BASE + path, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new SupportApiError(0, "You appear to be offline. We'll keep trying.");
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new SupportApiError(res.status, errorDetail(data));
  return data;
}

export const supportApi = {
  config: () => request("GET", "/support/config"),

  async createConversation() {
    const data = await request("POST", "/support/conversations", { withLogin: true });
    const session = { id: data.conversation_id, token: data.token };
    saveSession(session);
    return session;
  },

  messages: (session, afterSeq) =>
    request("GET", `/support/conversations/${session.id}/messages?after_seq=${afterSeq}`, { session }),

  sendText: (session, clientMsgId, text) =>
    request("POST", `/support/conversations/${session.id}/messages`, {
      session,
      body: { client_msg_id: clientMsgId, text },
    }),

  escalate: (session, payload) =>
    request("POST", `/support/conversations/${session.id}/escalate`, {
      session,
      body: payload,
      withLogin: true,
    }),

  async audio(session, messageId) {
    let res;
    try {
      res = await fetch(`${BASE}/support/conversations/${session.id}/messages/${messageId}/audio`, {
        headers: { "X-Support-Token": session.token },
      });
    } catch {
      throw new SupportApiError(0, "You appear to be offline.");
    }
    if (!res.ok) {
      const data = await res.json().catch(() => null);
      throw new SupportApiError(res.status, errorDetail(data));
    }
    return res.blob();
  },

  // XHR rather than fetch: fetch can't report upload progress.
  sendVoice(session, clientMsgId, blob, mime, onProgress) {
    return new Promise((resolve, reject) => {
      const form = new FormData();
      const ext = mime.includes("ogg") ? "ogg" : mime.includes("mp4") ? "m4a" : "webm";
      form.append("file", blob, `voice-note.${ext}`);
      form.append("client_msg_id", clientMsgId);

      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${BASE}/support/conversations/${session.id}/voice`);
      xhr.setRequestHeader("X-Support-Token", session.token);
      xhr.responseType = "json";
      xhr.upload.onprogress = e => {
        if (e.lengthComputable) onProgress?.(e.loaded / e.total);
      };
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) resolve(xhr.response);
        else reject(new SupportApiError(xhr.status, errorDetail(xhr.response)));
      };
      xhr.onerror = () => reject(new SupportApiError(0, "Upload failed. Check your connection and try again."));
      xhr.send(form);
    });
  },
};

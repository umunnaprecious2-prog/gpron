// Gpron support chat panel. Loaded on demand by launcher.js.
//
// The server decides when to reply (it batches quick successive messages),
// so this file never runs its own "wait and reply" timer. It sends each
// message as it's written, then polls for replies while the server reports
// that a reply is pending. All message text is rendered with textContent.
import "./widget.css";
import {
  SupportApiError,
  clearSession,
  loadSession,
  newClientId,
  supportApi,
} from "./support-client.js";

const OPEN_KEY = "gpron_support_open";
const SUGGESTIONS = [
  "What laundry services do you offer?",
  "How much does your service cost?",
  "How do I place an order?",
  "How can I track my laundry?",
  "How does express service work?",
];
const STAGE_TEXT = {
  collecting: "I'm following along...",
  transcribing: "Listening to your voice note...",
  thinking: "Putting that together...",
};
const ICON = {
  person: '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  minimize: '<path d="M6 9l6 6 6-6"/>',
  close: '<path d="M18 6L6 18M6 6l12 12"/>',
  send: '<path d="M22 2L11 13"/><path d="M22 2l-7 20-4-9-9-4 20-7z"/>',
  mic: '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10v1a7 7 0 0 0 14 0v-1M12 18v4"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor"/>',
  trash: '<path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/>',
  play: '<path d="M7 4v16l13-8z" fill="currentColor"/>',
  pause: '<path d="M7 4h4v16H7zM13 4h4v16h-4z" fill="currentColor"/>',
  back: '<path d="M15 18l-6-6 6-6"/>',
};

function icon(name) {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICON[name]}</svg>`;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function formatTime(iso) {
  // The API sends naive UTC timestamps; mark them as UTC before parsing.
  const date = iso ? new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`) : new Date();
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function pickRecordingMime() {
  if (typeof MediaRecorder === "undefined") return null;
  const options = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/mp4", "audio/webm"];
  return options.find(type => MediaRecorder.isTypeSupported?.(type)) ?? "";
}

class SupportWidget {
  constructor(launcher) {
    this.launcher = launcher;
    this.session = loadSession();
    this.config = null;
    this.lastSeq = 0;
    this.byId = new Map(); // server message id -> rendered <li>
    this.byClientId = new Map(); // optimistic bubbles awaiting their server id
    this.transcribingSeqs = new Set();
    this.stage = null;
    this.pollTimer = null;
    this.pollFailures = 0;
    this.closed = true;
    this.inFlight = 0; // sends not yet acknowledged
    this.audio = { player: null, playingId: null, cache: new Map() };
    this.rec = null;
    this.build();
    this.loadConfig();
    if (this.session) this.poll();
  }

  /* ---------------------------------------------------------------- DOM */

  build() {
    const root = el("section", "gp-chat");
    root.hidden = true;
    root.setAttribute("role", "dialog");
    root.setAttribute("aria-modal", "false");
    root.setAttribute("aria-labelledby", "gp-chat-title");
    root.innerHTML = `
      <header class="gp-chat__header">
        <div class="gp-chat__avatar" aria-hidden="true">🧺<span class="gp-chat__online"></span></div>
        <div class="gp-chat__title">
          <strong id="gp-chat-title">Ada</strong>
          <span class="gp-chat__subtitle">Gpron AI assistant</span>
        </div>
        <button type="button" class="gp-chat__icon-btn" data-action="human" aria-label="Talk to a person" title="Talk to a person">${icon("person")}</button>
        <button type="button" class="gp-chat__icon-btn" data-action="minimize" aria-label="Minimize chat" title="Minimize">${icon("minimize")}</button>
        <button type="button" class="gp-chat__icon-btn" data-action="close" aria-label="Close chat" title="Close">${icon("close")}</button>
      </header>
      <div class="gp-chat__banner" role="status" hidden></div>
      <div class="gp-chat__body">
        <ol class="gp-chat__log" role="log" aria-live="polite" aria-relevant="additions"></ol>
        <div class="gp-suggestions" aria-label="Suggested questions"></div>
      </div>
      <div class="gp-chat__status" aria-live="polite"></div>
      <form class="gp-chat__composer" novalidate>
        <label class="gp-sr-only" for="gp-chat-input">Type your message</label>
        <textarea id="gp-chat-input" class="gp-chat__input" rows="1" placeholder="Type your message..." autocomplete="off"></textarea>
        <button type="button" class="gp-round-btn gp-round-btn--mic" data-action="record" aria-label="Record a voice note" title="Record a voice note" hidden>${icon("mic")}</button>
        <button type="submit" class="gp-round-btn gp-round-btn--send" aria-label="Send message" disabled>${icon("send")}</button>
      </form>
      <div class="gp-counter" hidden></div>
      <div class="gp-recorder" hidden></div>
      <p class="gp-chat__footer">
        <span>AI assistant. Prices and order status come from Gpron's system.</span>
        <button type="button" class="gp-link-btn" data-action="new-chat">New chat</button>
      </p>
      <div class="gp-sheet" hidden></div>`;
    document.body.appendChild(root);

    this.root = root;
    this.log = root.querySelector(".gp-chat__log");
    this.body = root.querySelector(".gp-chat__body");
    this.banner = root.querySelector(".gp-chat__banner");
    this.statusEl = root.querySelector(".gp-chat__status");
    this.form = root.querySelector(".gp-chat__composer");
    this.input = root.querySelector(".gp-chat__input");
    this.sendBtn = root.querySelector(".gp-round-btn--send");
    this.micBtn = root.querySelector('[data-action="record"]');
    this.counter = root.querySelector(".gp-counter");
    this.recorderEl = root.querySelector(".gp-recorder");
    this.sheet = root.querySelector(".gp-sheet");
    this.suggestions = root.querySelector(".gp-suggestions");

    this.renderWelcome();

    root.addEventListener("click", e => {
      const action = e.target.closest("[data-action]")?.dataset.action;
      if (action === "minimize") this.hide({ keepPolling: true });
      else if (action === "close") this.hide({ keepPolling: false });
      else if (action === "human") this.openEscalation();
      else if (action === "record") this.startRecording();
      else if (action === "new-chat") this.newChat();
    });
    root.addEventListener("keydown", e => {
      if (e.key !== "Escape") return;
      if (!this.sheet.hidden) this.closeEscalation();
      else if (this.rec) this.cancelRecording();
      else this.hide({ keepPolling: true });
    });
    this.form.addEventListener("submit", e => {
      e.preventDefault();
      this.submitInput();
    });
    this.input.addEventListener("keydown", e => {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
        e.preventDefault();
        this.submitInput();
      }
    });
    this.input.addEventListener("input", () => this.onInput());
  }

  renderWelcome() {
    const li = el("li", "gp-msg gp-msg--assistant");
    li.appendChild(
      el(
        "div",
        "gp-bubble",
        "Hi, I'm Ada, Gpron's AI assistant. I can help with our services, prices, placing an order or tracking your laundry. You can type or send a voice note. Need a person? Tap the profile icon at the top.",
      ),
    );
    this.log.appendChild(li);

    for (const question of SUGGESTIONS) {
      const chip = el("button", "gp-chip", question);
      chip.type = "button";
      chip.addEventListener("click", () => this.sendText(question));
      this.suggestions.appendChild(chip);
    }
  }

  async loadConfig() {
    try {
      this.config = await supportApi.config();
    } catch {
      this.config = { ai_available: false, voice_input: false, voice_output: false, voice_max_seconds: 60, max_message_chars: 1000 };
      this.showBanner("Chat is having trouble connecting. You can still leave a request for our team.");
    }
    this.root.querySelector("#gp-chat-title").textContent = this.config.assistant_name || "Ada";
    if (!this.config.ai_available) {
      this.root.querySelector(".gp-chat__online").classList.add("is-offline");
      this.root.querySelector(".gp-chat__subtitle").textContent = "Assistant offline. Tap the profile icon to reach our team.";
    }
    this.micBtn.hidden = !(this.config.voice_input && pickRecordingMime() !== null && navigator.mediaDevices?.getUserMedia);
    this.input.maxLength = this.config.max_message_chars;
  }

  /* ------------------------------------------------------- open / close */

  show() {
    this.closed = false;
    this.root.hidden = false;
    this.launcher.hidden = true;
    this.launcher.setAttribute("aria-expanded", "true");
    this.launcher.querySelector(".gp-unread").hidden = true;
    try { sessionStorage.setItem(OPEN_KEY, "1"); } catch { /* ignore */ }
    if (this.session) this.poll();
    this.scrollToEnd();
    this.input.focus();
  }

  hide({ keepPolling }) {
    if (this.rec) this.cancelRecording();
    this.root.hidden = true;
    this.launcher.hidden = false;
    this.launcher.setAttribute("aria-expanded", "false");
    this.closed = !keepPolling;
    if (!keepPolling) this.stopPolling();
    this.stopAudio();
    try { sessionStorage.setItem(OPEN_KEY, "0"); } catch { /* ignore */ }
    this.launcher.focus();
  }

  newChat() {
    if (!window.confirm("Start a new chat? This conversation will be cleared from this device.")) return;
    clearSession();
    this.session = null;
    this.stopPolling();
    this.stopAudio();
    this.lastSeq = 0;
    this.byId.clear();
    this.byClientId.clear();
    this.transcribingSeqs.clear();
    this.log.textContent = "";
    this.suggestions.textContent = "";
    this.suggestions.hidden = false;
    this.renderWelcome();
    this.setStage(null);
    this.input.focus();
  }

  /* ---------------------------------------------------------- messages */

  onInput() {
    this.input.style.height = "auto";
    this.input.style.height = `${Math.min(this.input.scrollHeight, 120)}px`;
    const length = this.input.value.length;
    const max = this.config?.max_message_chars ?? 1000;
    this.sendBtn.disabled = !this.input.value.trim();
    this.counter.hidden = length < max * 0.8;
    this.counter.textContent = `${length} / ${max}`;
  }

  submitInput() {
    const text = this.input.value.trim();
    if (!text) return;
    this.input.value = "";
    this.onInput();
    this.sendText(text);
  }

  async ensureSession() {
    if (!this.session) this.session = await supportApi.createConversation();
    return this.session;
  }

  async sendText(text, clientId = newClientId(), existing = null) {
    this.suggestions.hidden = true;
    const li = existing ?? this.renderPending({ text, kind: "text", clientId });
    this.setMeta(li, "Sending...");
    this.inFlight += 1;
    try {
      await this.ensureSession();
      const res = await supportApi.sendText(this.session, clientId, text);
      this.bind(li, res.message);
      this.setStage(this.stage ?? "collecting");
      this.schedulePoll(1000);
    } catch (err) {
      if (err.status === 404) {
        // Conversation expired (retention) or was cleared: start over once.
        clearSession();
        this.session = null;
        if (!existing) return this.sendText(text, clientId, li);
      }
      this.markFailed(li, err.message, () => this.sendText(text, clientId, li));
    } finally {
      this.inFlight -= 1;
    }
  }

  renderPending({ text, kind, clientId = null }) {
    const li = el("li", "gp-msg gp-msg--customer");
    if (clientId) this.byClientId.set(clientId, li);
    const bubble = el("div", "gp-bubble");
    if (kind === "voice") {
      bubble.innerHTML = `<div class="gp-voice-label">${icon("mic")}<span>Voice note</span></div>`;
      bubble.appendChild(el("div", "gp-voice-pending", text));
    } else {
      bubble.textContent = text;
    }
    li.appendChild(bubble);
    li.appendChild(el("div", "gp-meta"));
    this.log.appendChild(li);
    this.scrollToEnd();
    return li;
  }

  setMeta(li, text, isError = false) {
    const meta = li.querySelector(".gp-meta");
    meta.textContent = "";
    const span = el("span", isError ? "gp-error" : "", text);
    meta.appendChild(span);
    return meta;
  }

  markFailed(li, message, retry) {
    const meta = this.setMeta(li, message || "Not sent.", true);
    const btn = el("button", "gp-link-btn", "Retry");
    btn.type = "button";
    btn.addEventListener("click", retry, { once: true });
    meta.appendChild(btn);
  }

  bind(li, message) {
    li.dataset.id = message.id;
    this.byId.set(message.id, li);
    if (message.client_msg_id) this.byClientId.delete(message.client_msg_id);
    this.updateCustomerMessage(li, message);
  }

  updateCustomerMessage(li, message) {
    if (message.kind === "voice") {
      const bubble = li.querySelector(".gp-bubble");
      let body = bubble.querySelector(".gp-voice-pending, .gp-voice-text");
      if (!body) {
        bubble.innerHTML = `<div class="gp-voice-label">${icon("mic")}<span>Voice note</span></div>`;
        body = el("div");
        bubble.appendChild(body);
      }
      if (message.status === "transcribing") {
        body.className = "gp-voice-pending";
        body.textContent = "Transcribing...";
        this.transcribingSeqs.add(message.seq);
      } else {
        this.transcribingSeqs.delete(message.seq);
        if (message.status === "ready") {
          body.className = "gp-voice-text";
          body.textContent = message.content;
        } else {
          body.className = "gp-voice-pending";
          body.textContent = "Couldn't make out this voice note. Please try again or type it.";
        }
      }
    }
    this.setMeta(li, formatTime(message.created_at));
  }

  renderServerMessage(message) {
    // A poll can return a just-sent message before its send request resolves.
    const optimistic = message.client_msg_id && this.byClientId.get(message.client_msg_id);
    if (optimistic) {
      this.bind(optimistic, message);
      return;
    }
    const existing = this.byId.get(message.id);
    if (existing) {
      if (message.role === "customer") this.updateCustomerMessage(existing, message);
      return;
    }
    if (message.role === "customer") {
      const li = this.renderPending({ text: message.content, kind: message.kind });
      this.bind(li, message);
      return;
    }

    const li = el("li", `gp-msg gp-msg--${message.role}${message.status === "fallback" ? " gp-msg--fallback" : ""}`);
    li.dataset.id = message.id;
    li.appendChild(el("div", "gp-bubble", message.content));
    const meta = el("div", "gp-meta");
    meta.appendChild(el("span", "", formatTime(message.created_at)));
    if (message.role === "assistant" && message.status === "ready" && this.config?.voice_output) {
      meta.appendChild(this.playButton(message.id));
    }
    li.appendChild(meta);
    this.byId.set(message.id, li);
    this.log.appendChild(li);
    if (this.root.hidden && message.role === "assistant") {
      this.launcher.querySelector(".gp-unread").hidden = false;
    }
  }

  /* ------------------------------------------------------------ polling */

  schedulePoll(delay) {
    clearTimeout(this.pollTimer);
    this.pollTimer = setTimeout(() => this.poll(), delay);
  }

  stopPolling() {
    clearTimeout(this.pollTimer);
    this.pollTimer = null;
  }

  async poll() {
    if (!this.session) return;
    // Re-fetch from the oldest voice note still transcribing so its status updates.
    const cursor = this.transcribingSeqs.size
      ? Math.min(this.lastSeq, Math.min(...this.transcribingSeqs) - 1)
      : this.lastSeq;
    let data;
    try {
      data = await supportApi.messages(this.session, cursor);
    } catch (err) {
      if (err.status === 404) {
        clearSession();
        this.session = null;
        this.setStage(null);
        this.showBanner("That chat has expired. Send a message to start a new one.");
        return;
      }
      this.pollFailures += 1;
      this.showBanner("Connection lost. Retrying...");
      this.root.querySelector(".gp-chat__online").classList.add("is-offline");
      this.schedulePoll(Math.min(1000 * 2 ** this.pollFailures, 15000));
      return;
    }
    if (this.pollFailures) {
      this.pollFailures = 0;
      this.hideBanner();
      if (this.config?.ai_available) this.root.querySelector(".gp-chat__online").classList.remove("is-offline");
    }

    const atBottom = this.body.scrollHeight - this.body.scrollTop - this.body.clientHeight < 80;
    for (const message of data.messages) {
      this.renderServerMessage(message);
      this.lastSeq = Math.max(this.lastSeq, message.seq);
    }
    if (data.messages.length) {
      this.suggestions.hidden = true;
      if (atBottom) this.scrollToEnd();
    }
    this.setStage(data.stage);

    const keepGoing = data.stage || this.inFlight > 0 || this.transcribingSeqs.size > 0;
    if (keepGoing && !this.closed) this.schedulePoll(data.poll_after_ms || 1000);
    else if (keepGoing) this.schedulePoll(3000);
  }

  setStage(stage) {
    this.stage = stage;
    this.statusEl.textContent = "";
    if (!stage) return;
    const dots = el("span", "gp-dots");
    dots.setAttribute("aria-hidden", "true");
    dots.innerHTML = "<span></span><span></span><span></span>";
    this.statusEl.append(dots, el("span", "", STAGE_TEXT[stage] ?? ""));
  }

  showBanner(text) {
    this.banner.textContent = text;
    this.banner.hidden = false;
  }

  hideBanner() {
    this.banner.hidden = true;
  }

  scrollToEnd() {
    requestAnimationFrame(() => {
      this.body.scrollTop = this.body.scrollHeight;
    });
  }

  /* ----------------------------------------------------- audio playback */

  playButton(messageId) {
    const btn = el("button", "gp-play");
    btn.type = "button";
    btn.innerHTML = `${icon("play")}<span>Listen</span>`;
    btn.setAttribute("aria-label", "Play this reply aloud");
    btn.addEventListener("click", () => this.togglePlayback(messageId, btn));
    return btn;
  }

  async togglePlayback(messageId, btn) {
    const { audio } = this;
    if (audio.playingId === messageId && audio.player && !audio.player.paused) {
      audio.player.pause();
      return;
    }
    this.stopAudio();
    let url = audio.cache.get(messageId);
    if (!url) {
      btn.setAttribute("aria-busy", "true");
      btn.querySelector("span").textContent = "Loading...";
      try {
        url = URL.createObjectURL(await supportApi.audio(this.session, messageId));
        audio.cache.set(messageId, url);
      } catch (err) {
        btn.removeAttribute("aria-busy");
        btn.querySelector("span").textContent = "Audio unavailable";
        return;
      }
      btn.removeAttribute("aria-busy");
    }
    const player = new Audio(url);
    audio.player = player;
    audio.playingId = messageId;
    const setLabel = playing => {
      btn.innerHTML = `${icon(playing ? "pause" : "play")}<span>${playing ? "Pause" : "Listen"}</span>`;
      btn.setAttribute("aria-label", playing ? "Pause audio" : "Play this reply aloud");
    };
    player.addEventListener("play", () => setLabel(true));
    player.addEventListener("pause", () => setLabel(false));
    player.addEventListener("ended", () => setLabel(false));
    player.play().catch(() => setLabel(false));
  }

  stopAudio() {
    if (this.audio.player) {
      this.audio.player.pause();
      this.audio.player = null;
      this.audio.playingId = null;
    }
  }

  /* ---------------------------------------------------- voice recording */

  async startRecording() {
    if (this.rec) return;
    const mime = pickRecordingMime();
    if (mime === null || !navigator.mediaDevices?.getUserMedia) {
      this.showBanner("Voice notes aren't supported in this browser. Please type your message.");
      return;
    }
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      const blocked = err?.name === "NotAllowedError" || err?.name === "SecurityError";
      this.showBanner(
        blocked
          ? "Microphone access is blocked. Allow it in your browser's site settings, or type your message instead."
          : err?.name === "NotFoundError"
            ? "No microphone was found. Please type your message instead."
            : "Couldn't start recording. Please type your message instead.",
      );
      return;
    }
    this.hideBanner();
    const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    const chunks = [];
    const startedAt = Date.now();
    const maxMs = (this.config?.voice_max_seconds ?? 60) * 1000;
    this.rec = { recorder, stream, chunks, startedAt, cancelled: false, timer: null };

    recorder.addEventListener("dataavailable", e => e.data.size && chunks.push(e.data));
    recorder.addEventListener("stop", () => this.onRecordingStopped());
    recorder.start(250);

    this.form.hidden = true;
    this.counter.hidden = true;
    this.recorderEl.hidden = false;
    this.recorderEl.innerHTML = `
      <button type="button" class="gp-round-btn gp-round-btn--ghost" data-rec="cancel" aria-label="Cancel recording">${icon("trash")}</button>
      <div class="gp-recorder__live" role="status"><span class="gp-rec-dot" aria-hidden="true"></span><span class="gp-rec-time">0:00</span><span class="gp-recorder__hint">Recording</span></div>
      <button type="button" class="gp-round-btn gp-round-btn--stop" data-rec="stop" aria-label="Stop recording">${icon("stop")}</button>`;
    this.recorderEl.querySelector('[data-rec="cancel"]').addEventListener("click", () => this.cancelRecording());
    this.recorderEl.querySelector('[data-rec="stop"]').addEventListener("click", () => this.stopRecording());
    this.recorderEl.querySelector('[data-rec="stop"]').focus();

    const timeEl = this.recorderEl.querySelector(".gp-rec-time");
    this.rec.timer = setInterval(() => {
      const elapsed = Date.now() - startedAt;
      const s = Math.floor(elapsed / 1000);
      timeEl.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
      if (elapsed >= maxMs) this.stopRecording();
    }, 250);
  }

  stopRecording() {
    if (this.rec?.recorder.state === "recording") this.rec.recorder.stop();
  }

  cancelRecording() {
    if (!this.rec) return;
    this.rec.cancelled = true;
    if (this.rec.recorder.state === "recording") this.rec.recorder.stop();
    else this.resetRecorder();
  }

  onRecordingStopped() {
    const rec = this.rec;
    clearInterval(rec.timer);
    rec.stream.getTracks().forEach(track => track.stop());
    if (rec.cancelled) return this.resetRecorder();

    const durationMs = Date.now() - rec.startedAt;
    const type = rec.recorder.mimeType || rec.chunks[0]?.type || "audio/webm";
    const blob = new Blob(rec.chunks, { type });
    if (durationMs < 1000 || blob.size < 1000) {
      this.resetRecorder();
      this.showBanner("That recording was too short. Hold on a little longer and try again.");
      return;
    }

    // Review before sending.
    const url = URL.createObjectURL(blob);
    this.recorderEl.innerHTML = `
      <button type="button" class="gp-round-btn gp-round-btn--ghost" data-rec="discard" aria-label="Discard voice note">${icon("trash")}</button>
      <audio controls preload="metadata"></audio>
      <button type="button" class="gp-round-btn gp-round-btn--send" data-rec="send" aria-label="Send voice note">${icon("send")}</button>`;
    this.recorderEl.querySelector("audio").src = url;
    this.recorderEl.querySelector('[data-rec="discard"]').addEventListener("click", () => {
      URL.revokeObjectURL(url);
      this.resetRecorder();
    });
    this.recorderEl.querySelector('[data-rec="send"]').addEventListener("click", () => {
      URL.revokeObjectURL(url);
      this.resetRecorder();
      this.sendVoice(blob, type);
    });
    this.recorderEl.querySelector('[data-rec="send"]').focus();
  }

  resetRecorder() {
    if (this.rec) clearInterval(this.rec.timer);
    this.rec = null;
    this.recorderEl.hidden = true;
    this.recorderEl.textContent = "";
    this.form.hidden = false;
    this.input.focus();
  }

  async sendVoice(blob, mime, clientId = newClientId(), existing = null) {
    this.suggestions.hidden = true;
    const li = existing ?? this.renderPending({ text: "Uploading...", kind: "voice", clientId });
    const pendingText = li.querySelector(".gp-voice-pending");
    if (pendingText) pendingText.textContent = "Uploading...";
    const meta = this.setMeta(li, "Uploading 0%");
    const bar = el("div", "gp-progress");
    bar.innerHTML = "<span></span>";
    li.querySelector(".gp-bubble").appendChild(bar);
    this.inFlight += 1;
    try {
      await this.ensureSession();
      const res = await supportApi.sendVoice(this.session, clientId, blob, mime, fraction => {
        const pct = Math.round(fraction * 100);
        bar.firstChild.style.width = `${pct}%`;
        meta.firstChild.textContent = `Uploading ${pct}%`;
      });
      bar.remove();
      this.bind(li, res.message);
      this.setStage("transcribing");
      this.schedulePoll(1000);
    } catch (err) {
      bar.remove();
      if (err.status === 404 && !existing) {
        clearSession();
        this.session = null;
        return this.sendVoice(blob, mime, clientId, li);
      }
      const retryable = !err.status || err.status >= 500 || err.status === 429;
      if (retryable) this.markFailed(li, err.message, () => this.sendVoice(blob, mime, clientId, li));
      else this.setMeta(li, err.message, true);
    } finally {
      this.inFlight -= 1;
    }
  }

  /* --------------------------------------------------------- escalation */

  openEscalation() {
    const user = (() => {
      try { return JSON.parse(localStorage.getItem("gpron_user")); } catch { return null; }
    })();
    this.sheet.hidden = false;
    this.sheet.innerHTML = `
      <div class="gp-sheet__head">
        <button type="button" class="gp-chat__icon-btn gp-icon-dark" data-sheet="back" aria-label="Back to chat">${icon("back")}</button>
        <h3 id="gp-sheet-title">Talk to a person</h3>
      </div>
      <div class="gp-sheet__body">
        <p>Leave your details and the Gpron team will contact you. Requests are reviewed during opening hours (Mon to Fri 8am to 6pm, Sat 9am to 4pm, Sun 10am to 2pm).</p>
        <form novalidate>
          <div class="gp-field">
            <label for="gp-esc-cat">What is it about?</label>
            <select id="gp-esc-cat" name="category">
              <option value="general">General question</option>
              <option value="order_issue">A problem with my order</option>
              <option value="complaint">Complaint</option>
              <option value="pricing">Pricing</option>
              <option value="pickup_delivery">Pickup or delivery</option>
              <option value="payment">Payment</option>
            </select>
          </div>
          <div class="gp-field">
            <label for="gp-esc-msg">How can we help?</label>
            <textarea id="gp-esc-msg" name="message" maxlength="1000" required placeholder="Include your tracking ID if it's about an order"></textarea>
          </div>
          <div class="gp-field">
            <label for="gp-esc-name">Your name</label>
            <input id="gp-esc-name" name="contact_name" maxlength="100" autocomplete="name" required />
          </div>
          <div class="gp-row">
            <div class="gp-field">
              <label for="gp-esc-phone">Phone</label>
              <input id="gp-esc-phone" name="contact_phone" type="tel" maxlength="30" autocomplete="tel" />
            </div>
            <div class="gp-field">
              <label for="gp-esc-email">Email</label>
              <input id="gp-esc-email" name="contact_email" type="email" maxlength="255" autocomplete="email" />
            </div>
          </div>
          <label class="gp-check"><input type="checkbox" name="include_chat_excerpt" checked /> Share my last few chat messages so I don't have to repeat myself</label>
          <p class="gp-form-error" role="alert" hidden></p>
          <button type="submit" class="gp-primary">Send request</button>
        </form>
      </div>`;
    this.sheet.setAttribute("role", "region");
    this.sheet.setAttribute("aria-labelledby", "gp-sheet-title");
    const form = this.sheet.querySelector("form");
    if (user) {
      form.contact_name.value = user.name || "";
      form.contact_email.value = user.email || "";
    }
    this.sheet.querySelector('[data-sheet="back"]').addEventListener("click", () => this.closeEscalation());
    form.addEventListener("submit", e => {
      e.preventDefault();
      this.submitEscalation(form);
    });
    form.category.focus();
  }

  closeEscalation() {
    this.sheet.hidden = true;
    this.sheet.textContent = "";
    this.input.focus();
  }

  async submitEscalation(form) {
    const errorEl = form.querySelector(".gp-form-error");
    const button = form.querySelector(".gp-primary");
    const payload = {
      category: form.category.value,
      message: form.message.value.trim(),
      contact_name: form.contact_name.value.trim(),
      contact_phone: form.contact_phone.value.trim() || null,
      contact_email: form.contact_email.value.trim() || null,
      include_chat_excerpt: form.include_chat_excerpt.checked,
    };
    const problem =
      payload.message.length < 3 ? "Tell us a little about what you need." :
      payload.contact_name.length < 2 ? "Please add your name." :
      !payload.contact_phone && !payload.contact_email ? "Add a phone number or email so we can reach you." :
      "";
    if (problem) {
      errorEl.textContent = problem;
      errorEl.hidden = false;
      return;
    }
    errorEl.hidden = true;
    button.disabled = true;
    button.textContent = "Sending...";
    try {
      await this.ensureSession();
      const ticket = await supportApi.escalate(this.session, payload);
      const body = this.sheet.querySelector(".gp-sheet__body");
      body.innerHTML = `
        <div class="gp-success" role="status">
          <strong>Request recorded</strong>
          <span>Your reference</span><br />
          <span class="gp-ref"></span>
          <p>Our team reviews requests during opening hours and will contact you using the details you gave.</p>
          <button type="button" class="gp-primary">Back to chat</button>
        </div>`;
      body.querySelector(".gp-ref").textContent = ticket.reference;
      body.querySelector(".gp-primary").addEventListener("click", () => this.closeEscalation());
      body.querySelector(".gp-primary").focus();
      this.poll();
    } catch (err) {
      errorEl.textContent = err instanceof SupportApiError ? err.message : "Couldn't send your request. Please try again.";
      errorEl.hidden = false;
      button.disabled = false;
      button.textContent = "Send request";
    }
  }
}

let instance = null;

export function openSupportWidget(launcher) {
  instance ??= new SupportWidget(launcher);
  instance.show();
}

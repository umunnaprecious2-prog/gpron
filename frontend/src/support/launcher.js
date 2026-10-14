// Support chat launcher. Kept tiny on purpose: the chat panel, its CSS and
// all recording code load only when a visitor first opens the chat.
import "./launcher.css";

const OPEN_KEY = "gpron_support_open";
const CHAT_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/><path d="M8.5 11.5h.01M12 11.5h.01M15.5 11.5h.01"/></svg>`;

let widgetPromise = null;

function loadWidget() {
  widgetPromise ??= import("./widget.js");
  return widgetPromise;
}

function readOpenFlag() {
  try { return sessionStorage.getItem(OPEN_KEY) === "1"; } catch { return false; }
}

function mountLauncher() {
  if (document.querySelector(".gp-chat-launcher")) return;
  const button = document.createElement("button");
  button.type = "button";
  button.className = "gp-chat-launcher";
  button.setAttribute("aria-label", "Open Gpron customer support chat");
  button.setAttribute("aria-haspopup", "dialog");
  button.setAttribute("aria-expanded", "false");
  button.innerHTML = `${CHAT_ICON}<span class="gp-unread" hidden></span>`;
  document.body.appendChild(button);
  document.body.classList.add("gp-has-chat");

  const open = async () => {
    button.disabled = true;
    try {
      const { openSupportWidget } = await loadWidget();
      openSupportWidget(button);
    } catch {
      // Chunk failed to load (offline / deploy in progress); let them retry.
      widgetPromise = null;
      button.title = "Chat couldn't load. Check your connection and try again.";
    } finally {
      button.disabled = false;
    }
  };
  button.addEventListener("click", open);

  // Keep the chat open across page navigation within the tab.
  if (readOpenFlag()) open();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mountLauncher);
} else {
  mountLauncher();
}

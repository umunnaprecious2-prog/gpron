// In Docker Compose, the backend is reachable at http://backend:8000 (service
// name on the compose network), not localhost. VITE_PROXY_TARGET lets the
// compose file override the dev-proxy target without touching this file.
const proxyTarget = process.env.VITE_PROXY_TARGET || "http://localhost:8000";

export default {
  server: {
    port: 5174,
    proxy: {
      "/auth": proxyTarget,
      "/orders": proxyTarget,
      // Only proxy /track when it's an API call, not /track.html
      "/track/": proxyTarget,
      "/newsletter": proxyTarget,
    },
  },
  build: {
    rollupOptions: {
      input: {
        main: "index.html",
        login: "login.html",
        register: "register.html",
        dashboard: "dashboard.html",
        manager: "manager.html",
        track: "track.html",
      },
    },
  },
};

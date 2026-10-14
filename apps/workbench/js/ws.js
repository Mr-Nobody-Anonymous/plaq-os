/**
 * Plaq-OS Real-time WebSocket Client
 */
class PlaqWebSocket {
  constructor(url) {
    this.url = url || `ws://${window.location.host}/ws/stream`;
    this.socket = null;
    this.listeners = new Map();
    this.reconnectTimer = null;
    this.connected = false;
  }

  connect() {
    try {
      this.socket = new WebSocket(this.url);

      this.socket.onopen = () => {
        this.connected = true;
        this.emit("status", { connected: true });
        console.log("[Plaq-WS] Connected to Plaq-OS WebSocket Stream");
      };

      this.socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          this.emit("event", payload);
          if (payload.event_type) {
            this.emit(payload.event_type, payload);
          }
        } catch (err) {
          console.warn("[Plaq-WS] Failed to parse message:", event.data);
        }
      };

      this.socket.onclose = () => {
        this.connected = false;
        this.emit("status", { connected: false });
        this.scheduleReconnect();
      };

      this.socket.onerror = (err) => {
        console.error("[Plaq-WS] WebSocket error:", err);
        if (this.socket) {
          this.socket.close();
        }
      };
    } catch (exc) {
      console.warn("[Plaq-WS] Connection error:", exc);
      this.scheduleReconnect();
    }
  }

  scheduleReconnect() {
    if (this.reconnectTimer) return;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      console.log("[Plaq-WS] Attempting reconnection...");
      this.connect();
    }, 3000);
  }

  send(data) {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(typeof data === "string" ? data : JSON.stringify(data));
    }
  }

  on(event, handler) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event).add(handler);
  }

  off(event, handler) {
    if (this.listeners.has(event)) {
      this.listeners.get(event).delete(handler);
    }
  }

  emit(event, data) {
    if (this.listeners.has(event)) {
      for (const handler of this.listeners.get(event)) {
        try {
          handler(data);
        } catch (e) {
          console.error("[Plaq-WS] Listener error:", e);
        }
      }
    }
  }
}

// Export singleton
window.plaqWs = new PlaqWebSocket();

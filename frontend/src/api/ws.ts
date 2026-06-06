import type { WsIncoming, WsOutgoing } from "../types";

const WS_BASE = import.meta.env.VITE_WS_URL ?? "ws://localhost:8000";

export class ChatSocket {
  private ws: WebSocket | null = null;
  private sessionId: string;
  private onMessage: (msg: WsIncoming) => void;
  private onOpen: () => void;
  private onClose: () => void;

  constructor(
    sessionId: string,
    onMessage: (msg: WsIncoming) => void,
    onOpen: () => void,
    onClose: () => void
  ) {
    this.sessionId = sessionId;
    this.onMessage = onMessage;
    this.onOpen = onOpen;
    this.onClose = onClose;
  }

  connect() {
    this.ws = new WebSocket(`${WS_BASE}/ws/${this.sessionId}`);

    this.ws.onopen = () => this.onOpen();

    this.ws.onmessage = (event) => {
      try {
        const msg: WsIncoming = JSON.parse(event.data);
        if (msg.type === "ping") {
          this.send({ type: "pong" });
          return;
        }
        this.onMessage(msg);
      } catch {}
    };

    this.ws.onclose = () => this.onClose();
    this.ws.onerror = () => this.ws?.close();
  }

  send(msg: WsOutgoing) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  disconnect() {
    this.ws?.close();
    this.ws = null;
  }
}

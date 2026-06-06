export interface Citation {
  doc_id: string;
  page: number;
  section?: string;
}

export interface Message {
  message_id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
  citations?: Citation[];
  streaming?: boolean;
}

export interface DocEntry {
  docId: string;
  name: string;
  status: DocStatus;
}

export type WsIncoming =
  | { type: "status"; doc_id: string; state: "processing" | "ready" | "error"; error?: string }
  | { type: "step"; text: string }
  | { type: "token"; text: string }
  | { type: "done"; message_id: string; citations: Citation[] }
  | { type: "error"; message: string }
  | { type: "ping" };

export type WsOutgoing =
  | { type: "user_message"; content: string }
  | { type: "cancel" }
  | { type: "pong" };

export type DocStatus = "idle" | "processing" | "ready" | "error";

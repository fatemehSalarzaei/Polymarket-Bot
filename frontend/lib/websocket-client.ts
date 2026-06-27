import type { DashboardWsEvent } from "@/types/websocket";

const wsUrl = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws/dashboard";

export type DashboardWebSocketHandlers = {
  onEvent: (event: DashboardWsEvent) => void;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (message: string) => void;
};

export function connectDashboardWebSocket(handlers: DashboardWebSocketHandlers): () => void {
  let closedByClient = false;
  let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
  let reconnectDelay = 1000;
  let socket: WebSocket | undefined;

  const connect = () => {
    try {
      socket = new WebSocket(wsUrl);
    } catch (err) {
      handlers.onError?.(err instanceof Error ? err.message : "WebSocket connection failed");
      scheduleReconnect();
      return;
    }

    socket.onopen = () => {
      reconnectDelay = 1000;
      handlers.onOpen?.();
    };

    socket.onmessage = (message) => {
      try {
        handlers.onEvent(JSON.parse(message.data) as DashboardWsEvent);
      } catch {
        handlers.onError?.("Received an unreadable dashboard update");
      }
    };

    socket.onerror = () => {
      handlers.onError?.("Dashboard WebSocket error");
    };

    socket.onclose = () => {
      handlers.onClose?.();
      if (!closedByClient) {
        scheduleReconnect();
      }
    };
  };

  const scheduleReconnect = () => {
    reconnectTimer = setTimeout(connect, reconnectDelay);
    reconnectDelay = Math.min(reconnectDelay * 2, 15000);
  };

  connect();

  return () => {
    closedByClient = true;
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
    }
    socket?.close();
  };
}

export function getDashboardWsUrl() {
  return wsUrl;
}


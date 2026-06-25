import type { AgentEnvelope } from "../types/quest";

export const WEBSOCKET_RESPONSE_TIMEOUT_MS = 120_000;

export function sendAgentRequest(
  websocketUrl: string,
  request: Record<string, unknown>,
): Promise<AgentEnvelope> {
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(websocketUrl);
    const timeout = window.setTimeout(() => {
      socket.close();
      reject(new Error("WebSocket response timed out"));
    }, WEBSOCKET_RESPONSE_TIMEOUT_MS);

    socket.addEventListener("open", () => {
      socket.send(JSON.stringify(request));
    });

    socket.addEventListener("message", (event) => {
      window.clearTimeout(timeout);
      socket.close();
      try {
        resolve(JSON.parse(event.data) as AgentEnvelope);
      } catch (error) {
        reject(error);
      }
    });

    socket.addEventListener("error", () => {
      window.clearTimeout(timeout);
      reject(new Error("WebSocket connection failed"));
    });
  });
}


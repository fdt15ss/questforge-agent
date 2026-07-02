import { describe, expect, it } from "vitest";
import { WEBSOCKET_RESPONSE_TIMEOUT_MS } from "./wsClient";

describe("websocket client configuration", () => {
  it("waits up to 180 seconds for slow quest generation responses", () => {
    expect(WEBSOCKET_RESPONSE_TIMEOUT_MS).toBe(180_000);
  });
});

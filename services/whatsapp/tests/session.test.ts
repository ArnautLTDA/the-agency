import { describe, it, expect } from "vitest";
import { WhatsAppSessionManager } from "../src/session.js";

describe("WhatsApp Session Manager (TC-105, TC-106, TC-174, TC-175)", () => {
  it("initializes with DISCONNECTED state and tracks state transitions (TC-105)", () => {
    const manager = new WhatsAppSessionManager();
    expect(manager.getState()).toBe("DISCONNECTED");

    manager.setState("CONNECTING");
    expect(manager.getState()).toBe("CONNECTING");

    manager.setState("QR_READY", "mock_qr_data_12345");
    expect(manager.getState()).toBe("QR_READY");
    expect(manager.getRawQr()).toBe("mock_qr_data_12345");

    manager.setState("CONNECTED", null, "5511999998888@s.whatsapp.net");
    expect(manager.getState()).toBe("CONNECTED");
    expect(manager.getStatus().userJid).toBe("5511999998888@s.whatsapp.net");
    expect(manager.getStatus().hasQr).toBe(false);
  });

  it("generates QR code data URL when QR is ready (TC-106)", async () => {
    const manager = new WhatsAppSessionManager();
    manager.setState("QR_READY", "2@dummy_qr_matrix");

    const dataUrl = await manager.getQrCodeDataUrl();
    expect(dataUrl).not.toBeNull();
    expect(dataUrl).toContain("data:image/png;base64,");
  });

  it("handles exponential backoff up to 5 reconnect attempts (TC-174, TC-175)", () => {
    const manager = new WhatsAppSessionManager(5);

    // Attempt 1: 2000ms
    const r1 = manager.handleDisconnection(500);
    expect(r1.canReconnect).toBe(true);
    expect(r1.delayMs).toBe(2000);

    // Attempt 2: 4000ms
    const r2 = manager.handleDisconnection(500);
    expect(r2.canReconnect).toBe(true);
    expect(r2.delayMs).toBe(4000);

    // Attempt 3: 8000ms
    const r3 = manager.handleDisconnection(500);
    expect(r3.canReconnect).toBe(true);
    expect(r3.delayMs).toBe(8000);

    // Attempt 4: 16000ms
    const r4 = manager.handleDisconnection(500);
    expect(r4.canReconnect).toBe(true);
    expect(r4.delayMs).toBe(16000);

    // Attempt 5: 32000ms
    const r5 = manager.handleDisconnection(500);
    expect(r5.canReconnect).toBe(true);
    expect(r5.delayMs).toBe(32000);

    // Attempt 6: Max reached -> canReconnect is false
    const r6 = manager.handleDisconnection(500);
    expect(r6.canReconnect).toBe(false);
    expect(manager.getState()).toBe("DISCONNECTED");
  });

  it("transitions to LOGGED_OUT without reconnect on 401 or 403 status", () => {
    const manager = new WhatsAppSessionManager();
    const result = manager.handleDisconnection(401);

    expect(result.canReconnect).toBe(false);
    expect(manager.getState()).toBe("LOGGED_OUT");
  });
});

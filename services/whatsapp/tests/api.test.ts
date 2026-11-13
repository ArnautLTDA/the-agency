import { describe, it, expect, vi } from "vitest";
import request from "supertest";
import { createApp } from "../src/app.js";
import { WhatsAppSessionManager } from "../src/session.js";
import { WhatsAppServiceHandler } from "../src/mcp_tools.js";

describe("WhatsApp Gateway API & MCP Tools (:3005)", () => {
  const sessionManager = new WhatsAppSessionManager();
  const mockServiceHandler: WhatsAppServiceHandler = {
    sendMessage: vi.fn().mockResolvedValue({ id: "msg_123", status: "sent" }),
    checkNumbers: vi
      .fn()
      .mockResolvedValue([
        {
          phone: "5511999998888",
          exists: true,
          jid: "5511999998888@s.whatsapp.net",
        },
      ]),
    sessionManager,
  };

  const app = createApp(sessionManager, mockServiceHandler);
  const validKey = "agency_dev_secret_key_12345";

  it("exposes public health endpoint without authentication", async () => {
    const res = await request(app).get("/api/v1/health");
    expect(res.status).toBe(200);
    expect(res.body.status).toBe("healthy");
    expect(res.body.service).toBe("whatsapp-gateway");
    expect(res.body.port).toBe(3005);
  });

  it("exposes public session status without authentication", async () => {
    const res = await request(app).get("/api/v1/session/status");
    expect(res.status).toBe(200);
    expect(res.body.state).toBe("DISCONNECTED");
  });

  it("returns 404 for QR endpoint when QR is not ready", async () => {
    const res = await request(app).get("/api/v1/session/qr");
    expect(res.status).toBe(404);
    expect(res.body.error).toBe("qr_not_ready");
  });

  it("returns QR code data URL when QR is ready", async () => {
    sessionManager.setState("QR_READY", "mock_qr_matrix_data");
    const res = await request(app).get("/api/v1/session/qr");
    expect(res.status).toBe(200);
    expect(res.body.qr).toContain("data:image/png;base64,");
  });

  it("rejects protected routes without X-Agency-Key with 401", async () => {
    const res = await request(app).post("/api/v1/session/logout");
    expect(res.status).toBe(401);
    expect(res.body.error).toBe("missing_or_invalid_agency_key");
  });

  it("rejects protected routes with invalid X-Agency-Key with 401", async () => {
    const res = await request(app)
      .post("/api/v1/session/logout")
      .set("X-Agency-Key", "wrong-key");
    expect(res.status).toBe(401);
    expect(res.body.error).toBe("missing_or_invalid_agency_key");
  });

  it("allows protected route with valid X-Agency-Key", async () => {
    const res = await request(app)
      .post("/api/v1/session/logout")
      .set("X-Agency-Key", validKey);
    expect(res.status).toBe(200);
    expect(res.body.success).toBe(true);
    expect(res.body.state).toBe("LOGGED_OUT");
  });

  it("lists registered MCP tools", async () => {
    const res = await request(app)
      .get("/api/v1/mcp/tools")
      .set("X-Agency-Key", validKey);
    expect(res.status).toBe(200);
    expect(res.body.tools).toBeInstanceOf(Array);
    const names = res.body.tools.map((t: any) => t.name);
    expect(names).toContain("send_whatsapp_message");
    expect(names).toContain("check_whatsapp_numbers");
    expect(names).toContain("get_whatsapp_session_status");
  });

  it("executes send_whatsapp_message via MCP call", async () => {
    const res = await request(app)
      .post("/api/v1/mcp/call")
      .set("X-Agency-Key", validKey)
      .send({
        name: "send_whatsapp_message",
        arguments: { to: "5511999998888", text: "Olá cliente!" },
      });

    expect(res.status).toBe(200);
    expect(res.body.result.success).toBe(true);
    expect(mockServiceHandler.sendMessage).toHaveBeenCalledWith(
      "5511999998888",
      "Olá cliente!",
    );
  });

  it("executes check_whatsapp_numbers via MCP call", async () => {
    const res = await request(app)
      .post("/api/v1/mcp/call")
      .set("X-Agency-Key", validKey)
      .send({
        name: "check_whatsapp_numbers",
        arguments: { phones: ["5511999998888"] },
      });

    expect(res.status).toBe(200);
    expect(res.body.result.results[0].exists).toBe(true);
  });
});

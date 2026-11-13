import express, { Express, Request, Response } from "express";
import cors from "cors";
import { agencyKeyMiddleware } from "./auth.js";
import { WhatsAppSessionManager } from "./session.js";
import { WhatsAppMCPHandler, WhatsAppServiceHandler } from "./mcp_tools.js";

export function createApp(
  sessionManager: WhatsAppSessionManager = new WhatsAppSessionManager(),
  serviceHandler?: WhatsAppServiceHandler,
): Express {
  const app = express();
  app.use(cors());
  app.use(express.json());

  // Apply X-Agency-Key auth middleware
  app.use(agencyKeyMiddleware);

  const defaultHandler: WhatsAppServiceHandler = serviceHandler || {
    sendMessage: async (to, text) => ({
      id: "mock_id",
      to,
      text,
      status: "sent",
    }),
    sessionManager,
  };
  const mcpHandler = new WhatsAppMCPHandler(defaultHandler);

  // Healthcheck endpoints (Exempt from auth)
  app.get(["/health", "/api/v1/health"], (req: Request, res: Response) => {
    res.json({
      status: "healthy",
      service: "whatsapp-gateway",
      port: 3005,
    });
  });

  // Session endpoints (Exempt from auth)
  app.get("/api/v1/session/status", (req: Request, res: Response) => {
    res.json(sessionManager.getStatus());
  });

  app.get("/api/v1/session/qr", async (req: Request, res: Response) => {
    const qrDataUrl = await sessionManager.getQrCodeDataUrl();
    if (!qrDataUrl) {
      res
        .status(404)
        .json({ error: "qr_not_ready", state: sessionManager.getState() });
      return;
    }
    res.json({ qr: qrDataUrl, raw: sessionManager.getRawQr() });
  });

  // Protected endpoints (Require X-Agency-Key)
  app.post("/api/v1/session/logout", (req: Request, res: Response) => {
    sessionManager.setState("LOGGED_OUT");
    res.json({ success: true, state: "LOGGED_OUT" });
  });

  // MCP tool call HTTP bridge
  app.get("/api/v1/mcp/tools", (req: Request, res: Response) => {
    res.json({ tools: mcpHandler.getTools() });
  });

  app.post("/api/v1/mcp/call", async (req: Request, res: Response) => {
    const { name, arguments: args } = req.body;
    if (!name) {
      res.status(400).json({ error: "tool name is required" });
      return;
    }

    try {
      const result = await mcpHandler.executeTool(name, args || {});
      res.json({ result });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  return app;
}

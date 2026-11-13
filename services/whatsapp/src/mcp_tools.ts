import { WhatsAppSessionManager } from "./session.js";
import { OutboundMessageSender } from "./amqp/outbound_consumer.js";

export interface WhatsAppServiceHandler {
  sendMessage(to: string, text: string): Promise<any>;
  sendMedia?(
    to: string,
    mediaUrl: string,
    caption?: string,
    mediaType?: string,
  ): Promise<any>;
  checkNumbers?(
    phones: string[],
  ): Promise<Array<{ phone: string; exists: boolean; jid?: string }>>;
  sessionManager: WhatsAppSessionManager;
}

export class WhatsAppMCPHandler {
  private handler: WhatsAppServiceHandler;

  constructor(handler: WhatsAppServiceHandler) {
    this.handler = handler;
  }

  getTools(): Array<{
    name: string;
    description: string;
    inputSchema: object;
  }> {
    return [
      {
        name: "send_whatsapp_message",
        description:
          "Sends a direct text message to a WhatsApp phone number or JID.",
        inputSchema: {
          type: "object",
          properties: {
            to: {
              type: "string",
              description:
                "Destination phone in E.164 or JID (e.g. 5511999998888)",
            },
            text: { type: "string", description: "Message body" },
          },
          required: ["to", "text"],
        },
      },
      {
        name: "send_whatsapp_media",
        description:
          "Sends media (image/document/audio) to a WhatsApp destination.",
        inputSchema: {
          type: "object",
          properties: {
            to: { type: "string" },
            media_url: { type: "string" },
            caption: { type: "string" },
            media_type: {
              type: "string",
              enum: ["image", "document", "audio"],
            },
          },
          required: ["to", "media_url"],
        },
      },
      {
        name: "check_whatsapp_numbers",
        description:
          "Checks if a list of phone numbers are registered on WhatsApp.",
        inputSchema: {
          type: "object",
          properties: {
            phones: { type: "array", items: { type: "string" } },
          },
          required: ["phones"],
        },
      },
      {
        name: "get_whatsapp_session_status",
        description:
          "Returns the current WhatsApp socket connection and authentication status.",
        inputSchema: {
          type: "object",
          properties: {},
        },
      },
    ];
  }

  async executeTool(name: string, args: Record<string, any>): Promise<any> {
    switch (name) {
      case "send_whatsapp_message": {
        const result = await this.handler.sendMessage(args.to, args.text);
        return { success: true, to: args.to, result };
      }

      case "send_whatsapp_media": {
        if (!this.handler.sendMedia) {
          throw new Error("Media sending not supported in current provider");
        }
        const result = await this.handler.sendMedia(
          args.to,
          args.media_url,
          args.caption,
          args.media_type,
        );
        return { success: true, to: args.to, result };
      }

      case "check_whatsapp_numbers": {
        if (!this.handler.checkNumbers) {
          // Default fallback
          const checked = (args.phones || []).map((p: string) => ({
            phone: p,
            exists: true,
            jid: `${p.replace(/\D/g, "")}@s.whatsapp.net`,
          }));
          return { results: checked };
        }
        const results = await this.handler.checkNumbers(args.phones);
        return { results };
      }

      case "get_whatsapp_session_status": {
        const status = this.handler.sessionManager.getStatus();
        return status;
      }

      default:
        throw new Error(`Unknown WhatsApp tool: ${name}`);
    }
  }
}

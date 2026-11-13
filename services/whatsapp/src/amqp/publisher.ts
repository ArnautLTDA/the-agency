import { Channel } from "amqplib";
import { AMQPMessageEnvelope } from "./envelope.js";

export class WhatsAppAMQPPublisher {
  private channel: Channel | null;
  private exchange: string;

  constructor(
    channel: Channel | null = null,
    exchange: string = "agency.topic",
  ) {
    this.channel = channel;
    this.exchange = exchange;
  }

  setChannel(channel: Channel): void {
    this.channel = channel;
  }

  /**
   * Publishes incoming raw message envelope to whatsapp.raw queue for Guardrail processing.
   */
  async publishRawMessage(
    senderJid: string,
    messageId: string,
    text?: string,
    audioBase64?: string,
    mediaType?: string,
    correlationId?: string,
  ): Promise<AMQPMessageEnvelope> {
    const envelope = new AMQPMessageEnvelope({
      correlation_id: correlationId,
      from_service: "whatsapp-gateway",
      to_service: "guardrail-gateway",
      payload: {
        sender_jid: senderJid,
        message_id: messageId,
        text: text || null,
        audio_base64: audioBase64 || null,
        media_type: mediaType || "text",
        received_at: new Date().toISOString(),
      },
    });

    if (this.channel) {
      const buffer = Buffer.from(envelope.toJSON());
      this.channel.publish(this.exchange, "whatsapp.raw", buffer, {
        contentType: "application/json",
        correlationId: envelope.correlation_id,
        messageId: envelope.message_id,
      });
    }

    return envelope;
  }
}

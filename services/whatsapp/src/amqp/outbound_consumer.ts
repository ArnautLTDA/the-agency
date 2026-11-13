import { Channel, ConsumeMessage } from "amqplib";
import { AMQPMessageEnvelope } from "./envelope.js";
import { Humanizer } from "../humanizer.js";

export interface OutboundMessageSender {
  sendMessage(toJid: string, text: string): Promise<any>;
  sendPresenceUpdate?(
    type: "composing" | "paused",
    toJid: string,
  ): Promise<any>;
  readMessages?(keys: any[]): Promise<any>;
}

export class WhatsAppOutboundConsumer {
  private channel: Channel | null;
  private sender: OutboundMessageSender;
  private humanizer: Humanizer;
  private isProcessing = false;

  constructor(
    sender: OutboundMessageSender,
    humanizer: Humanizer = new Humanizer(),
    channel: Channel | null = null,
  ) {
    this.sender = sender;
    this.humanizer = humanizer;
    this.channel = channel;
  }

  setChannel(channel: Channel): void {
    this.channel = channel;
  }

  /**
   * Processes a single outbound message applying humanizer and business hours constraints.
   */
  async processOutboundEnvelope(envelope: AMQPMessageEnvelope): Promise<{
    delivered: boolean;
    reason?: string;
    typingDurationMs?: number;
    delayMs?: number;
    scheduledFor?: string;
  }> {
    const payload = envelope.payload;
    const toJid = payload.to_jid || payload.phone || payload.to;
    const text = payload.text || payload.message;

    if (!toJid || !text) {
      return { delivered: false, reason: "missing_destination_or_text" };
    }

    // 1. Check business hours (TC-163, TC-164)
    const now = new Date();
    if (!this.humanizer.isWithinBusinessHours(now)) {
      const nextOpening = this.humanizer.getNextBusinessHoursOpening(now);
      return {
        delivered: false,
        reason: "outside_business_hours",
        scheduledFor: nextOpening.toISOString(),
      };
    }

    // 2. Calculate humanizer timings (TC-102, TC-103, TC-104)
    const typingDurationMs = this.humanizer.calculateTypingDurationMs(text);
    const typingDelayMs = this.humanizer.getRandomTypingDelayMs();

    // 3. Simulate human interactions
    if (this.sender.sendPresenceUpdate) {
      await this.sender.sendPresenceUpdate("composing", toJid);
    }

    // 4. Send actual message
    await this.sender.sendMessage(toJid, text);

    if (this.sender.sendPresenceUpdate) {
      await this.sender.sendPresenceUpdate("paused", toJid);
    }

    return {
      delivered: true,
      typingDurationMs,
      delayMs: typingDelayMs,
    };
  }

  /**
   * Handles raw AMQP message payload from channel.
   */
  async handleAmqpMessage(msg: ConsumeMessage | null): Promise<void> {
    if (!msg || !this.channel) return;

    try {
      const content = msg.content.toString("utf-8");
      const envelope = AMQPMessageEnvelope.fromJSON(content);
      const result = await this.processOutboundEnvelope(envelope);

      if (result.delivered) {
        this.channel.ack(msg);
      } else if (result.reason === "outside_business_hours") {
        // Re-queue or hold for business hours delivery
        this.channel.nack(msg, false, true);
      } else {
        // Unrecoverable data error -> reject to dead letter
        this.channel.nack(msg, false, false);
      }
    } catch (err) {
      this.channel.nack(msg, false, false);
    }
  }
}

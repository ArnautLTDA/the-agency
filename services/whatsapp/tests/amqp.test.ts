import { describe, it, expect, vi } from "vitest";
import {
  AMQPMessageEnvelope,
  PayloadTooLargeError,
  MAX_PAYLOAD_BYTES,
} from "../src/amqp/envelope.js";
import { WhatsAppAMQPPublisher } from "../src/amqp/publisher.js";
import {
  WhatsAppOutboundConsumer,
  OutboundMessageSender,
} from "../src/amqp/outbound_consumer.js";
import { Humanizer } from "../src/humanizer.js";

describe("WhatsApp AMQP Messaging (TC-171, TC-172, TC-173)", () => {
  it("serializes and deserializes AMQP envelope with correlation_id", () => {
    const envelope = new AMQPMessageEnvelope({
      correlation_id: "corr-1234",
      from_service: "whatsapp-gateway",
      to_service: "guardrail-gateway",
      payload: { text: "Olá", sender: "5511999998888" },
    });

    const jsonStr = envelope.toJSON();
    const restored = AMQPMessageEnvelope.fromJSON(jsonStr);

    expect(restored.correlation_id).toBe("corr-1234");
    expect(restored.from_service).toBe("whatsapp-gateway");
    expect(restored.to_service).toBe("guardrail-gateway");
    expect(restored.payload.text).toBe("Olá");
  });

  it("throws PayloadTooLargeError when payload exceeds 64 KB (TC-172)", () => {
    const largeString = "x".repeat(MAX_PAYLOAD_BYTES + 100);
    expect(() => {
      new AMQPMessageEnvelope({
        from_service: "whatsapp-gateway",
        to_service: "guardrail-gateway",
        payload: { bigData: largeString },
      });
    }).toThrow(PayloadTooLargeError);
  });

  it("publishes raw incoming message to whatsapp.raw exchange", async () => {
    const mockChannel = {
      publish: vi.fn().mockReturnValue(true),
    } as any;

    const publisher = new WhatsAppAMQPPublisher(mockChannel, "agency.topic");
    const envelope = await publisher.publishRawMessage(
      "5511999998888@s.whatsapp.net",
      "msg-001",
      "Gostaria de agendar um horário",
      undefined,
      "text",
      "corr-abc",
    );

    expect(envelope.from_service).toBe("whatsapp-gateway");
    expect(envelope.to_service).toBe("guardrail-gateway");
    expect(mockChannel.publish).toHaveBeenCalledWith(
      "agency.topic",
      "whatsapp.raw",
      expect.any(Buffer),
      expect.objectContaining({ correlationId: "corr-abc" }),
    );
  });

  it("processes outbound message within business hours simulating human presence", async () => {
    const mockSender: OutboundMessageSender = {
      sendMessage: vi.fn().mockResolvedValue({ status: "sent" }),
      sendPresenceUpdate: vi.fn().mockResolvedValue(true),
    };

    // Custom humanizer forced within business hours
    const humanizer = new Humanizer();
    vi.spyOn(humanizer, "isWithinBusinessHours").mockReturnValue(true);

    const consumer = new WhatsAppOutboundConsumer(mockSender, humanizer);
    const envelope = new AMQPMessageEnvelope({
      from_service: "engine-core",
      to_service: "whatsapp-gateway",
      payload: {
        to_jid: "5511999998888@s.whatsapp.net",
        text: "Seu agendamento foi confirmado para amanhã às 15h!",
      },
    });

    const result = await consumer.processOutboundEnvelope(envelope);

    expect(result.delivered).toBe(true);
    expect(mockSender.sendPresenceUpdate).toHaveBeenCalledWith(
      "composing",
      "5511999998888@s.whatsapp.net",
    );
    expect(mockSender.sendMessage).toHaveBeenCalledWith(
      "5511999998888@s.whatsapp.net",
      "Seu agendamento foi confirmado para amanhã às 15h!",
    );
  });

  it("holds outbound message when outside business hours", async () => {
    const mockSender: OutboundMessageSender = {
      sendMessage: vi.fn().mockResolvedValue({ status: "sent" }),
    };

    const humanizer = new Humanizer();
    vi.spyOn(humanizer, "isWithinBusinessHours").mockReturnValue(false);
    vi.spyOn(humanizer, "getNextBusinessHoursOpening").mockReturnValue(
      new Date("2026-11-16T11:30:00.000Z"),
    );

    const consumer = new WhatsAppOutboundConsumer(mockSender, humanizer);
    const envelope = new AMQPMessageEnvelope({
      from_service: "engine-core",
      to_service: "whatsapp-gateway",
      payload: {
        to_jid: "5511999998888@s.whatsapp.net",
        text: "Mensagem noturna",
      },
    });

    const result = await consumer.processOutboundEnvelope(envelope);

    expect(result.delivered).toBe(false);
    expect(result.reason).toBe("outside_business_hours");
    expect(result.scheduledFor).toBe("2026-11-16T11:30:00.000Z");
    expect(mockSender.sendMessage).not.toHaveBeenCalled();
  });

  it("handles raw amqp message ack and nack", async () => {
    const mockChannel = {
      ack: vi.fn(),
      nack: vi.fn(),
    } as any;

    const mockSender: OutboundMessageSender = {
      sendMessage: vi.fn().mockResolvedValue({ status: "sent" }),
    };

    const humanizer = new Humanizer();
    vi.spyOn(humanizer, "isWithinBusinessHours").mockReturnValue(true);

    const consumer = new WhatsAppOutboundConsumer(
      mockSender,
      humanizer,
      mockChannel,
    );

    const envelope = new AMQPMessageEnvelope({
      from_service: "engine-core",
      to_service: "whatsapp-gateway",
      payload: { to_jid: "5511999998888@s.whatsapp.net", text: "Olá" },
    });

    const validMsg = {
      content: Buffer.from(envelope.toJSON()),
    } as any;

    await consumer.handleAmqpMessage(validMsg);
    expect(mockChannel.ack).toHaveBeenCalledWith(validMsg);

    // Invalid message nacked without requeue
    const invalidMsg = { content: Buffer.from("invalid-json") } as any;
    await consumer.handleAmqpMessage(invalidMsg);
    expect(mockChannel.nack).toHaveBeenCalledWith(invalidMsg, false, false);
  });
});

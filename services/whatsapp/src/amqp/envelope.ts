import { v4 as uuidv4 } from "uuid";

export const MAX_PAYLOAD_BYTES = 65536; // 64 KB

export class PayloadTooLargeError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PayloadTooLargeError";
  }
}

export interface AMQPMessageEnvelopeData {
  message_id?: string;
  correlation_id?: string;
  from_service: string;
  to_service: string;
  timestamp?: string;
  payload: Record<string, any>;
}

export class AMQPMessageEnvelope {
  public readonly message_id: string;
  public readonly correlation_id: string;
  public readonly from_service: string;
  public readonly to_service: string;
  public readonly timestamp: string;
  public readonly payload: Record<string, any>;

  constructor(data: AMQPMessageEnvelopeData) {
    if (!data.from_service || !data.from_service.trim()) {
      throw new Error("from_service must not be empty");
    }
    if (!data.to_service || !data.to_service.trim()) {
      throw new Error("to_service must not be empty");
    }

    const payload = data.payload || {};
    const serializedPayload = Buffer.from(JSON.stringify(payload), "utf-8");
    if (serializedPayload.byteLength > MAX_PAYLOAD_BYTES) {
      throw new PayloadTooLargeError(
        `Payload size of ${serializedPayload.byteLength} bytes exceeds limit of ${MAX_PAYLOAD_BYTES} bytes.`,
      );
    }

    this.message_id = data.message_id || uuidv4();
    this.correlation_id = data.correlation_id || uuidv4();
    this.from_service = data.from_service.trim();
    this.to_service = data.to_service.trim();
    this.timestamp = data.timestamp || new Date().toISOString();
    this.payload = payload;
  }

  toJSON(): string {
    return JSON.stringify({
      message_id: this.message_id,
      correlation_id: this.correlation_id,
      from_service: this.from_service,
      to_service: this.to_service,
      timestamp: this.timestamp,
      payload: this.payload,
    });
  }

  static fromJSON(jsonStr: string): AMQPMessageEnvelope {
    const parsed = JSON.parse(jsonStr);
    return new AMQPMessageEnvelope(parsed);
  }
}

/**
 * Baileys WhatsApp Session Management (TC-105, TC-106, TC-174, TC-175).
 */

import { EventEmitter } from "events";
import qrcode from "qrcode";
import { config } from "./config.js";

export type SessionState =
  "DISCONNECTED" | "CONNECTING" | "QR_READY" | "CONNECTED" | "LOGGED_OUT";

export interface SessionStatus {
  state: SessionState;
  hasQr: boolean;
  userJid: string | null;
  reconnectAttempts: number;
}

export class WhatsAppSessionManager extends EventEmitter {
  private state: SessionState = "DISCONNECTED";
  private currentQrData: string | null = null;
  private userJid: string | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;

  constructor(maxReconnectAttempts: number = 5) {
    super();
    this.maxReconnectAttempts = maxReconnectAttempts;
  }

  getState(): SessionState {
    return this.state;
  }

  getStatus(): SessionStatus {
    return {
      state: this.state,
      hasQr: this.currentQrData !== null,
      userJid: this.userJid,
      reconnectAttempts: this.reconnectAttempts,
    };
  }

  async getQrCodeDataUrl(): Promise<string | null> {
    if (!this.currentQrData) return null;
    return await qrcode.toDataURL(this.currentQrData);
  }

  getRawQr(): string | null {
    return this.currentQrData;
  }

  /**
   * Internal state transition method.
   */
  setState(
    newState: SessionState,
    qrCode: string | null = null,
    jid: string | null = null,
  ): void {
    this.state = newState;
    this.currentQrData = qrCode;
    if (jid) this.userJid = jid;

    if (newState === "CONNECTED") {
      this.reconnectAttempts = 0;
      this.currentQrData = null;
    }

    this.emit("state_changed", this.getStatus());
  }

  /**
   * Handles connection disconnection and calculates backoff for auto-reconnection (TC-174, TC-175).
   */
  handleDisconnection(statusCode?: number): {
    canReconnect: boolean;
    delayMs: number;
  } {
    if (statusCode === 401 || statusCode === 403) {
      this.setState("LOGGED_OUT");
      return { canReconnect: false, delayMs: 0 };
    }

    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      this.setState("DISCONNECTED");
      return { canReconnect: false, delayMs: 0 };
    }

    this.reconnectAttempts += 1;
    this.setState("CONNECTING");

    // Exponential backoff: 2s, 4s, 8s, 16s, 32s
    const delayMs = Math.min(
      2000 * Math.pow(2, this.reconnectAttempts - 1),
      32000,
    );
    return { canReconnect: true, delayMs };
  }

  reset(): void {
    this.state = "DISCONNECTED";
    this.currentQrData = null;
    this.userJid = null;
    this.reconnectAttempts = 0;
  }
}

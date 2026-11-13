/**
 * WhatsApp Humanizer module simulating human messaging cadences (TC-101 to TC-104, TC-163, TC-164).
 */

export interface HumanizerConfig {
  minTypingDelayMs: number;
  maxTypingDelayMs: number;
  msPerCharacter: number;
  maxPresenceMs: number;
  minInterContactDelayMs: number;
  maxInterContactDelayMs: number;
  businessHoursStartHour: number;
  businessHoursStartMinute: number;
  businessHoursEndHour: number;
  businessHoursEndMinute: number;
}

export const defaultHumanizerConfig: HumanizerConfig = {
  minTypingDelayMs: 3000,
  maxTypingDelayMs: 8000,
  msPerCharacter: 30,
  maxPresenceMs: 15000,
  minInterContactDelayMs: 15000,
  maxInterContactDelayMs: 45000,
  businessHoursStartHour: 8,
  businessHoursStartMinute: 30,
  businessHoursEndHour: 18,
  businessHoursEndMinute: 30,
};

export class Humanizer {
  private lastContactTimestamps: Map<string, number> = new Map();
  private config: HumanizerConfig;

  constructor(customConfig: Partial<HumanizerConfig> = {}) {
    this.config = { ...defaultHumanizerConfig, ...customConfig };
  }

  /**
   * Calculates typing presence duration based on text length (TC-103).
   * ~30ms per character capped at 15s max.
   */
  calculateTypingDurationMs(text: string): number {
    const raw = text.length * this.config.msPerCharacter;
    return Math.min(Math.max(raw, 500), this.config.maxPresenceMs);
  }

  /**
   * Generates random inter-message typing delay between 3s and 8s (TC-102).
   */
  getRandomTypingDelayMs(): number {
    const min = this.config.minTypingDelayMs;
    const max = this.config.maxTypingDelayMs;
    return Math.floor(Math.random() * (max - min + 1)) + min;
  }

  /**
   * Calculates delay required before dispatching to a new contact (TC-104).
   * Pacing is between 15s and 45s between distinct conversations.
   */
  getInterContactPacingDelayMs(
    contactJid: string,
    now: number = Date.now(),
  ): number {
    const lastTime = this.lastContactTimestamps.get(contactJid);
    if (!lastTime) {
      this.lastContactTimestamps.set(contactJid, now);
      return 0;
    }

    const elapsed = now - lastTime;
    const targetInterval =
      Math.floor(
        Math.random() *
          (this.config.maxInterContactDelayMs -
            this.config.minInterContactDelayMs +
            1),
      ) + this.config.minInterContactDelayMs;

    const remainingWait = Math.max(0, targetInterval - elapsed);
    this.lastContactTimestamps.set(contactJid, now + remainingWait);
    return remainingWait;
  }

  /**
   * Verifies if given date/time is within configured business hours (08:30-18:30 BRT, Mon-Fri) (TC-163, TC-164).
   */
  isWithinBusinessHours(date: Date = new Date()): boolean {
    // Convert to BRT (UTC-3)
    const utcHours = date.getUTCHours();
    const utcMinutes = date.getUTCMinutes();
    const dayOfWeekUtc = date.getUTCDay();

    // Calculate Brazil standard time (UTC - 3)
    let brtHours = utcHours - 3;
    let brtDay = dayOfWeekUtc;
    if (brtHours < 0) {
      brtHours += 24;
      brtDay = (dayOfWeekUtc + 6) % 7;
    }

    // Weekend check: 0 is Sunday, 6 is Saturday
    if (brtDay === 0 || brtDay === 6) {
      return false;
    }

    const currentMinutes = brtHours * 60 + utcMinutes;
    const startMinutes =
      this.config.businessHoursStartHour * 60 +
      this.config.businessHoursStartMinute;
    const endMinutes =
      this.config.businessHoursEndHour * 60 +
      this.config.businessHoursEndMinute;

    return currentMinutes >= startMinutes && currentMinutes <= endMinutes;
  }

  /**
   * Calculates the next opening time (08:30 BRT) if current time is outside business hours.
   */
  getNextBusinessHoursOpening(date: Date = new Date()): Date {
    const nextDate = new Date(date.getTime());
    let steps = 0;
    while (!this.isWithinBusinessHours(nextDate) && steps < 1008) {
      // Step forward by 10 minutes until within hours (max 7 days)
      nextDate.setTime(nextDate.getTime() + 10 * 60 * 1000);
      steps++;
    }
    return nextDate;
  }
}

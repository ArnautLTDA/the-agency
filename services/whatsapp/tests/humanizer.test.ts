import { describe, it, expect } from "vitest";
import { Humanizer } from "../src/humanizer.js";

describe("WhatsApp Humanizer (TC-101 to TC-104, TC-163, TC-164)", () => {
  const humanizer = new Humanizer();

  it("calculates typing duration based on character count capped at 15s (TC-103)", () => {
    // Short text: 20 chars * 30ms = 600ms
    const shortText = "Olá, tudo bem com vc";
    const durationShort = humanizer.calculateTypingDurationMs(shortText);
    expect(durationShort).toBeGreaterThanOrEqual(500);
    expect(durationShort).toBeLessThan(1000);

    // Very long text: 1000 chars * 30ms = 30000ms -> should cap at 15000ms
    const longText = "a".repeat(1000);
    const durationLong = humanizer.calculateTypingDurationMs(longText);
    expect(durationLong).toBe(15000);
  });

  it("generates random typing delay between 3000ms and 8000ms (TC-102)", () => {
    for (let i = 0; i < 20; i++) {
      const delay = humanizer.getRandomTypingDelayMs();
      expect(delay).toBeGreaterThanOrEqual(3000);
      expect(delay).toBeLessThanOrEqual(8000);
    }
  });

  it("enforces inter-contact pacing between 15s and 45s (TC-104)", () => {
    const contactA = "5511999990001@s.whatsapp.net";
    const t0 = 1000000;

    // First contact has 0 initial wait
    const delay1 = humanizer.getInterContactPacingDelayMs(contactA, t0);
    expect(delay1).toBe(0);

    // Immediate subsequent contact requires pacing between 15s and 45s
    const delay2 = humanizer.getInterContactPacingDelayMs(contactA, t0 + 1000);
    expect(delay2).toBeGreaterThanOrEqual(14000);
    expect(delay2).toBeLessThanOrEqual(45000);
  });

  it("validates business hours correctly for Brazil standard time (08:30-18:30 BRT, Mon-Fri) (TC-163)", () => {
    // Wednesday 14:00 BRT (17:00 UTC)
    const wednesdayWorkingHours = new Date(Date.UTC(2026, 10, 11, 17, 0, 0));
    expect(humanizer.isWithinBusinessHours(wednesdayWorkingHours)).toBe(true);

    // Wednesday 08:35 BRT (11:35 UTC)
    const wednesdayMorning = new Date(Date.UTC(2026, 10, 11, 11, 35, 0));
    expect(humanizer.isWithinBusinessHours(wednesdayMorning)).toBe(true);
  });

  it("rejects out-of-hours messages (nighttime and weekends) (TC-164)", () => {
    // Wednesday 22:00 BRT (Thursday 01:00 UTC)
    const wednesdayNight = new Date(Date.UTC(2026, 10, 12, 1, 0, 0));
    expect(humanizer.isWithinBusinessHours(wednesdayNight)).toBe(false);

    // Sunday 14:00 BRT
    const sundayAfternoon = new Date(Date.UTC(2026, 10, 15, 17, 0, 0));
    expect(humanizer.isWithinBusinessHours(sundayAfternoon)).toBe(false);
  });

  it("computes next opening time at 08:30 BRT when out of hours", () => {
    // Sunday 20:00 BRT -> next opening should be within Monday business hours
    const sundayNight = new Date(Date.UTC(2026, 10, 15, 23, 0, 0));
    const nextOpening = humanizer.getNextBusinessHoursOpening(sundayNight);
    expect(humanizer.isWithinBusinessHours(nextOpening)).toBe(true);
  });
});

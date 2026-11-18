import { test, expect } from "@playwright/test";
import {
  cn,
  formatDate,
  formatDateTime,
  formatRelativeTime,
  truncate,
  formatNumber,
  scoreColor,
  scoreBadgeClass,
} from "../src/lib/utils";

test.describe("Frontend Utility Functions", () => {
  test("cn: combines classes properly", () => {
    expect(cn("bg-red-500", "text-white")).toBe("bg-red-500 text-white");
    expect(cn("p-4", false && "hidden", null, undefined, "m-2")).toBe("p-4 m-2");
  });

  test("formatDate: formats ISO date string", () => {
    expect(formatDate(null)).toBe("—");
    expect(formatDate(undefined)).toBe("—");
    const formatted = formatDate("2026-11-17T10:00:00Z");
    expect(formatted).toContain("2026");
  });

  test("formatDateTime: formats ISO date string with time", () => {
    expect(formatDateTime(null)).toBe("—");
    const formatted = formatDateTime("2026-11-17T10:00:00Z");
    expect(formatted).toContain("2026");
  });

  test("formatRelativeTime: handles recent and older intervals", () => {
    expect(formatRelativeTime(null)).toBe("—");

    const now = new Date();
    expect(formatRelativeTime(now.toISOString())).toBe("just now");

    const tenMinsAgo = new Date(Date.now() - 10 * 60 * 1000);
    expect(formatRelativeTime(tenMinsAgo.toISOString())).toBe("10m ago");

    const twoHoursAgo = new Date(Date.now() - 2 * 60 * 60 * 1000);
    expect(formatRelativeTime(twoHoursAgo.toISOString())).toBe("2h ago");

    const threeDaysAgo = new Date(Date.now() - 3 * 24 * 60 * 60 * 1000);
    expect(formatRelativeTime(threeDaysAgo.toISOString())).toBe("3d ago");
  });

  test("truncate: cuts string with ellipsis at maxLength", () => {
    expect(truncate("Hello World", 5)).toBe("Hello…");
    expect(truncate("Short", 10)).toBe("Short");
    expect(truncate("", 5)).toBe("");
  });

  test("formatNumber: formats large numbers compactly", () => {
    expect(formatNumber(500)).toBe("500");
    expect(formatNumber(1200)).toBe("1.2k");
    expect(formatNumber(2500000)).toBe("2.5M");
  });

  test("scoreColor & scoreBadgeClass: returns correct classes for score thresholds", () => {
    expect(scoreColor(0.85)).toBe("text-emerald-400");
    expect(scoreColor(0.55)).toBe("text-amber-400");
    expect(scoreColor(0.25)).toBe("text-red-400");

    expect(scoreBadgeClass(0.85)).toContain("emerald");
    expect(scoreBadgeClass(0.55)).toContain("amber");
    expect(scoreBadgeClass(0.25)).toContain("red");
  });
});

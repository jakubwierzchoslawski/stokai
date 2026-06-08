import { describe, it, expect } from 'vitest';
/**
 * Unit tests for screenerUtils.rowsToCsv (TDD).
 *
 * Covers:
 * - correct header row
 * - correct data rows
 * - numeric formatting (2dp for scores/price, 0dp for market cap)
 * - active_event_categories joined with ";"
 * - special characters escaped per RFC 4180
 */
import { rowsToCsv } from "../../../src/frontend/features/screener/screenerUtils";
import type { ScreenerRow } from "../../../src/frontend/features/screener/screenerTypes";

function makeRow(overrides: Partial<ScreenerRow> = {}): ScreenerRow {
  return {
    company_id: "00000000-0000-0000-0000-000000000001",
    ticker: "AAPL",
    name: "Apple Inc",
    sector: "Technology",
    market_cap: 3_000_000_000,
    custom_score: 87.654,
    score_delta: -3.21,
    current_price: 180.99,
    active_events_count: 2,
    active_event_categories: ["geopolitical", "financial"],
    ...overrides,
  };
}

describe("rowsToCsv", () => {
  describe("header row", () => {
    it("produces the correct header row as the first line", () => {
      const csv = rowsToCsv([]);
      const firstLine = csv.split("\r\n")[0];
      expect(firstLine).toBe(
        "Ticker,Name,Sector,Market Cap,Custom Score,Score Delta,Price,Active Events,Event Categories",
      );
    });
  });

  describe("data rows", () => {
    it("produces one data row per ScreenerRow", () => {
      const csv = rowsToCsv([makeRow(), makeRow({ ticker: "MSFT" })]);
      const lines = csv.split("\r\n").filter(Boolean);
      // header + 2 data rows
      expect(lines).toHaveLength(3);
    });

    it("outputs ticker in the first data column", () => {
      const csv = rowsToCsv([makeRow({ ticker: "GOOG" })]);
      const dataLine = csv.split("\r\n")[1];
      expect(dataLine.startsWith("GOOG,")).toBe(true);
    });
  });

  describe("numeric formatting", () => {
    it("formats custom_score to 2 decimal places", () => {
      const csv = rowsToCsv([makeRow({ custom_score: 87.654 })]);
      expect(csv).toContain("87.65");
    });

    it("formats score_delta to 2 decimal places", () => {
      const csv = rowsToCsv([makeRow({ score_delta: -3.21 })]);
      expect(csv).toContain("-3.21");
    });

    it("formats current_price to 2 decimal places", () => {
      const csv = rowsToCsv([makeRow({ current_price: 180.9 })]);
      expect(csv).toContain("180.90");
    });

    it("formats market_cap to 0 decimal places", () => {
      const csv = rowsToCsv([makeRow({ market_cap: 3_000_000_000.7 })]);
      // Should not contain a decimal point for market cap
      const dataLine = csv.split("\r\n")[1];
      expect(dataLine).toContain("3000000001");
    });
  });

  describe("active_event_categories", () => {
    it("joins categories with semicolon", () => {
      const csv = rowsToCsv([
        makeRow({ active_event_categories: ["geopolitical", "financial", "macro"] }),
      ]);
      expect(csv).toContain("geopolitical;financial;macro");
    });

    it("handles empty categories array", () => {
      const csv = rowsToCsv([makeRow({ active_event_categories: [] })]);
      const dataLine = csv.split("\r\n")[1];
      // Last field should be empty (no categories)
      expect(dataLine.endsWith(",")).toBe(true);
    });
  });

  describe("RFC 4180 special character escaping", () => {
    it("wraps field containing comma in double-quotes", () => {
      const csv = rowsToCsv([makeRow({ name: "Smith, Jones & Co" })]);
      expect(csv).toContain('"Smith, Jones & Co"');
    });

    it("escapes embedded double-quotes by doubling them", () => {
      const csv = rowsToCsv([makeRow({ name: 'He said "hello"' })]);
      expect(csv).toContain('"He said ""hello"""');
    });

    it("wraps field containing newline in double-quotes", () => {
      const csv = rowsToCsv([makeRow({ name: "Line1\nLine2" })]);
      expect(csv).toContain('"Line1\nLine2"');
    });

    it("does not quote ordinary fields", () => {
      const csv = rowsToCsv([makeRow({ ticker: "AAPL" })]);
      // ticker should not be wrapped in quotes since it has no special chars
      const dataLine = csv.split("\r\n")[1];
      expect(dataLine.startsWith("AAPL,")).toBe(true);
      expect(dataLine.startsWith('"AAPL",')).toBe(false);
    });
  });

  describe("CRLF line endings", () => {
    it("uses CRLF line endings between rows", () => {
      const csv = rowsToCsv([makeRow()]);
      // Should contain at least one CRLF
      expect(csv).toContain("\r\n");
    });
  });
});

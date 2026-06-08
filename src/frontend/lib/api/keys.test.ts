import { describe, it, expect } from "vitest";
import { qk } from "./keys";

describe("qk", () => {
  it("returns a tuple of [resource, ...ids]", () => {
    expect(qk("briefs", "abc")).toEqual(["briefs", "abc"]);
  });
  it("appends a params object when provided", () => {
    expect(qk("screener", { sector: "tech" })).toEqual(["screener", { sector: "tech" }]);
  });
  it("treats a single-string call as [resource]", () => {
    expect(qk("me")).toEqual(["me"]);
  });
});

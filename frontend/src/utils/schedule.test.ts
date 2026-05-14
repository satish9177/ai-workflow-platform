import { describe, expect, it } from "vitest";

import { buildTriggerPayload, cronToLabel, SCHEDULE_PRESETS } from "./schedule";

describe("cronToLabel", () => {
  it("returns correct label for each preset cron value", () => {
    for (const preset of SCHEDULE_PRESETS.filter((option) => option.cron !== "custom")) {
      expect(cronToLabel(preset.cron)).toBe(preset.label);
    }
  });

  it("returns the raw expression for an unknown cron string", () => {
    expect(cronToLabel("5 10 * * 2")).toBe("5 10 * * 2");
  });
});

describe("buildTriggerPayload", () => {
  it("with mode manual returns trigger_type manual and empty trigger_config", () => {
    expect(buildTriggerPayload("manual", "")).toEqual({ trigger_type: "manual", trigger_config: {} });
  });

  it("with mode cron returns trigger_type cron and correct trigger_config shape", () => {
    expect(buildTriggerPayload("cron", "0 9 * * 1")).toEqual({
      trigger_type: "cron",
      trigger_config: { cron_expression: "0 9 * * 1" },
    });
  });
});

describe("SCHEDULE_PRESETS", () => {
  it("contains exactly 6 entries", () => {
    expect(SCHEDULE_PRESETS).toHaveLength(6);
  });

  it("every preset except Custom has a non-empty cron string that is not custom", () => {
    for (const preset of SCHEDULE_PRESETS.filter((option) => option.label !== "Custom")) {
      expect(preset.cron).toBeTruthy();
      expect(preset.cron).not.toBe("custom");
    }
  });
});

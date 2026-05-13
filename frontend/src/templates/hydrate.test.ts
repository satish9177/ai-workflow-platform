import { describe, expect, it } from "vitest";

import { getMissingPlaceholders, hydrate } from "./hydrate";
import type { WorkflowTemplate } from "./types";

const template: WorkflowTemplate = {
  id: "test",
  name: "Test",
  description: "Test template",
  required_integrations: [],
  placeholders: [
    { key: "required", label: "Required", type: "text", required: true },
    { key: "optional", label: "Optional", type: "text", required: false },
  ],
  workflow_definition: {},
};

describe("hydrate", () => {
  it("replaces a single token", () => {
    expect(hydrate({ name: "{{name}}" }, { name: "Workflow" })).toEqual({ name: "Workflow" });
  });

  it("replaces multiple tokens", () => {
    expect(hydrate({ a: "{{one}}", b: "{{two}}" }, { one: "1", two: "2" })).toEqual({ a: "1", b: "2" });
  });

  it("replaces repeated token occurrences", () => {
    expect(hydrate({ a: "{{name}}", b: "{{name}}" }, { name: "Repeated" })).toEqual({
      a: "Repeated",
      b: "Repeated",
    });
  });

  it("leaves missing tokens unchanged", () => {
    expect(hydrate({ name: "{{missing}}" }, {})).toEqual({ name: "{{missing}}" });
  });

  it("works with empty values object", () => {
    expect(hydrate({ name: "Static" }, {})).toEqual({ name: "Static" });
  });
});

describe("getMissingPlaceholders", () => {
  it("returns required empty keys", () => {
    expect(getMissingPlaceholders(template, { required: " " })).toEqual(["required"]);
  });

  it("ignores optional empty keys", () => {
    expect(getMissingPlaceholders(template, { required: "filled", optional: "" })).toEqual([]);
  });

  it("returns empty array when required values are filled", () => {
    expect(getMissingPlaceholders(template, { required: "filled" })).toEqual([]);
  });
});

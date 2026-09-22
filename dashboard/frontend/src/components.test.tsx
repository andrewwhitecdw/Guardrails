import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { JsonBlock, RailBars, StatusPill } from "./components";
import type { RailInfo } from "./types";

describe("StatusPill", () => {
  it("renders the status text", () => {
    render(<StatusPill status="blocked" />);
    expect(screen.getByText("blocked")).toBeTruthy();
  });
});

describe("RailBars", () => {
  const rails: RailInfo[] = [
    { name: "self check input", stop: true, duration: 0.5 },
    { name: "codeword", stop: false, duration: 0.25 },
  ];

  it("renders rail names with stop markers and durations", () => {
    render(<RailBars rails={rails} />);
    expect(screen.getByText("self check input (stopped)")).toBeTruthy();
    expect(screen.getByText("codeword")).toBeTruthy();
    expect(screen.getByText("500 ms")).toBeTruthy();
    expect(screen.getByText("250 ms")).toBeTruthy();
  });

  it("renders empty state", () => {
    render(<RailBars rails={[]} />);
    expect(screen.getByText("No rails activated.")).toBeTruthy();
  });
});

describe("JsonBlock", () => {
  it("pretty-prints JSON", () => {
    render(<JsonBlock data={{ a: 1 }} />);
    expect(screen.getByText(/"a": 1/)).toBeTruthy();
  });
});

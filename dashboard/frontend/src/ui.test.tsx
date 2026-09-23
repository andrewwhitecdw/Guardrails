import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Button, EmptyState, Skeleton, Spinner, Toaster, resetToastsForTests, toast } from "./ui";

beforeEach(() => {
  resetToastsForTests();
});

describe("Button", () => {
  it("renders primary variant with green background", () => {
    render(<Button variant="primary">Go</Button>);
    const btn = screen.getByRole("button", { name: "Go" });
    expect(btn.style.backgroundColor).toBe("rgb(118, 185, 0)");
  });

  it("renders danger variant with red text", () => {
    render(<Button variant="danger">Delete</Button>);
    expect(screen.getByRole("button", { name: "Delete" }).style.color).toBe("rgb(255, 92, 92)");
  });

  it("is disabled when asked", () => {
    render(<Button disabled>Nope</Button>);
    expect(screen.getByRole("button", { name: "Nope" })).toHaveProperty("disabled", true);
  });
});

describe("EmptyState", () => {
  it("renders title and hint", () => {
    render(<EmptyState title="Nothing here" hint="Try again" />);
    expect(screen.getByText("Nothing here")).toBeTruthy();
    expect(screen.getByText("Try again")).toBeTruthy();
  });
});

describe("Skeleton", () => {
  it("renders a pulsing placeholder", () => {
    const { container } = render(<Skeleton width={100} height={10} />);
    expect((container.firstChild as HTMLElement).style.animation).toContain("nv-pulse");
  });
});

describe("Spinner", () => {
  it("renders a status indicator", () => {
    render(<Spinner />);
    expect(screen.getByRole("status")).toBeTruthy();
  });
});

describe("toast", () => {
  it("shows a toast in the toaster", () => {
    render(<Toaster />);
    act(() => toast("Saved", "success"));
    expect(screen.getByText("Saved")).toBeTruthy();
  });

  it("auto-dismisses the toast after 4 seconds", () => {
    vi.useFakeTimers();
    try {
      render(<Toaster />);
      act(() => toast("Bye"));
      expect(screen.getByText("Bye")).toBeTruthy();
      act(() => vi.advanceTimersByTime(4000));
      expect(screen.queryByText("Bye")).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });
});

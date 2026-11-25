import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { WeekFeePanel } from "../components/WeekFeePanel";
import type { WeekFee } from "../lib/twoGameTypes";

/**
 * Batch 238 (owner, 24 Nov 2026): the week's payment is a strip at the top of both game
 * screens. What is owed, the payment link and the status check stay in view; the detail
 * folds away, and a `#payment` link opens it.
 */
const fee = (extra: Partial<WeekFee> = {}): WeekFee => ({
  league_id: "league-a",
  week_id: "week-a",
  week_label: "2026-11-28",
  billing_starts_at: "2026-11-23T00:00:00Z",
  billing_ends_at: "2026-11-30T00:00:00Z",
  obligation_pence: 100,
  amount_owed_pence: 100,
  paid_through: false,
  pooled_credit_pence: 0,
  payment_url: "https://synthetic.invalid/pay",
  destination: "/leagues/league-a/weeks/week-a/fantasy#payment",
  obligations: [{ week_id: "week-a", week_label: "2026-11-28", remaining_pence: 100 }],
  ...extra,
});

function strip(value: WeekFee, entry = "/leagues/league-a/weeks/week-a/fantasy") {
  const refresh = vi.fn();
  render(
    <MemoryRouter initialEntries={[entry]}>
      <WeekFeePanel fee={value} onRefresh={refresh} />
    </MemoryRouter>,
  );
  return { refresh };
}

describe("the week's payment strip", () => {
  it("offers Pay £1 for both games and folds the detail away until asked", () => {
    const { refresh } = strip(fee());
    const region = screen.getByRole("region", { name: "Payment for 28 Nov" });
    expect(region).toHaveTextContent("£1.00 owed through this week");
    expect(region).toHaveTextContent("One £1 a week covers both games.");
    expect(screen.getByRole("link", { name: "Pay £1" })).toHaveAttribute(
      "href",
      "https://synthetic.invalid/pay",
    );
    const details = screen.getByRole("button", { name: "Details" });
    expect(details).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByText(/Pooled credit after recorded fees/)).not.toBeVisible();
    fireEvent.click(details);
    expect(details).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(/Pooled credit after recorded fees/)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Check payment status" }));
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("names a larger balance on the button, and offers none once paid", () => {
    strip(fee({ amount_owed_pence: 300 }));
    expect(screen.getByRole("link", { name: "Pay £3.00" })).toBeTruthy();
    document.body.innerHTML = "";
    strip(fee({ amount_owed_pence: 0, paid_through: true }));
    expect(screen.getByRole("region", { name: "Payment for 28 Nov" })).toHaveTextContent(
      "Paid through this week",
    );
    expect(screen.queryByRole("link", { name: /^Pay / })).toBeNull();
  });

  it("opens the detail and takes focus when a #payment link lands on it", () => {
    strip(fee(), "/leagues/league-a/weeks/week-a/fantasy#payment");
    const region = screen.getByRole("region", { name: "Payment for 28 Nov" });
    expect(screen.getByRole("button", { name: "Details" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(screen.getByText(/Pooled credit after recorded fees/)).toBeVisible();
    expect(region).toHaveFocus();
  });

  // Batch 247 (owner, 25 Nov 2026): a paid week is one line. The status check and Details
  // stay in it as icon buttons; the heading and the £1 note fold away with the detail.
  it("keeps a paid week to one line, its status check and detail one tap away", () => {
    const { refresh } = strip(fee({ amount_owed_pence: 0, paid_through: true }));
    expect(screen.getByRole("status")).toHaveTextContent("Paid through this week");
    const heading = screen.getByRole("heading", { name: "Payment for 28 Nov" });
    expect(heading).toHaveClass("sr-only");
    expect(screen.getByText("One £1 a week covers both games.")).not.toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Check payment status" }));
    expect(refresh).toHaveBeenCalledTimes(1);
    const details = screen.getByRole("button", { name: "Details" });
    expect(details).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(details);
    expect(details).toHaveAttribute("aria-expanded", "true");
    expect(heading).not.toHaveClass("sr-only");
    expect(screen.getByText("One £1 a week covers both games.")).toBeVisible();
    expect(screen.getByText(/Pooled credit after recorded fees/)).toBeVisible();
  });

  it("shows a paid week's heading and detail when a #payment link lands on it", () => {
    strip(
      fee({ amount_owed_pence: 0, paid_through: true }),
      "/leagues/league-a/weeks/week-a/fantasy#payment",
    );
    const region = screen.getByRole("region", { name: "Payment for 28 Nov" });
    expect(screen.getByRole("button", { name: "Details" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(screen.getByRole("heading", { name: "Payment for 28 Nov" })).not.toHaveClass(
      "sr-only",
    );
    expect(screen.getByText(/Pooled credit after recorded fees/)).toBeVisible();
    expect(region).toHaveFocus();
  });
});

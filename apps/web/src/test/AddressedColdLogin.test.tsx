import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";
import { ProtectedRoute } from "../components/ProtectedRoute";
vi.mock("../contexts/AuthContext", () => ({
  useAuth: () => ({
    player: null,
    sessionResuming: false,
    sessionUnlockRequired: false,
  }),
}));
function Destination() {
  const location = useLocation();
  return <p>{location.pathname + location.search}</p>;
}
describe("cold addressed game login", () => {
  it.each([
    "/leagues/league-b/games?season=2026#history",
    "/leagues/former/games/",
    "/leagues/league-b/weeks/week-z/group#payment",
    "/leagues/league-b/weeks/week-a/fantasy?from=receipt#payment",
  ])("retains the complete destination for %s", async (path) => {
    render(
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route element={<ProtectedRoute />}>
            <Route path="/leagues/*" element={<p>Protected game</p>} />
          </Route>
          <Route path="/login" element={<Destination />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(
      await screen.findByText("/login?next=" + encodeURIComponent(path)),
    ).toBeVisible();
  });
  it.each([
    "/leagues/legacy/predictions?gw=old",
    "/leagues/league-b/games/settings",
  ])("preserves the existing login behaviour for %s", async (path) => {
    render(
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route element={<ProtectedRoute />}>
            <Route path="/leagues/*" element={<p>Protected game</p>} />
          </Route>
          <Route path="/login" element={<Destination />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByText("/login")).toBeVisible();
  });
});

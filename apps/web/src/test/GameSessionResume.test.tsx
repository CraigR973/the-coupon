import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider, useAuth } from "../contexts/AuthContext";
import { getAccessToken, getStoredPlayer, storeTokens } from "../lib/tokens";

const token = (seconds: number) =>
  `x.${btoa(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + seconds }))}.x`;
const response = (body: unknown) =>
  new Response(JSON.stringify(body), { status: 200 });
function Member() {
  const auth = useAuth();
  return (
    <>
      <p data-testid="member">
        {auth.player?.id}:{String(auth.sessionResuming)}
      </p>
      <button onClick={() => void auth.login("Bob", "1357")}>
        Sign in Bob
      </button>
    </>
  );
}
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  localStorage.clear();
});
describe("cold session and deferred game identity", () => {
  it("keeps the newly signed-in member when the old cold-start refresh returns late", async () => {
    localStorage.clear();
    storeTokens(token(-1), "refresh-alice", {
      id: "alice",
      displayName: "Alice",
      role: "player",
      timezone: "Europe/London",
    });
    let release!: (value: Response) => void;
    const paused = new Promise<Response>((resolve) => {
      release = resolve;
    });
    const bobToken = token(7200);
    const fetcher = vi.fn(async (url: string) =>
      url.endsWith("/refresh")
        ? paused
        : response({
            access_token: bobToken,
            refresh_token: "refresh-bob",
            player: {
              id: "bob",
              display_name: "Bob",
              role: "player",
              timezone: "Europe/London",
            },
          }),
    );
    vi.stubGlobal("fetch", fetcher);
    const client = new QueryClient();
    render(
      <QueryClientProvider client={client}>
        <AuthProvider>
          <Member />
        </AuthProvider>
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("member")).toHaveTextContent("alice:true");
    fireEvent.click(screen.getByRole("button", { name: "Sign in Bob" }));
    await screen.findByText("bob:false");
    await act(async () => {
      release(
        response({ access_token: token(3600), refresh_token: "rotated-alice" }),
      );
      await paused;
    });
    expect(screen.getByTestId("member")).toHaveTextContent("bob:false");
    expect(getStoredPlayer()?.id).toBe("bob");
    expect(getAccessToken()).toBe(bobToken);
    client.clear();
  });
});

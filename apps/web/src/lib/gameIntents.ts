import { ApiError, NetworkError, apiFetch } from "./api";
import { getStoredPlayer } from "./tokens";
import { gamePath, type GameEntry, type GameTarget } from "./twoGameTypes";

export type IntentPhase =
  | "queued"
  | "sending"
  | "checking"
  | "uncertain"
  | "confirmed"
  | "conflict"
  | "refused";
export interface GameChoice {
  fixture_id: string;
  market: string;
  outcome: string;
  odds?: string;
}
export interface GameIntent {
  target: GameTarget;
  slot: number;
  /**
   * For a removal (Batch 235) the body still names the pick being withdrawn, so the slip
   * keeps treating the slot as held until the empty readback arrives; only the expected
   * revision and the operation id are sent.
   */
  body: GameChoice & { expected_revision: number; operation_id: string };
  remove?: boolean;
  phase: IntentPhase;
  message: string;
  refusal?: ApiError;
}
export const intentKey = (target: GameTarget, slot: number) =>
  `${target.league_id}/${target.week_id}/${target.game_kind}/${slot}`;
const endpoint = (intent: GameIntent) =>
  gamePath(intent.target) +
  (intent.target.game_kind === "group" ? "/pick" : `/slots/${intent.slot}`);
interface Ports {
  read: (path: string, member: string) => Promise<GameEntry>;
  write: (
    path: string,
    body: GameIntent["body"],
    member: string,
  ) => Promise<GameEntry>;
  remove: (
    path: string,
    body: { expected_revision: number; operation_id: string },
    member: string,
  ) => Promise<GameEntry>;
  member: () => string | null;
  changed: () => void | Promise<void>;
}
const defaultPorts: Ports = {
  read: (path, member) =>
    apiFetch<GameEntry>(path, { expectedMemberId: member, timeoutMs: 10_000 }),
  write: (path, body, member) =>
    apiFetch<GameEntry>(path, {
      method: "PUT",
      body: JSON.stringify(body),
      expectedMemberId: member,
      timeoutMs: 10_000,
    }),
  remove: (path, body, member) =>
    apiFetch<GameEntry>(path, {
      method: "DELETE",
      body: JSON.stringify(body),
      expectedMemberId: member,
      timeoutMs: 10_000,
    }),
  member: () => getStoredPlayer()?.id ?? null,
  changed: () => undefined,
};

/** One immutable operation per exact target/slot. Route remounts cannot own this queue. */
export class GameIntents {
  private values = new Map<string, GameIntent>();
  private listeners = new Set<() => void>();
  private running = new Set<string>();
  private snapshot: GameIntent[] = [];
  private active = true;
  private generation = 0;
  private ports: Ports;
  constructor(
    readonly memberId: string,
    ports: Partial<Ports> = {},
  ) {
    this.ports = { ...defaultPorts, ...ports };
  }
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  getSnapshot = () => this.snapshot;
  activate = () => {
    this.active = true;
  };
  dispose = () => {
    this.active = false;
    this.generation++;
    this.values.clear();
    this.emit();
  };
  private emit() {
    this.snapshot = [...this.values.values()];
    this.listeners.forEach((listener) => listener());
  }
  private current(key: string, intent: GameIntent, generation: number) {
    return (
      this.active &&
      this.generation === generation &&
      this.ports.member() === this.memberId &&
      this.values.get(key)?.body.operation_id === intent.body.operation_id
    );
  }
  private update(
    key: string,
    intent: GameIntent,
    generation: number,
    phase: IntentPhase,
    message: string,
    refusal?: ApiError,
  ) {
    if (!this.current(key, intent, generation)) return;
    this.values.set(key, { ...intent, phase, message, refusal });
    this.emit();
  }
  choose(
    target: GameTarget,
    slot: number,
    choice: GameChoice,
    revision: number,
  ) {
    if (!this.active || this.ports.member() !== this.memberId) return;
    const key = intentKey(target, slot);
    this.values.set(key, {
      target: { ...target },
      slot,
      body: {
        ...choice,
        expected_revision: revision,
        operation_id: crypto.randomUUID(),
      },
      phase: "queued",
      message: "Waiting to save this choice.",
    });
    this.emit();
    void this.run(key);
  }
  /** Withdraw the pick a slot holds (Batch 235): one replayable DELETE, read back first. */
  remove(target: GameTarget, slot: number, pick: GameChoice, revision: number) {
    if (!this.active || this.ports.member() !== this.memberId) return;
    const key = intentKey(target, slot);
    this.values.set(key, {
      target: { ...target },
      slot,
      body: {
        fixture_id: pick.fixture_id,
        market: pick.market,
        outcome: pick.outcome,
        expected_revision: revision,
        operation_id: crypto.randomUUID(),
      },
      remove: true,
      phase: "queued",
      message: "Waiting to remove this pick.",
    });
    this.emit();
    void this.run(key);
  }
  reconnect = () => {
    for (const [key, intent] of this.values) {
      if (["queued", "uncertain"].includes(intent.phase)) void this.run(key);
    }
  };
  retry = (key: string) => {
    const intent = this.values.get(key);
    if (intent && ["queued", "uncertain"].includes(intent.phase))
      void this.run(key);
  };
  dismiss = (key: string) => {
    const intent = this.values.get(key);
    if (intent && !["sending", "checking"].includes(intent.phase)) {
      this.values.delete(key);
      this.emit();
    }
  };
  private async refreshRefused(
    key: string,
    intent: GameIntent,
    generation: number,
  ) {
    try {
      await this.ports.changed();
    } catch {
      if (!this.current(key, intent, generation)) return;
      const current = this.values.get(key)!;
      this.update(
        key,
        current,
        generation,
        current.phase,
        current.message +
          " The current saved choice could not be refreshed; check it before choosing again.",
        current.refusal,
      );
    }
  }
  private async run(key: string): Promise<void> {
    if (this.running.has(key)) return;
    const intent = this.values.get(key),
      generation = this.generation;
    if (!intent || !this.current(key, intent, generation)) return;
    this.running.add(key);
    let accepted = false;
    try {
      // Read before every dispatch, including known-offline reconnect. The same UUID
      // remains safe if the original request is still finishing behind this read.
      this.update(
        key,
        intent,
        generation,
        "checking",
        "Checking this exact saved choice…",
      );
      const entry = await this.ports.read(endpoint(intent), this.memberId);
      if (!this.current(key, intent, generation)) return;
      if (entry.operation_id === intent.body.operation_id) {
        accepted = true;
        await this.ports.changed();
        this.update(
          key,
          intent,
          generation,
          "confirmed",
          intent.remove ? "Pick removed." : "Saved choice confirmed.",
        );
        return;
      }
      if (entry.revision !== intent.body.expected_revision) {
        this.update(
          key,
          intent,
          generation,
          "conflict",
          "This choice changed on another device. Review the saved choice before choosing again.",
        );
        await this.refreshRefused(key, intent, generation);
        return;
      }
      if (intent.remove) {
        this.update(key, intent, generation, "sending", "Removing this pick…");
        const { expected_revision, operation_id } = intent.body;
        await this.ports.remove(
          endpoint(intent),
          { expected_revision, operation_id },
          this.memberId,
        );
      } else {
        this.update(key, intent, generation, "sending", "Saving this choice…");
        await this.ports.write(endpoint(intent), intent.body, this.memberId);
      }
      accepted = true;
      if (!this.current(key, intent, generation)) return;
      // An accepted operation is a historical receipt, not fresh result state.
      // Keep this target busy until its authoritative revision has refreshed;
      // a receipt alone cannot make a subsequent replacement safe to dispatch.
      this.update(
        key,
        intent,
        generation,
        "checking",
        "Refreshing the current saved choice…",
      );
      await this.ports.changed();
      this.update(
        key,
        intent,
        generation,
        "confirmed",
        intent.remove ? "Pick removed." : "Saved choice confirmed.",
      );
    } catch (error) {
      if (!this.current(key, intent, generation)) return;
      if (accepted) {
        this.update(
          key,
          intent,
          generation,
          "uncertain",
          "A save receipt arrived, but the current choice could not be refreshed. Check the saved choice before retrying.",
        );
      } else if (error instanceof NetworkError) {
        this.update(
          key,
          intent,
          generation,
          error.mayHaveLanded || intent.phase === "uncertain"
            ? "uncertain"
            : "queued",
          error.mayHaveLanded || intent.phase === "uncertain"
            ? "No answer yet. Check the saved choice before retrying."
            : "Offline choice kept on this device until you reconnect.",
        );
      } else {
        const refusal = error instanceof ApiError ? error : undefined;
        this.update(
          key,
          intent,
          generation,
          refusal?.code === "ENTRY_CHANGED" ? "conflict" : "refused",
          refusal?.message ??
            "This choice could not be saved. Review it and choose again.",
          refusal,
        );
        await this.refreshRefused(key, intent, generation);
      }
    } finally {
      this.running.delete(key);
      const next = this.values.get(key);
      if (
        next?.body.operation_id !== intent.body.operation_id &&
        next?.phase === "queued"
      )
        void this.run(key);
    }
  }
}

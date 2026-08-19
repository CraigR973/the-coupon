import '@testing-library/jest-dom';
import { configure } from '@testing-library/react';
import { toHaveNoViolations } from 'jest-axe';
expect.extend(toHaveNoViolations);

// Testing Library retries a `findBy*` for 1000ms by default, which is a statement
// about how fast the machine is rather than about the code. Every page here renders
// from a react-query read of a mocked fetch, so under CPU contention — a full suite
// on a busy laptop, or CI sharing a runner — the data lands after the wait has already
// given up and the element is reported missing. Measured on this repo: two full suites
// run concurrently produced roughly one failure in four, always `Unable to find …` for
// an element that does appear a moment later.
//
// 5000ms only extends how long a wait tolerates slowness; it cannot make a missing
// element appear, so a genuine regression still fails — just later. `testTimeout` has
// to stay clear of it or a single exhausted wait would trip the test timeout at the
// same moment and report the wrong cause.
//
// This does **not** cover asserting on stale state after the element is found: the
// element exists, so no wait is involved and no timeout helps. That needs a barrier on
// the data — see `formReady()` in `LeagueSettingsPage.test.tsx`.
configure({ asyncUtilTimeout: 5000 });

// jsdom does not implement matchMedia — provide a stub so hooks that call
// detectStandalone() or useInstallPrompt() don't throw in unit tests.
if (typeof window.matchMedia === 'undefined') {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
}

// Polyfill ResizeObserver (used by @radix-ui/react-popover in jsdom)
if (typeof globalThis.ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

// `setup.ts` registers jest-axe's matcher with `expect.extend`. Its types extend the
// `jest` namespace, which Vitest 5 no longer reads, so the matcher is declared to
// Vitest here (Batch 202). The type parameters mirror Vitest's own `Matchers`.
import 'vitest';

declare module 'vitest' {
  interface Matchers<R extends void | Promise<void> = void | Promise<void>, _T = unknown> {
    toHaveNoViolations(): R;
  }
}

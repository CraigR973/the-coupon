import { memo } from 'react';
import { useCountdown, type CountdownParts } from '@/hooks/useCountdown';

/**
 * The one thing on screen that has to change every second.
 *
 * Batch 165. The countdown used to be computed in the page body, so a tick re-rendered
 * the whole round screen — fixtures, roster, coupon and all — once a second, and there is
 * no `React.memo` anywhere in this codebase to stop the cascade. This owns the tick
 * instead, and is memoised so a re-render of its parent for any other reason does not
 * reach it.
 *
 * It renders text only, so the parent composes the sentence:
 * `Picks lock in <Countdown target={iso} format={formatCountdown} />`.
 *
 * `format` is a prop rather than built in because the two screens word it differently —
 * the round screen shows seconds inside an hour and home does not — and unifying them
 * here would quietly change what a member reads on one of them. Pass a module-level
 * function: a fresh closure each render would defeat the memo.
 */
export const Countdown = memo(function Countdown({
  target,
  format,
}: {
  target: string;
  format: (parts: CountdownParts) => string;
}) {
  return <>{format(useCountdown(target))}</>;
});

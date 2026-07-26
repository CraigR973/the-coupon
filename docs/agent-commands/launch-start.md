---
description: Start one ordered Coupon launch phase on a clean working branch.
---

# /launch-start

This workflow only prepares a branch and reports scope. It does not provision,
deploy, seed, or otherwise execute the phase.

`$ARGUMENTS` must match `^L[0-5]$` exactly. Lowercase IDs are not normalized.

1. Read `STATUS.md`, `docs/LAUNCH_PLAN.md`, and the latest `launch-log.md`
   section.
2. Reject the request before using `$ARGUMENTS` in any command unless it
   matches the required expression. Then locate the exact status row:

   ```bash
   grep -nE "^- \[[ x]\] \*\*$ARGUMENTS — " \
     /Users/craigrobinson/the-coupon/docs/LAUNCH_PLAN.md
   ```

   Stop if the ID is invalid, absent, or already checked.
3. Enforce phase order. Every earlier `L` status row must already be checked.
   Report the first open prerequisite and stop if the sequence has a gap.
4. Require a clean worktree on local `main`:

   ```bash
   git -C /Users/craigrobinson/the-coupon status --porcelain
   git -C /Users/craigrobinson/the-coupon symbolic-ref --short HEAD
   ```

   Do not stash, discard, or absorb unrelated work.
5. Create the phase's canonical branch:

   | Phase | Branch |
   | --- | --- |
   | `L0` | `chore/launch-l0-project-identity` |
   | `L1` | `feat/launch-l1-hardening` |
   | `L2` | `feat/launch-l2-staging-infrastructure` |
   | `L3` | `chore/launch-l3-staging-verification` |
   | `L4` | `feat/launch-l4-production-infrastructure` |
   | `L5` | `chore/launch-l5-first-saturday-watch` |

   Stop if the branch already exists; never delete or overwrite it.
6. Read the matching `### $ARGUMENTS — ...` section through its `**Gate:**`
   paragraph. Report:
   - the branch;
   - the exact phase title;
   - every unchecked phase item;
   - the gate;
   - owner decisions or credentials that will be required;
   - external systems the phase is allowed to affect.
7. Remind the user to implement only that phase, then invoke
   `/launch-verify $ARGUMENTS` and wait for explicit
   `/launch-closeout $ARGUMENTS`.

## Safety

- Never infer an external target from an ambient CLI login, cached project
  link, `.codex/config.toml`, or another repository.
- Starting a phase does not authorize access to an unconfirmed Supabase,
  Railway, Vercel, GitHub, DNS, Sentry, or Betfair target.
- Never log into the owner's live Betfair account. Owner-only checks remain
  owner actions even when listed in a launch gate.
- Do not fetch, pull, push, create a PR, provision, deploy, seed, alter DNS, or
  update phase checkboxes in this workflow.

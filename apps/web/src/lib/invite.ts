import { toast } from 'sonner';

export interface InviteMessageParams {
  leagueName: string;
  joinCode: string;
  origin: string;
  /**
   * A `/join/:token` link, when the league has a live invite to offer.
   *
   * The one-tap path: it carries the league, so the recipient never types a code and
   * never has to find the join screen. `LeagueAdminInvitesPage` has minted these since
   * Batch 100 and the message explained only the other flow.
   */
  inviteUrl?: string;
}

/**
 * What a stranger reads first. Batch 118 rewrote it, because every line of it described
 * something that is no longer true.
 *
 * * It said *"sign in with the display name and PIN from your admin."* Signup became
 *   public on 2026-08-22 and the onboarding copy was corrected then; this — the half that
 *   gets sent to people outside the app — was not. Nobody has ever been able to follow it.
 * * It routed the recipient through *Leagues → Join by code* while `/join/:token` links
 *   existed as a one-tap path, so it explained only the clunkier of the two flows.
 * * It opened with *"Install the app first:"* over the bare origin, which is wrong for a
 *   recipient reading it on a computer — where the app runs in the browser — and drops
 *   everyone else onto a URL with no idea what to do with it.
 *
 * The shape now: what the game is, then the one link to tap, then what happens when they
 * tap it on each kind of device, then the code as the fallback for a message forwarded
 * without its link. Kept under 400 characters because it is pasted into a share sheet.
 */
export function buildInviteMessage({
  leagueName,
  joinCode,
  origin,
  inviteUrl,
}: InviteMessageParams): string {
  const lines = [
    `Join me on The Coupon — our weekly football picks.`,
    ``,
    `Claim one unique Saturday selection, score the frozen odds, climb the table.`,
    ``,
  ];

  if (inviteUrl) {
    lines.push(`Tap to join ${leagueName}:`, inviteUrl, ``);
  } else {
    lines.push(`Open ${origin} to get started.`, ``);
  }

  lines.push(
    `On a computer it runs in the browser; on a phone it shows you how to add it. You make your own account — nothing to ask an admin for.`,
    ``,
  );

  if (inviteUrl) {
    // One line, because it is the fallback for a message forwarded without its link —
    // and the link above already names the league.
    lines.push(`No link? ${origin} → Leagues → Join by code → ${joinCode}`);
  } else {
    lines.push(`Then: Leagues → Join by code.`, `League: ${leagueName}`, `Join code: ${joinCode}`);
  }

  return lines.join('\n');
}

export interface ShareInviteParams {
  message: string;
}

export async function shareInvite({ message }: ShareInviteParams): Promise<'shared' | 'copied' | 'cancelled'> {
  if (typeof navigator !== 'undefined' && navigator.share) {
    try {
      // Share text only — no url param. iOS renders the url as a separate
      // clickable link below the text, which clutters the preview and appears
      // adjacent to the "already have the app" line. The install URL is already
      // embedded in the message text so there's no information loss.
      await navigator.share({ text: message });
      return 'shared';
    } catch (err) {
      // AbortError = user dismissed/swiped the share sheet — not an error, stay silent
      if (err instanceof Error && err.name === 'AbortError') return 'cancelled';
      throw err;
    }
  }
  await navigator.clipboard.writeText(`${message}`);
  toast.success('Invite link copied to clipboard');
  return 'copied';
}

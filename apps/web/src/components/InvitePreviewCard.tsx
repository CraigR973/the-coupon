export interface InvitePreview {
  league_name: string;
  inviter_name: string;
  member_count: number;
}

export function InvitePreviewCard({ preview }: { preview: InvitePreview }) {
  return (
    <div className="rounded-xl border border-border bg-surface px-5 py-4 text-center space-y-1">
      <p className="font-sans font-semibold text-text-primary">{preview.league_name}</p>
      <p className="text-sm text-text-secondary">Invited by {preview.inviter_name}</p>
      <p className="text-xs text-text-muted">
        {preview.member_count} {preview.member_count === 1 ? 'member' : 'members'}
      </p>
    </div>
  );
}

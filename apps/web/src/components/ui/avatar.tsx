import { useState, useEffect, type HTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

interface AvatarProps extends HTMLAttributes<HTMLDivElement> {
  name: string;
  size?: 'sm' | 'md' | 'lg';
  /** Optional photo URL. Falls back to initials when null/undefined or on load error. */
  src?: string | null;
}

const SIZE: Record<NonNullable<AvatarProps['size']>, string> = {
  sm: 'h-8 w-8 text-xs',
  md: 'h-10 w-10 text-sm',
  lg: 'h-14 w-14 text-lg',
};

/** Returns 1–2 initial letters from a display name. */
export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  if (parts.length === 1) return parts[0]!.slice(0, 2).toUpperCase();
  return (parts[0]![0]! + parts[parts.length - 1]![0]!).toUpperCase();
}

/**
 * Solid avatar fills and the foreground token paired with each one.
 *
 * The token names are data as well as documentation: `contrast.test.ts` reads
 * this table and measures every pair in both themes. Keeping the class beside
 * the pair means the tested colours cannot drift from the colours rendered by
 * the component.
 */
export const AVATAR_PALETTE = [
  {
    background: 'primary',
    foreground: 'on-primary',
    className: 'bg-[var(--primary)] text-[var(--on-primary)]',
  },
  {
    background: 'accent',
    foreground: 'on-accent',
    className: 'bg-[var(--accent)] text-[var(--on-accent)]',
  },
  {
    background: 'metal-dark',
    foreground: 'on-primary',
    className: 'bg-[var(--metal-dark)] text-[var(--on-primary)]',
  },
  {
    background: 'gold',
    foreground: 'on-primary',
    className: 'bg-[var(--gold)] text-[var(--on-primary)]',
  },
  {
    background: 'metal',
    foreground: 'avatar-on-metal',
    className: 'bg-[var(--metal)] text-[var(--avatar-on-metal)]',
  },
  {
    background: 'bronze',
    foreground: 'avatar-on-bronze',
    className: 'bg-[var(--bronze)] text-[var(--avatar-on-bronze)]',
  },
] as const;

function tintFor(name: string): string {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) | 0;
  return AVATAR_PALETTE[Math.abs(h) % AVATAR_PALETTE.length]!.className;
}

export function Avatar({ name, size = 'md', src, className, ...props }: AvatarProps) {
  const [imgError, setImgError] = useState(false);
  useEffect(() => { setImgError(false); }, [src]);
  const showPhoto = !!src && !imgError;

  return (
    <div
      className={cn(
        'inline-flex items-center justify-center rounded-full select-none overflow-hidden',
        SIZE[size],
        !showPhoto && cn('font-sans font-semibold', tintFor(name)),
        className,
      )}
      aria-hidden
      {...props}
    >
      {showPhoto ? (
        <img
          src={src}
          alt=""
          className="h-full w-full object-cover"
          onError={() => setImgError(true)}
        />
      ) : (
        initials(name)
      )}
    </div>
  );
}

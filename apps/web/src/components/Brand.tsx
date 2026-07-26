import { cn } from '@/lib/utils';
import { brand } from '@/theme/tokens';

type BrandVariant = 'splash' | 'compact' | 'mono' | 'lockup' | 'mark';

interface BrandProps {
  variant?: BrandVariant;
  size?: number;
  label?: string;
  decorative?: boolean;
  className?: string;
}

/**
 * "The Coupon" wordmark + mark.
 *
 * variants:
 *   splash  - vertical mark + wordmark (login / join / welcome)
 *   lockup  - mark left + wordmark right
 *   compact - small header lockup
 *   mono    - short name in mono (misc)
 *   mark    - the ticket mark alone
 *
 * NOTE: this is a lean placeholder identity; the full visual rebrand is Batch 6.
 */

/** A simple coupon-ticket glyph (perforated stub) rendered inline as SVG. */
function CouponMark({ size, decorative, label }: { size: number; decorative: boolean; label: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      role={decorative ? 'presentation' : 'img'}
      aria-hidden={decorative ? true : undefined}
      aria-label={decorative ? undefined : label}
      className="text-primary"
    >
      <rect x="2.5" y="7" width="27" height="18" rx="3" className="fill-primary/15 stroke-primary" strokeWidth="1.5" />
      <line x1="20" y1="8" x2="20" y2="24" className="stroke-primary" strokeWidth="1.5" strokeDasharray="2 2.5" />
      <path d="M7 13.5h8M7 18.5h6" className="stroke-primary" strokeWidth="1.5" strokeLinecap="round" />
      <circle cx="24.5" cy="16" r="2" className="fill-primary" />
    </svg>
  );
}

export function Brand({
  variant = 'splash',
  size,
  label = brand.full,
  decorative = false,
  className,
}: BrandProps) {
  const markSize = size ?? 32;

  if (variant === 'mono') {
    return (
      <span
        className={cn(
          'font-mono font-semibold tracking-[0.3em] text-wordmark text-sm uppercase',
          className,
        )}
        aria-hidden={decorative ? true : undefined}
        aria-label={decorative ? undefined : label}
      >
        {brand.short}
      </span>
    );
  }

  if (variant === 'mark') {
    return (
      <span className={className}>
        <CouponMark size={markSize} decorative={decorative} label={label} />
      </span>
    );
  }

  if (variant === 'compact') {
    return (
      <span
        className={cn(
          'inline-flex items-center gap-2 font-mono font-semibold uppercase tracking-[0.2em] text-[11px] leading-none text-wordmark-h whitespace-nowrap select-none',
          className,
        )}
        aria-hidden={decorative ? true : undefined}
        aria-label={decorative ? undefined : label}
      >
        <CouponMark size={size ?? 22} decorative label={label} />
        <span>THE COUPON</span>
      </span>
    );
  }

  if (variant === 'lockup') {
    return (
      <div
        className={cn('flex items-center gap-4 select-none', className)}
        aria-hidden={decorative ? true : undefined}
        aria-label={decorative ? undefined : label}
      >
        <CouponMark size={size ?? 56} decorative label={label} />
        <p className="font-mono font-semibold uppercase tracking-[0.18em] text-2xl sm:text-3xl leading-none text-wordmark">
          THE COUPON
        </p>
      </div>
    );
  }

  // splash — vertical lockup: mark above the wordmark (login / join / welcome)
  return (
    <div
      className={cn('flex flex-col items-center text-center select-none gap-4', className)}
      aria-hidden={decorative ? true : undefined}
      aria-label={decorative ? undefined : label}
    >
      <CouponMark size={size ?? 68} decorative label={label} />
      <p className="font-mono font-semibold uppercase tracking-[0.18em] text-3xl sm:text-4xl leading-none text-wordmark">
        THE COUPON
      </p>
    </div>
  );
}

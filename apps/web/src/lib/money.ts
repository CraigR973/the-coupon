/**
 * Pay to pick (Batch 206, ADR 0009): pence as members read them, and back again.
 *
 * The API counts in whole pence everywhere, so the screens only ever convert at the edge.
 * A whole number of pounds drops its pence — the weekly fee reads "£1", not "£1.00" —
 * and anything else shows both places, so "£1.50" never becomes "£1.5".
 */
export function formatPence(pence: number): string {
  const sign = pence < 0 ? '−' : '';
  const abs = Math.abs(Math.round(pence));
  const pounds = Math.floor(abs / 100);
  const rest = abs % 100;
  const whole = pounds.toLocaleString('en-GB');
  return rest === 0 ? `${sign}£${whole}` : `${sign}£${whole}.${String(rest).padStart(2, '0')}`;
}

/**
 * Read what an organiser typed into a pounds field as pence, or `null` when it is not an
 * amount: blank, not a number, more than two decimal places, or a currency sign in the
 * wrong place. A leading `£` and surrounding spaces are forgiven, because that is what
 * people type.
 *
 * `allowNegative` is for adjustments, the one entry that can charge a member.
 */
export function parsePounds(input: string, { allowNegative = false } = {}): number | null {
  const cleaned = input.trim().replace(/^(-?)£/, '$1');
  const pattern = allowNegative ? /^-?\d+(\.\d{1,2})?$/ : /^\d+(\.\d{1,2})?$/;
  if (!pattern.test(cleaned)) return null;
  const negative = cleaned.startsWith('-');
  const [pounds, decimals = ''] = cleaned.replace('-', '').split('.');
  const pence = Number(pounds) * 100 + Number(decimals.padEnd(2, '0'));
  if (!Number.isSafeInteger(pence)) return null;
  return negative ? -pence : pence;
}

/** Pence as a pounds field shows them for editing: "1", "1.50". */
export function penceToInput(pence: number | null | undefined): string {
  if (pence === null || pence === undefined) return '';
  return formatPence(pence).replace('£', '').replace(/,/g, '');
}

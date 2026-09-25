import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Download, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { ApiError, apiFetch } from '../lib/api';
import { useAuth } from '../contexts/AuthContext';
import { PinInput } from './PinInput';

/**
 * A member's own data: take a copy of it, or delete the account (Batch 136).
 *
 * Deletion asks for the PIN again because it cannot be undone. A wrong PIN comes back as
 * 403 rather than 401 — `apiFetch` reads any 401 as an expired session and signs the
 * member out, which is the wrong answer to a typo here of all places. A refusal (the
 * only admin of a league others play in, or a site admin) is shown in the panel, where
 * the member is looking, rather than as a toast that disappears.
 */
export function YourDataSection() {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [downloading, setDownloading] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [pin, setPin] = useState('');
  const [deleting, setDeleting] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);

  async function download() {
    setDownloading(true);
    try {
      const data = await apiFetch<unknown>('/api/v1/me/export');
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `the-coupon-my-data-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Couldn't prepare your data. Try again in a moment.");
    } finally {
      setDownloading(false);
    }
  }

  async function deleteAccount(e: React.FormEvent) {
    e.preventDefault();
    if (pin.length !== 4) return;
    setDeleting(true);
    setRefusal(null);
    try {
      await apiFetch('/api/v1/me/delete', { method: 'POST', body: JSON.stringify({ pin }) });
      await logout();
      toast.success('Your account has been deleted.');
      navigate('/login', { replace: true });
    } catch (error) {
      setPin('');
      setRefusal(
        error instanceof ApiError && (error.status === 403 || error.status === 409)
          ? error.detail
          : "Couldn't delete your account. Try again in a moment.",
      );
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="space-y-3">
        <p className="text-sm font-sans text-text-secondary">
          Download everything The Coupon holds about you — your profile, your leagues and every
          pick — as a file.
        </p>
        <button
          type="button"
          onClick={download}
          disabled={downloading}
          className="inline-flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-sans border border-border bg-surface-elevated text-text-primary hover:bg-surface disabled:opacity-50 transition-colors"
        >
          <Download size={14} aria-hidden />
          {downloading ? 'Preparing…' : 'Download my data'}
        </button>
      </div>

      <div className="space-y-3 border-t border-border pt-5">
        {!confirming ? (
          <button
            type="button"
            onClick={() => setConfirming(true)}
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-sans border border-error/40 text-error hover:bg-surface-elevated transition-colors"
          >
            <Trash2 size={14} aria-hidden />
            Delete my account
          </button>
        ) : (
          <form onSubmit={deleteAccount} className="space-y-3">
            <p className="text-sm font-sans text-text-secondary">
              This can't be undone. Your name, PIN, devices and settings are removed straight away and
              you're signed out. Your past picks stay in each league's tables as "Former member", so
              everyone else's standings still add up.
            </p>
            <div className="space-y-1">
              <p className="text-sm font-sans text-text-primary">Enter your PIN to confirm</p>
              <PinInput value={pin} onChange={setPin} maxLength={4} label="Confirm PIN" />
            </div>
            {refusal && (
              <p role="alert" className="text-sm font-sans text-error">
                {refusal}
              </p>
            )}
            <div className="flex flex-wrap gap-2">
              <button
                type="submit"
                disabled={pin.length !== 4 || deleting}
                // Error *text* on the plain surface, not white on an error fill and not on a red
                // tint: white on the dark theme's --error is 3.76:1 and --error-ink on a 10%
                // tint is 4.30:1 in the light theme, both under AA. On the surface it is 5.02:1
                // (light) and 5.62:1 (dark).
                className="inline-flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-sans border border-error/60 text-error hover:bg-surface-elevated disabled:opacity-50 transition-colors"
              >
                <Trash2 size={14} aria-hidden />
                {deleting ? 'Deleting…' : 'Delete my account permanently'}
              </button>
              <button
                type="button"
                onClick={() => {
                  setConfirming(false);
                  setPin('');
                  setRefusal(null);
                }}
                className="px-3 py-1.5 rounded-md text-sm font-sans border border-border text-text-primary hover:bg-surface-elevated transition-colors"
              >
                Cancel
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

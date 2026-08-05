import { useCallback, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Bell, BellOff, Download, Send, Check, Sun, Moon, Monitor, Info, Globe, KeyRound, Percent } from 'lucide-react';
import { PinInput } from '../components/PinInput';
import { toast } from 'sonner';
import { apiFetch } from '../lib/api';
import { formatOdds } from '../lib/coupon';
import type { OddsFormat } from '../lib/types';
import { usePushSubscription } from '../hooks/usePushSubscription';
import { useInstallPrompt } from '../hooks/useInstallPrompt';
import { Skeleton } from '../components/ui/skeleton';
import { useTheme } from '../contexts/ThemeContext';
import { useAuth } from '../contexts/AuthContext';
import { cn } from '../lib/utils';
import { PageHeader } from '../components/PageHeader';

// ── Types ─────────────────────────────────────────────────────────────────────

interface NotificationPreferences {
  global_mute: boolean;
  quiet_hours_start: string | null;
  quiet_hours_end: string | null;
}

// ── Sub-components ────────────────────────────────────────────────────────────

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-5">
      <h2 className="text-base font-semibold text-text-primary font-sans tracking-tight mb-4">{title}</h2>
      {children}
    </div>
  );
}

function Toggle({
  checked,
  onChange,
  label,
  disabled = false,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <label className="flex items-center justify-between cursor-pointer py-2">
      <span className="text-sm font-sans text-text-primary">{label}</span>
      <button
        role="switch"
        aria-checked={checked}
        aria-label={label}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary ${
          checked ? 'bg-primary' : 'bg-border'
        } ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
      >
        <span
          className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
            checked ? 'translate-x-6' : 'translate-x-1'
          }`}
        />
      </button>
    </label>
  );
}

// ── Push notifications section ────────────────────────────────────────────────

function PushSection() {
  const { permission, isSubscribed, isLoading, subscribe, unsubscribe } = usePushSubscription();
  const [testing, setTesting] = useState(false);

  const handleTest = async () => {
    setTesting(true);
    try {
      await apiFetch('/api/v1/push/test', { method: 'POST' });
      toast.success('Test notification sent — check your device');
    } catch {
      toast.error('Failed to send test notification');
    } finally {
      setTesting(false);
    }
  };

  const notSupported =
    typeof window !== 'undefined' &&
    (!('serviceWorker' in navigator) || !('PushManager' in window));

  if (notSupported) {
    return (
      <p className="text-sm text-text-muted font-sans">
        Push notifications are not supported in this browser.
      </p>
    );
  }

  if (permission === 'denied') {
    const ua = typeof navigator !== 'undefined' ? navigator.userAgent : '';
    const isIos = /iPhone|iPad|iPod/.test(ua);
    const isChrome = /Chrome/.test(ua) && !/Edg|OPR/.test(ua);
    const hint = isIos
      ? 'Go to iOS Settings → Safari → Notifications and allow this site.'
      : isChrome
        ? 'Click the lock icon in the address bar, set Notifications to "Allow", then reload.'
        : 'Open your browser settings and allow notifications for this site.';
    return (
      <div className="rounded-md bg-warning/10 border border-warning/30 px-4 py-3 space-y-1">
        <p className="text-sm font-sans font-medium text-warning">Notifications blocked</p>
        <p className="text-xs font-sans text-text-secondary">{hint}</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-sans text-text-primary">
          {isSubscribed ? 'Notifications enabled' : 'Notifications disabled'}
        </p>
        <button
          onClick={isSubscribed ? unsubscribe : subscribe}
          disabled={isLoading}
          className="flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-sans transition-colors border border-border hover:bg-surface-elevated disabled:opacity-50"
        >
          {isSubscribed ? <BellOff size={14} /> : <Bell size={14} />}
          {isSubscribed ? 'Unsubscribe' : 'Subscribe'}
        </button>
      </div>
      {isSubscribed && (
        <button
          onClick={handleTest}
          disabled={testing}
          data-testid="test-push-btn"
          className="flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-sans border border-border hover:bg-surface-elevated disabled:opacity-50 transition-colors"
        >
          <Send size={14} />
          {testing ? 'Sending…' : 'Send test notification'}
        </button>
      )}
    </div>
  );
}

// ── PWA install section ───────────────────────────────────────────────────────

function InstallSection() {
  const { canInstall, isInstalled, isIosSafari, prompt } = useInstallPrompt();

  if (isInstalled) {
    return (
      <div className="flex items-center gap-2 text-sm text-text-secondary font-sans">
        <Check size={16} className="text-primary" />
        App is installed
      </div>
    );
  }

  if (isIosSafari) {
    return (
      <p className="text-sm text-text-secondary font-sans">
        Tap <strong>⋯</strong> → <strong>Share</strong> → <strong>Add to Home Screen</strong>.
      </p>
    );
  }

  if (!canInstall) {
    return (
      <p className="text-sm text-text-muted font-sans">
        Use your browser's install option if supported.
      </p>
    );
  }

  return (
    <button
      onClick={() => void prompt()}
      className="flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-sans border border-border hover:bg-surface-elevated transition-colors"
    >
      <Download size={14} />
      Install app
    </button>
  );
}

// ── Preferences section ───────────────────────────────────────────────────────

function PreferencesSection() {
  const queryClient = useQueryClient();

  const { data: prefs, isLoading } = useQuery<NotificationPreferences>({
    queryKey: ['notification-preferences'],
    queryFn: () => apiFetch('/api/v1/notifications/preferences'),
  });

  const mutation = useMutation({
    mutationFn: (patch: Partial<NotificationPreferences>) =>
      apiFetch<NotificationPreferences>('/api/v1/notifications/preferences', {
        method: 'PATCH',
        body: JSON.stringify(patch),
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData(['notification-preferences'], updated);
    },
    onError: () => toast.error('Failed to save preferences'),
  });

  const update = useCallback(
    (patch: Partial<NotificationPreferences>) => mutation.mutate(patch),
    [mutation],
  );

  if (isLoading || !prefs) {
    return (
      <div className="space-y-3" aria-label="Loading preferences">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </div>
    );
  }

  const muted = prefs.global_mute;

  return (
    <div className="space-y-1">
      <Toggle
        checked={!muted}
        onChange={(v) => update({ global_mute: !v })}
        label="Enable all notifications"
      />

      <div className="pt-3 border-t border-border">
        <p className="text-sm font-sans text-text-secondary mb-2">Quiet hours (no notifications)</p>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-sm font-sans text-text-secondary">
            From
            <input
              type="time"
              value={prefs.quiet_hours_start ?? ''}
              disabled={muted}
              onChange={(e) => update({ quiet_hours_start: e.target.value || '' })}
              className="rounded-md border border-border bg-surface-elevated px-2 py-1 text-sm font-mono text-text-primary disabled:opacity-50"
            />
          </label>
          <label className="flex items-center gap-2 text-sm font-sans text-text-secondary">
            To
            <input
              type="time"
              value={prefs.quiet_hours_end ?? ''}
              disabled={muted}
              onChange={(e) => update({ quiet_hours_end: e.target.value || '' })}
              className="rounded-md border border-border bg-surface-elevated px-2 py-1 text-sm font-mono text-text-primary disabled:opacity-50"
            />
          </label>
          {(prefs.quiet_hours_start || prefs.quiet_hours_end) && (
            <button
              onClick={() => update({ quiet_hours_start: '', quiet_hours_end: '' })}
              disabled={muted}
              className="text-xs text-text-muted hover:text-text-primary disabled:opacity-50"
            >
              Clear
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Change PIN section ────────────────────────────────────────────────────────

function ChangePinSection() {
  const [currentPin, setCurrentPin] = useState('');
  const [newPin, setNewPin] = useState('');
  const [saving, setSaving] = useState(false);

  const canSubmit = currentPin.length === 4 && newPin.length === 4 && currentPin !== newPin;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setSaving(true);
    try {
      await apiFetch('/api/v1/auth/me/pin', {
        method: 'PUT',
        body: JSON.stringify({ current_pin: currentPin, new_pin: newPin }),
      });
      setCurrentPin('');
      setNewPin('');
      toast.success('PIN changed successfully');
    } catch {
      toast.error('Current PIN is incorrect or request failed');
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="flex items-center gap-2 text-sm text-text-secondary font-sans">
        <KeyRound size={14} aria-hidden />
        <span>Enter your current PIN, then choose a new 4-digit PIN.</span>
      </div>
      <div className="space-y-1">
        <label className="text-sm font-sans text-text-primary">Current PIN</label>
        <PinInput value={currentPin} onChange={setCurrentPin} maxLength={4} />
      </div>
      <div className="space-y-1">
        <label className="text-sm font-sans text-text-primary">New PIN</label>
        <PinInput value={newPin} onChange={setNewPin} maxLength={4} />
      </div>
      {currentPin.length === 4 && newPin.length === 4 && currentPin === newPin && (
        <p className="text-xs text-error font-sans">New PIN must differ from current PIN.</p>
      )}
      <button
        type="submit"
        disabled={!canSubmit || saving}
        className="inline-flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-sans border border-border bg-primary text-white hover:bg-primary/90 disabled:opacity-50 transition-colors"
      >
        <Check size={14} aria-hidden />
        {saving ? 'Saving…' : 'Change PIN'}
      </button>
    </form>
  );
}

// ── Theme switch ──────────────────────────────────────────────────────────────

function AppearanceSection() {
  const { mode, setMode } = useTheme();
  const options = [
    { value: 'light' as const, label: 'Light', Icon: Sun },
    { value: 'dark' as const, label: 'Dark', Icon: Moon },
    { value: 'system' as const, label: 'System', Icon: Monitor },
  ];
  return (
    <div>
      <p className="text-sm text-text-secondary font-sans mb-3">
        Choose how the app looks. System follows your device&apos;s dark-mode setting.
      </p>
      <div
        role="radiogroup"
        aria-label="Theme"
        className="inline-flex w-full max-w-sm gap-1 p-1 rounded-md bg-surface-elevated border border-border"
      >
        {options.map(({ value, label, Icon }) => {
          const active = mode === value;
          return (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => setMode(value)}
              className={cn(
                'flex-1 inline-flex items-center justify-center gap-2 px-3 py-2 rounded-sm text-sm font-medium font-sans transition-colors tap-target press-down focus-visible:outline-none focus-visible:shadow-glow',
                active
                  ? 'bg-surface text-text-primary shadow-sm'
                  : 'text-text-secondary hover:text-text-primary',
              )}
            >
              <Icon className="h-4 w-4" aria-hidden />
              {label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ── Timezone section ──────────────────────────────────────────────────────────

const TIMEZONES = [
  'Europe/London',
  'Europe/Dublin',
  'Europe/Paris',
  'Europe/Berlin',
  'Europe/Madrid',
  'Europe/Rome',
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'America/Toronto',
  'America/Vancouver',
  'America/Mexico_City',
  'Australia/Sydney',
  'Australia/Melbourne',
  'Pacific/Auckland',
  'UTC',
];

function TimezoneSection() {
  const { player, updatePlayer } = useAuth();
  const [tz, setTz] = useState(player?.timezone ?? 'UTC');
  const [saving, setSaving] = useState(false);

  const isDirty = tz !== player?.timezone;

  async function handleSave() {
    setSaving(true);
    try {
      await apiFetch('/api/v1/auth/me', {
        method: 'PATCH',
        body: JSON.stringify({ timezone: tz }),
      });
      updatePlayer({ timezone: tz });
      toast.success('Timezone updated');
    } catch {
      toast.error('Failed to update timezone');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-sm text-text-secondary font-sans">
        <Globe size={14} aria-hidden />
        <span>Used for kickoff times and notification scheduling.</span>
      </div>
      <select
        id="timezone"
        value={tz}
        onChange={(e) => setTz(e.target.value)}
        aria-label="Timezone"
        className="flex h-10 w-full items-center rounded-md border border-border bg-surface px-3 py-2 text-sm text-text-primary font-sans focus:outline-none focus:ring-2 focus:ring-primary"
      >
        {TIMEZONES.map((t) => (
          <option key={t} value={t}>
            {t.replace(/_/g, ' ')}
          </option>
        ))}
      </select>
      {isDirty && (
        <button
          type="button"
          disabled={saving}
          onClick={handleSave}
          className="inline-flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-sans border border-border bg-primary text-white hover:bg-primary/90 disabled:opacity-50 transition-colors"
        >
          <Check size={14} aria-hidden />
          {saving ? 'Saving…' : 'Save timezone'}
        </button>
      )}
    </div>
  );
}

// ── Odds format section ───────────────────────────────────────────────────────

function OddsFormatSection() {
  const { player, updatePlayer } = useAuth();
  const current: OddsFormat = player?.oddsFormat ?? 'decimal';
  const [saving, setSaving] = useState<OddsFormat | null>(null);

  const options: Array<{ value: OddsFormat; label: string; sample: string }> = [
    { value: 'decimal', label: 'Decimal', sample: formatOdds(2.5, 'decimal') },
    { value: 'fractional', label: 'Fractional', sample: formatOdds(2.5, 'fractional') },
  ];

  async function choose(value: OddsFormat) {
    if (value === current) return;
    setSaving(value);
    try {
      await apiFetch('/api/v1/auth/me', {
        method: 'PATCH',
        body: JSON.stringify({ odds_format: value }),
      });
      updatePlayer({ oddsFormat: value });
      toast.success(`Showing ${value} odds`);
    } catch {
      toast.error('Failed to update odds format');
    } finally {
      setSaving(null);
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-sm text-text-secondary font-sans">
        <Percent size={14} aria-hidden />
        <span>How prices are shown. Points always come from the decimal price.</span>
      </div>
      <div
        role="radiogroup"
        aria-label="Odds format"
        className="inline-flex w-full max-w-sm gap-1 p-1 rounded-md bg-surface-elevated border border-border"
      >
        {options.map(({ value, label, sample }) => {
          const active = current === value;
          return (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={active}
              disabled={saving !== null}
              onClick={() => void choose(value)}
              className={cn(
                'flex-1 inline-flex flex-col items-center justify-center gap-0.5 px-3 py-2 rounded-sm text-sm font-medium font-sans transition-colors tap-target press-down focus-visible:outline-none focus-visible:shadow-glow disabled:opacity-60',
                active
                  ? 'bg-surface text-text-primary shadow-sm'
                  : 'text-text-secondary hover:text-text-primary',
              )}
            >
              {label}
              <span className="font-mono text-[10px] tabular-nums text-text-muted">{sample}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function SettingsPage() {
  return (
    <div className="max-w-xl space-y-6">
      <PageHeader title="Settings" eyebrow="Account & device" />

      <SectionCard title="Change PIN">
        <ChangePinSection />
      </SectionCard>

      <SectionCard title="Timezone">
        <TimezoneSection />
      </SectionCard>

      <SectionCard title="Odds format">
        <OddsFormatSection />
      </SectionCard>

      <SectionCard title="Appearance">
        <AppearanceSection />
      </SectionCard>

      <SectionCard title="Push Notifications">
        <PushSection />
      </SectionCard>

      <SectionCard title="Notification Preferences">
        <PreferencesSection />
      </SectionCard>

      <SectionCard title="Install App">
        <InstallSection />
      </SectionCard>

      <Link
        to="/about"
        className="flex items-center gap-2 text-sm font-sans text-text-muted hover:text-text-primary transition-colors group"
      >
        <Info size={14} className="group-hover:text-primary transition-colors" aria-hidden />
        About &amp; scoring rules
      </Link>
    </div>
  );
}

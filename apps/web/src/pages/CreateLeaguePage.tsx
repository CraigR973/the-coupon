import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';
import { dropStaleMemberships } from '@/lib/leagues';
import type { LeagueSummary, PickMarket, SlateWindow } from '@/lib/types';
import { ALL_MARKETS, hhmmToMinutes, minutesToHHMM, SATURDAY_3PM_WINDOW, WEEKDAYS } from '@/lib/leagueConfig';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { PageHeader } from '@/components/PageHeader';

const SELECT_CLASS =
  'flex h-10 w-full items-center rounded-md border border-border bg-surface px-3 py-2 ' +
  'text-sm text-text-primary font-sans focus:outline-none focus:ring-2 focus:ring-primary';

export function CreateLeaguePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [privacy, setPrivacy] = useState<'public_open' | 'public_request' | 'private'>('public_open');
  const [maxMembers, setMaxMembers] = useState('');
  const [window, setWindow] = useState<SlateWindow>(SATURDAY_3PM_WINDOW);
  const [markets, setMarkets] = useState<Set<PickMarket>>(new Set(ALL_MARKETS.map((m) => m.value)));
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  function toggleMarket(market: PickMarket) {
    setMarkets((prev) => {
      const next = new Set(prev);
      if (next.has(market)) next.delete(market);
      else next.add(market);
      return next;
    });
  }

  function updateWindow(patch: Partial<SlateWindow>) {
    setWindow((prev) => ({ ...prev, ...patch }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    if (markets.size === 0) {
      setError('Offer at least one market.');
      return;
    }
    setIsLoading(true);
    try {
      const body: Record<string, unknown> = {
        name: name.trim(),
        privacy,
        slate_start_weekday: window.start_weekday,
        slate_start_minute: window.start_minute,
        slate_end_weekday: window.end_weekday,
        slate_end_minute: window.end_minute,
        lock_offset_minutes: window.lock_offset_minutes,
        offered_markets: ALL_MARKETS.map((m) => m.value).filter((v) => markets.has(v)),
      };
      if (description.trim()) body.description = description.trim();
      if (maxMembers) body.max_members = Number(maxMembers);

      const league = await apiFetch<LeagueSummary>('/api/v1/leagues', {
        method: 'POST',
        body: JSON.stringify(body),
      });
      dropStaleMemberships(queryClient);
      navigate(`/leagues/${league.slug}`, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create league');
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <PageHeader title="Create a League" />

      <form onSubmit={handleSubmit} className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">League details</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="space-y-1">
                <Label htmlFor="name">League name</Label>
                <Input
                  id="name"
                  required
                  maxLength={30}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Saturday crew"
                />
              </div>

              <div className="space-y-1">
                <Label htmlFor="description">Description (optional)</Label>
                <Input
                  id="description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="A quick tagline for your league"
                />
              </div>

              <div className="space-y-1">
                <Label htmlFor="privacy">Privacy</Label>
                <select
                  id="privacy"
                  value={privacy}
                  onChange={(e) => setPrivacy(e.target.value as typeof privacy)}
                  className={SELECT_CLASS}
                >
                  <option value="public_open">Open — anyone can join instantly</option>
                  <option value="public_request">Request — anyone can request to join</option>
                  <option value="private">Private — invite only</option>
                </select>
              </div>

              <div className="space-y-1">
                <Label htmlFor="maxMembers">Max members (optional, 2–50)</Label>
                <Input
                  id="maxMembers"
                  type="number"
                  min={2}
                  max={50}
                  value={maxMembers}
                  onChange={(e) => setMaxMembers(e.target.value)}
                  placeholder="Leave blank for default (15)"
                />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Fixture window</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-xs font-sans text-text-muted">
              When the slate runs. Defaults to the Saturday 3pm kick-offs — change it any time in
              settings.
            </p>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label htmlFor="startDay">Opens — day</Label>
                <select
                  id="startDay"
                  value={window.start_weekday}
                  onChange={(e) => updateWindow({ start_weekday: Number(e.target.value) })}
                  className={SELECT_CLASS}
                >
                  {WEEKDAYS.map((d) => (
                    <option key={d.value} value={d.value}>
                      {d.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1">
                <Label htmlFor="startTime">Opens — time</Label>
                <Input
                  id="startTime"
                  type="time"
                  value={minutesToHHMM(window.start_minute)}
                  onChange={(e) =>
                    updateWindow({ start_minute: hhmmToMinutes(e.target.value, window.start_minute) })
                  }
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="endDay">Closes — day</Label>
                <select
                  id="endDay"
                  value={window.end_weekday}
                  onChange={(e) => updateWindow({ end_weekday: Number(e.target.value) })}
                  className={SELECT_CLASS}
                >
                  {WEEKDAYS.map((d) => (
                    <option key={d.value} value={d.value}>
                      {d.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1">
                <Label htmlFor="endTime">Closes — time</Label>
                <Input
                  id="endTime"
                  type="time"
                  value={minutesToHHMM(window.end_minute)}
                  onChange={(e) =>
                    updateWindow({ end_minute: hhmmToMinutes(e.target.value, window.end_minute) })
                  }
                />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Markets offered</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <p className="text-xs font-sans text-text-muted">
              Which markets members pick from. Every UK competition is included by default — narrow
              that later in settings.
            </p>
            {ALL_MARKETS.map((m) => (
              <label
                key={m.value}
                className="flex items-center gap-3 rounded-md border border-border bg-surface px-3 py-2 text-sm font-sans text-text-primary"
              >
                <input
                  type="checkbox"
                  className="h-4 w-4 accent-primary"
                  checked={markets.has(m.value)}
                  onChange={() => toggleMarket(m.value)}
                />
                <span>{m.label}</span>
              </label>
            ))}
          </CardContent>
        </Card>

        {error && <p role="alert" className="text-xs text-error font-sans">{error}</p>}

        <div className="flex gap-3">
          <Button type="button" variant="outline" onClick={() => navigate(-1)} className="flex-1">
            Cancel
          </Button>
          <Button type="submit" disabled={isLoading} className="flex-1">
            {isLoading ? 'Creating…' : 'Create league'}
          </Button>
        </div>
      </form>
    </div>
  );
}

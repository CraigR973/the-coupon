import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { apiFetch, DEFAULT_LEAGUE_SLUG } from '@/lib/api';
import type {
  AdHocGameweekResult,
  CompetitionCatalogue,
  CompetitionRef,
  LeagueSummary,
  PickMarket,
  PickScope,
  SlateWindow,
} from '@/lib/types';
import {
  ALL_MARKETS,
  hhmmToMinutes,
  minutesToHHMM,
  SATURDAY_3PM_WINDOW,
  WEEKDAYS,
} from '@/lib/leagueConfig';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Toggle } from '@/components/ui/toggle';
import { PageHeader } from '@/components/PageHeader';

const SELECT_CLASS =
  'flex h-10 w-full items-center rounded-md border border-border bg-surface px-3 py-2 ' +
  'text-sm text-text-primary font-sans focus:outline-none focus:ring-2 focus:ring-primary';

export function LeagueSettingsPage() {
  const { slug = DEFAULT_LEAGUE_SLUG } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: league } = useQuery<LeagueSummary>({
    queryKey: ['league', slug],
    queryFn: () => apiFetch<LeagueSummary>(`/api/v1/leagues/${slug}`),
  });

  // The competition picker's catalogue — admin-only, and the provider memoises it, so
  // opening settings costs no upstream request on the common path.
  const { data: catalogue } = useQuery<CompetitionCatalogue>({
    queryKey: ['league', slug, 'competitions'],
    queryFn: () => apiFetch<CompetitionCatalogue>(`/api/v1/leagues/${slug}/competitions`),
  });

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [privacy, setPrivacy] = useState<'public_open' | 'public_request' | 'private'>('public_open');
  const [maxMembers, setMaxMembers] = useState('');
  const [pickScope, setPickScope] = useState<PickScope>('selection');
  const [window, setWindow] = useState<SlateWindow>(SATURDAY_3PM_WINDOW);
  const [markets, setMarkets] = useState<Set<PickMarket>>(new Set(ALL_MARKETS.map((m) => m.value)));
  const [allUk, setAllUk] = useState(true);
  const [selectedSlugs, setSelectedSlugs] = useState<Set<string>>(new Set());
  const [adHocDate, setAdHocDate] = useState('');
  // Once the admin touches the competition controls, a late-arriving (or refetched)
  // catalogue must not overwrite their in-progress choice.
  const catalogueTouched = useRef(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isCreatingRound, setIsCreatingRound] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState('');

  useEffect(() => {
    if (league) {
      setName(league.name);
      setDescription(league.description ?? '');
      setPrivacy(league.privacy);
      setMaxMembers(league.max_members?.toString() ?? '');
      setPickScope(league.pick_scope ?? 'selection');
      if (league.slate_window) setWindow(league.slate_window);
      if (league.offered_markets?.length) setMarkets(new Set(league.offered_markets));
    }
  }, [league]);

  useEffect(() => {
    if (catalogue && !catalogueTouched.current) {
      setAllUk(catalogue.all_uk);
      setSelectedSlugs(new Set(catalogue.selected.map((c) => c.slug)));
    }
  }, [catalogue]);

  // The choosable competitions: what the provider carries, unioned with any stored
  // selection (so a competition dropped from the provider's list still shows as ticked).
  const competitionOptions = useMemo<CompetitionRef[]>(() => {
    const bySlug = new Map<string, CompetitionRef>();
    for (const c of catalogue?.available ?? []) bySlug.set(c.slug, c);
    for (const c of catalogue?.selected ?? []) if (!bySlug.has(c.slug)) bySlug.set(c.slug, c);
    return [...bySlug.values()].sort((a, b) => a.name.localeCompare(b.name));
  }, [catalogue]);

  function toggleMarket(market: PickMarket) {
    setMarkets((prev) => {
      const next = new Set(prev);
      if (next.has(market)) next.delete(market);
      else next.add(market);
      return next;
    });
  }

  function toggleCompetition(slug: string) {
    catalogueTouched.current = true;
    setSelectedSlugs((prev) => {
      const next = new Set(prev);
      if (next.has(slug)) next.delete(slug);
      else next.add(slug);
      return next;
    });
  }

  function setAllUkTouched(next: boolean) {
    catalogueTouched.current = true;
    setAllUk(next);
  }

  function updateWindow(patch: Partial<SlateWindow>) {
    setWindow((prev) => ({ ...prev, ...patch }));
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (markets.size === 0) {
      toast.error('Offer at least one market.');
      return;
    }
    const competitions = allUk
      ? null
      : competitionOptions.filter((c) => selectedSlugs.has(c.slug)).map((c) => ({ ...c }));
    if (competitions !== null && competitions.length === 0) {
      toast.error('Pick at least one competition, or switch on “All UK leagues”.');
      return;
    }

    setIsSaving(true);
    try {
      const body: Record<string, unknown> = { name: name.trim(), privacy };
      if (description.trim()) body.description = description.trim();
      if (maxMembers) body.max_members = Number(maxMembers);
      body.pick_scope = pickScope;
      body.slate_start_weekday = window.start_weekday;
      body.slate_start_minute = window.start_minute;
      body.slate_end_weekday = window.end_weekday;
      body.slate_end_minute = window.end_minute;
      body.lock_offset_minutes = window.lock_offset_minutes;
      // Only the markets the game knows — a stale value in state cannot widen the enum.
      body.offered_markets = ALL_MARKETS.map((m) => m.value).filter((v) => markets.has(v));
      body.competitions = competitions;

      await apiFetch(`/api/v1/leagues/${slug}`, { method: 'PATCH', body: JSON.stringify(body) });
      toast.success('League settings saved');
      queryClient.invalidateQueries({ queryKey: ['league', slug] });
      queryClient.invalidateQueries({ queryKey: ['leagues', 'mine'] });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to save';
      toast.error(
        message.includes('PICK_SCOPE_CONFLICT')
          ? 'Two members already share a game this week — one of them must move before one-pick-per-match can be turned on.'
          : message,
      );
    } finally {
      setIsSaving(false);
    }
  }

  async function handleCreateRound() {
    if (!adHocDate) {
      toast.error('Choose a date for the round.');
      return;
    }
    setIsCreatingRound(true);
    try {
      const result = await apiFetch<AdHocGameweekResult>(`/api/v1/leagues/${slug}/gameweeks`, {
        method: 'POST',
        body: JSON.stringify({ starts_on: adHocDate }),
      });
      toast.success(
        `${result.created ? 'Round created' : 'Round refreshed'} — ${result.fixture_count} ${
          result.fixture_count === 1 ? 'fixture' : 'fixtures'
        }`,
      );
      setAdHocDate('');
      queryClient.invalidateQueries({ queryKey: ['gameweeks', slug] });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to create round';
      toast.error(
        message.includes('NO_FIXTURES')
          ? 'No fixtures found for that date in this league’s competitions.'
          : message,
      );
    } finally {
      setIsCreatingRound(false);
    }
  }

  async function handleDelete() {
    if (deleteConfirm !== league?.name) {
      toast.error('Type the league name exactly to confirm deletion');
      return;
    }
    setIsDeleting(true);
    try {
      await apiFetch(`/api/v1/leagues/${slug}`, { method: 'DELETE' });
      toast.success('League deleted');
      queryClient.invalidateQueries({ queryKey: ['leagues', 'mine'] });
      navigate('/leagues', { replace: true });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to delete');
      setIsDeleting(false);
    }
  }

  // Wait for the league before rendering the form: its data seeds every field, and
  // letting the admin edit an unseeded form would let a late load overwrite their input.
  if (!league) {
    return (
      <div className="max-w-lg mx-auto space-y-6">
        <PageHeader title="League Settings" back={{ to: `/leagues/${slug}`, label: 'Back' }} />
        <p className="text-sm text-text-muted font-sans">Loading…</p>
      </div>
    );
  }

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <PageHeader title="League Settings" back={{ to: `/leagues/${slug}`, label: 'Back' }} />

      <form onSubmit={handleSave} className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Details</CardTitle>
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
                />
              </div>

              <div className="space-y-1">
                <Label htmlFor="description">Description</Label>
                <Input
                  id="description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
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
                  <option value="public_open">Public — anyone can join instantly</option>
                  <option value="public_request">Public · request — anyone can request to join</option>
                  <option value="private">Private — invite only</option>
                </select>
              </div>

              <div className="space-y-1">
                <Label htmlFor="maxMembers">Max members (blank = unlimited)</Label>
                <Input
                  id="maxMembers"
                  type="number"
                  min={2}
                  max={500}
                  value={maxMembers}
                  onChange={(e) => setMaxMembers(e.target.value)}
                  placeholder="Unlimited"
                />
              </div>

              <div className="space-y-1">
                <Label htmlFor="pickScope">What a pick claims</Label>
                <select
                  id="pickScope"
                  value={pickScope}
                  onChange={(e) => setPickScope(e.target.value as PickScope)}
                  className={SELECT_CLASS}
                >
                  <option value="selection">One selection — others can take the same match</option>
                  <option value="fixture">The whole match — one member per game</option>
                </select>
                <p className="text-xs font-sans text-text-muted">
                  One member per game makes picks scarcer: it takes roughly five times more
                  fixtures to go round, so a {league?.max_members ?? 15}-member league needs at
                  least that many matches on the slate.
                </p>
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
              When this league’s slate runs. The default is the Saturday 3pm kick-offs; widen it
              to any range, such as Friday evening through Monday night.
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
            <div className="space-y-1">
              <Label htmlFor="lockOffset">Picks lock (minutes before it opens)</Label>
              <Input
                id="lockOffset"
                type="number"
                min={0}
                value={window.lock_offset_minutes}
                onChange={(e) =>
                  updateWindow({ lock_offset_minutes: Math.max(0, Number(e.target.value) || 0) })
                }
              />
            </div>
            <Button
              type="button"
              variant="outline"
              className="w-full"
              onClick={() => setWindow(SATURDAY_3PM_WINDOW)}
            >
              Reset to Saturday 3pm
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Markets offered</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <p className="text-xs font-sans text-text-muted">
              Which markets members can pick from. At least one is required.
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

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Competitions</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-sans text-text-primary">All UK leagues</p>
                <p className="text-xs font-sans text-text-muted">
                  Every British competition the odds source carries.
                </p>
              </div>
              <Toggle checked={allUk} onCheckedChange={setAllUkTouched} label="All UK leagues" />
            </div>

            {!allUk && (
              <div className="space-y-2">
                {competitionOptions.length === 0 ? (
                  <p className="text-xs font-sans text-text-muted">
                    Competitions appear here once the first slate has been fetched. Until then,
                    keep “All UK leagues” on.
                  </p>
                ) : (
                  competitionOptions.map((c) => (
                    <label
                      key={c.slug}
                      className="flex items-center gap-3 rounded-md border border-border bg-surface px-3 py-2 text-sm font-sans text-text-primary"
                    >
                      <input
                        type="checkbox"
                        className="h-4 w-4 accent-primary"
                        checked={selectedSlugs.has(c.slug)}
                        onChange={() => toggleCompetition(c.slug)}
                      />
                      <span>{c.name}</span>
                    </label>
                  ))
                )}
              </div>
            )}
          </CardContent>
        </Card>

        <Button type="submit" disabled={isSaving} className="w-full">
          {isSaving ? 'Saving…' : 'Save changes'}
        </Button>
      </form>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Add a one-off round</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-xs font-sans text-text-muted">
            Create a round on a date outside the usual cadence — Boxing Day, say. It uses this
            league’s window times and competitions on the date you choose.
          </p>
          <div className="space-y-1">
            <Label htmlFor="adHocDate">Round date</Label>
            <Input
              id="adHocDate"
              type="date"
              value={adHocDate}
              onChange={(e) => setAdHocDate(e.target.value)}
            />
          </div>
          <Button
            type="button"
            variant="outline"
            className="w-full"
            disabled={isCreatingRound}
            onClick={handleCreateRound}
          >
            {isCreatingRound ? 'Creating…' : 'Create round'}
          </Button>
        </CardContent>
      </Card>

      <Card className="border-error/30">
        <CardHeader>
          <CardTitle className="text-base text-error">Danger zone</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-text-secondary font-sans">
            To delete this league, type its name exactly: <strong>{league?.name}</strong>
          </p>
          <Input
            value={deleteConfirm}
            onChange={(e) => setDeleteConfirm(e.target.value)}
            placeholder="Type league name to confirm"
          />
          <Button
            variant="outline"
            className="w-full border-error/40 text-error hover:bg-error/10"
            disabled={isDeleting}
            onClick={handleDelete}
          >
            {isDeleting ? 'Deleting…' : 'Delete league'}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

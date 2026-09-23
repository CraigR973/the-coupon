"""Batch 128 — a shipment that applies a migration must carry a written way forward.

Production has no backup, no PITR and no durable dump (the owner's 2026-07-30 deferral),
and ``nixpacks.toml`` runs ``alembic upgrade head`` before uvicorn binds. So the moment a
revision lands, **the previous deployment stops being a rollback target** — that image
cannot resolve a revision it does not carry. ``STATUS.md`` recorded this four times as a
one-off before anyone noticed it was structural.

Two things hold the rule. ``check-migration-recovery.sh`` refuses the *shipment*, at
``/ship-prod`` step 1.7, reading the deployed revision from production's own
``/api/v1/health`` so a stale note about last time cannot satisfy it. And the last test
here refuses the *batch*, which is the half that matters: the plan has to be written while
somebody still knows why the migration is shaped the way it is, not at the upload.

That second half lives in a test rather than in ``check-closeout-safety.sh`` because that
script is a protected gate file — ``assert-quality-guardrails.sh`` refuses a batch that
edits the machinery judging it, and rightly. A test is the stronger place anyway: it runs
on every batch and in CI, not only at close-out.

Shell-level; no database.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3]
_CHECK = _ROOT / "scripts" / "check-migration-recovery.sh"
_RUNBOOKS = _ROOT / "docs" / "runbooks"
_VERSIONS = _ROOT / "migrations" / "versions"

#: A revision number far past anything real, so a stray file could never be mistaken for
#: one this project ships.
_FAKE = "0991"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(_CHECK), *args], capture_output=True, text=True, cwd=_ROOT, timeout=60
    )


@pytest.fixture
def plan() -> Iterator[Path]:
    """A recovery-plan path that does not exist yet and is removed afterwards."""
    path = _RUNBOOKS / f"migration-{_FAKE}-recovery.md"
    assert not path.exists(), "the fake revision collided with a real plan"
    yield path
    path.unlink(missing_ok=True)


def _usable_plan() -> str:
    body = "\n".join(f"line {n}: what happens if this is rolled back" for n in range(30))
    return f"# Forward recovery plan — migration {_FAKE}\n\n{body}\n"


def test_a_missing_plan_refuses_the_shipment(plan: Path) -> None:
    """The case the batch exists for."""
    result = _run("--plan-for", _FAKE)
    assert result.returncode == 1
    assert "no plan at" in result.stderr
    assert not plan.exists()


def test_a_stub_refuses_the_shipment_too(plan: Path) -> None:
    """A file that exists is not a plan. Three lines is a placeholder for one."""
    plan.write_text("# plan\n\nrollback: nope.\n")
    result = _run("--plan-for", _FAKE)
    assert result.returncode == 1
    assert "is a stub" in result.stderr


def test_a_plan_that_never_mentions_a_rollback_refuses_the_shipment(plan: Path) -> None:
    """Length is not substance. The rollback question is the one it exists to answer."""
    plan.write_text("# Forward recovery plan\n" + "\n".join(f"line {n}" for n in range(40)))
    result = _run("--plan-for", _FAKE)
    assert result.returncode == 1
    assert "never says what to do about a rollback" in result.stderr


def test_a_usable_plan_lets_the_shipment_through(plan: Path) -> None:
    """And says nothing while doing it — a gate that passes noisily gets ignored."""
    plan.write_text(_usable_plan())
    result = _run("--plan-for", _FAKE)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


def test_an_unknown_deployed_revision_is_not_treated_as_nothing_to_do() -> None:
    """The failure mode that would make this gate worse than useless.

    If the deployed revision cannot be established, the set of revisions this shipment
    would apply is unknown — which is not the same as empty. Exiting 0 there would wave
    through exactly the shipment this check exists to stop.
    """
    result = _run("--deployed", "0992")
    assert result.returncode == 2, result.stdout
    assert "CANNOT TELL" in result.stdout


def test_the_shipment_gate_passes_when_production_is_already_at_head() -> None:
    """The ordinary case: most shipments carry no migration at all."""
    head = sorted(path.name.split("_")[0] for path in _VERSIONS.glob("[0-9]*_*.py"))[-1]
    result = _run("--deployed", head)
    assert result.returncode == 0, result.stderr
    assert "applies no migration" in result.stdout


def test_every_revision_this_project_ships_past_016_can_be_named_by_the_gate() -> None:
    """The gate is worthless if it cannot parse the filenames it is pointed at.

    Revision files are ``NNN_slug.py`` and the gate takes everything before the first
    underscore. A future revision named differently would make the check silently see
    fewer revisions than exist, which reads exactly like a clean shipment.
    """
    revisions = [path.name.split("_")[0] for path in _VERSIONS.glob("[0-9]*_*.py")]
    assert revisions, "no revisions found where the gate looks for them"
    assert all(revision.isdigit() for revision in revisions), revisions
    assert len(set(revisions)) == len(revisions), "two files claim the same revision"


#: Where the convention starts. Revisions up to and including this one predate Batch 128;
#: their plans, where written, are sections of L4_PRODUCTION_INFRASTRUCTURE.md, and they
#: are long since deployed. Nothing is being backfilled — see docs/runbooks/migrations.md.
_CONVENTION_STARTS_AFTER = "025"


def test_every_revision_added_since_the_convention_carries_its_recovery_plan() -> None:
    """The batch-level half of the rule, and the one that has to hold.

    A plan written at the shipment is written by whoever is shipping, about a migration
    somebody else shaped, under time pressure. Written by the batch, it is written by the
    person who knows why the revision does what it does. This is what makes that happen:
    add a revision past 025 without ``docs/runbooks/migration-NNN-recovery.md`` and the
    gate goes red on your own branch, long before anything reaches production.
    """
    missing = []
    for path in sorted(_VERSIONS.glob("[0-9]*_*.py")):
        revision = path.name.split("_")[0]
        if revision <= _CONVENTION_STARTS_AFTER:
            continue
        result = _run("--plan-for", revision)
        if result.returncode != 0:
            missing.append(result.stderr.strip())

    assert not missing, (
        "a revision was added with no usable forward recovery plan:\n"
        + "\n".join(missing)
        + "\n\nProduction has no restore point and applies migrations on boot, so the "
        "shipment carrying this removes the rollback target until a later one applies "
        "none. docs/runbooks/migrations.md says what the plan has to answer."
    )

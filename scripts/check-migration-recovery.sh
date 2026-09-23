#!/usr/bin/env bash
# Batch 128 — refuse a shipment that applies a migration with nothing written down.
#
# Production has no backup, no PITR and no durable dump (owner's 2026-07-30 deferral),
# and `nixpacks.toml` runs `alembic upgrade head` on boot before uvicorn binds. So the
# moment a shipment applies a revision, **the previous deployment stops being a rollback
# target**: that image cannot resolve a revision it does not carry. STATUS.md has recorded
# this four times as a one-off. It is structural, and the only thing that makes it
# survivable is a plan written before the upload rather than during the incident.
#
#   scripts/check-migration-recovery.sh                 # reads the deployed revision live
#   scripts/check-migration-recovery.sh --deployed 024  # or take it as given
#
# Exit 0: nothing to apply, or every applied revision has a plan.
# Exit 1: a revision would be applied with no usable plan. Do not upload.
# Exit 2: the deployed revision could not be established. Do not upload either — an
#         unknown starting point is not the same as an empty diff.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSIONS="$ROOT/migrations/versions"
RUNBOOKS="$ROOT/docs/runbooks"
HEALTH="https://api-production-109b1.up.railway.app/api/v1/health"

#: A plan shorter than this is a placeholder. The shipped 016 plan is 92 lines; the
#: bar is deliberately well under that, so it refuses a stub without dictating a length.
MIN_PLAN_LINES=25

#: Statements that make the previous image unable to boot, or unable to read what it
#: wrote. Expand-then-contract exists to keep these out of the shipment that needs the
#: rollback: add the new shape, ship it, migrate, and only contract once no running image
#: depends on the old one. Found here, they are reported — the plan must answer for them.
#:
#: Scanned in `upgrade()` only. Every `downgrade()` drops what its upgrade created, so
#: scanning the whole file would flag all 25 revisions and mean nothing.
#: `alter_column` is in the list because it is where a column becomes NOT NULL or
#: changes type — both of which the previous image can meet as a write failure. A
#: `create_table` whose new columns are NOT NULL is not contracting and is not listed.
CONTRACTING='op\.(drop_column|drop_table|drop_constraint|drop_index|rename_table|alter_column)'

#: The one definition of "this plan is usable", called from here and from
#: check-closeout-safety.sh. Two copies of this rule would drift, and the copy that
#: drifted looser would be the one nobody noticed.
#: Prints the reason and returns non-zero when the plan will not do.
plan_problem() {
  # Split, not one `local`: bash 3.2 evaluates the whole statement before any of its
  # assignments take effect, so `plan` would interpolate an unset `revision` — which
  # under `set -u` is an error, not an empty string.
  local revision="$1"
  local plan="$RUNBOOKS/migration-$revision-recovery.md"
  local lines
  if [[ ! -f "$plan" ]]; then
    echo "no plan at docs/runbooks/migration-$revision-recovery.md"
    return 1
  fi
  lines="$(wc -l < "$plan" | tr -d ' ')"
  if (( lines < MIN_PLAN_LINES )); then
    echo "the plan at docs/runbooks/migration-$revision-recovery.md is a stub ($lines lines)"
    return 1
  fi
  if ! grep -qi 'roll' "$plan"; then
    echo "docs/runbooks/migration-$revision-recovery.md never says what to do about a rollback"
    return 1
  fi
  echo "$lines"
  return 0
}

deployed=""
while (( $# )); do
  case "$1" in
    --deployed) deployed="${2:-}"; shift 2 ;;
    # Used by check-closeout-safety.sh, which knows which revisions a batch adds but has
    # no business asking production anything. Prints nothing on success.
    --plan-for) shift; status=0
                for wanted in "$@"; do
                  if ! reason="$(plan_problem "$wanted")"; then
                    echo "  revision $wanted -> $reason" >&2
                    status=1
                  fi
                done
                exit "$status" ;;
    *) echo "usage: $0 [--deployed <revision>] | --plan-for <revision>..." >&2; exit 2 ;;
  esac
done

if [[ -z "$deployed" ]]; then
  deployed="$(curl -fsS --max-time 20 "$HEALTH" 2>/dev/null \
    | sed -n 's/.*"migration"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
fi
if [[ -z "$deployed" ]]; then
  echo "migration recovery: CANNOT TELL — no deployed revision from $HEALTH"
  echo "  Pass --deployed <revision> once you have established what production is running."
  echo "  An unknown starting point is not an empty diff; do not upload on this result."
  exit 2
fi

# `mapfile` is bash 4; macOS ships 3.2, which is what the local gate runs on.
revisions=()
while IFS= read -r line; do
  revisions+=("$line")
done < <(
  find "$VERSIONS" -maxdepth 1 -name '[0-9]*_*.py' -exec basename {} \; | sed 's/_.*//' | sort -u
)
if (( ${#revisions[@]} == 0 )); then
  echo "migration recovery: CANNOT TELL — no revisions found under $VERSIONS"
  exit 2
fi

if ! printf '%s\n' "${revisions[@]}" | grep -qx "$deployed"; then
  echo "migration recovery: CANNOT TELL — production reports revision '$deployed',"
  echo "  which is not in this tree. Establish what is actually running before uploading."
  exit 2
fi

# Lexical order is the chain order here: revisions are zero-padded and strictly
# sequential, which `alembic history` would confirm and the gate already proves by
# running `upgrade head` from empty on every run.
pending=()
for revision in "${revisions[@]}"; do
  [[ "$revision" > "$deployed" ]] && pending+=("$revision")
done

if (( ${#pending[@]} == 0 )); then
  echo "migration recovery: PASS — this shipment applies no migration (production at $deployed)"
  exit 0
fi

echo "migration recovery: this shipment applies ${#pending[@]} revision(s) past $deployed"
echo "  Each one removes the rollback target until a later shipment applies none."
echo

failed=0
for revision in "${pending[@]}"; do
  source_file="$(find "$VERSIONS" -maxdepth 1 -name "${revision}_*.py" | head -1)"
  printf '  %-4s ' "$revision"

  if ! reason="$(plan_problem "$revision")"; then
    echo "FAIL — $reason"
    echo "         The plan belongs to the batch that adds the revision, not to the shipment."
    echo "         docs/runbooks/migrations.md says what it has to answer."
    failed=1
  else
    echo "PASS — docs/runbooks/migration-$revision-recovery.md ($reason lines)"
  fi

  if [[ -n "$source_file" ]]; then
    contracting="$(
      sed -n '/^def upgrade/,/^def downgrade/p' "$source_file" \
        | grep -oE "$CONTRACTING" | sort -u | tr '\n' ' '
    )"
    if [[ -n "$contracting" ]]; then
      echo "         contracting DDL: $contracting"
      echo "         Expand-then-contract keeps these out of a shipment that may need its"
      echo "         rollback. The plan must say why this one cannot wait."
    fi
  fi
done

echo
if (( failed )); then
  echo "migration recovery: REFUSED — do not upload."
  exit 1
fi
echo "migration recovery: PASS — every applied revision has a written plan."
exit 0

#!/usr/bin/env bash
# Works out which parts of the repository a pull request or push changed, so
# CI can skip jobs that cannot be affected. CI, Rust Tests and CodeQL all call
# it, so the path rules live in one place.
#
# Fail-open: whenever the change set cannot be worked out (a scheduled or
# manual run, a new branch, a fetch that fails, a checkout that is not the
# merge commit) every area is reported changed and everything runs. Skipping
# is only ever the result of a diff that was actually computed.
#
# Which diff:
#   pull_request  the PR's test merge commit against its first parent, which
#                 is the base branch tip. That is everything the PR changes,
#                 not just the last push, so a PR that touched crates/ in its
#                 first commit still runs the Rust jobs on every later push.
#                 Checkout needs fetch-depth: 2.
#   push          the pushed range, github.event.before..HEAD.
#
# Environment:
#   EVENT_NAME     github.event_name
#   BEFORE         github.event.before (push only)
#   SELF           the calling workflow's own file; editing it runs everything
#   FULL_ON_PUSH   "true" to treat every push as changing everything
#
# Writes key=true|false lines to $GITHUB_OUTPUT (stdout when unset) and a
# short table to $GITHUB_STEP_SUMMARY when set.

set -uo pipefail

out="${GITHUB_OUTPUT:-/dev/stdout}"
event="${EVENT_NAME:-}"
self="${SELF:-}"
reason=""
files=""

compute() {
  case "$event" in
    pull_request)
      # Two parents means this is the merge commit GitHub built for the PR.
      if ! git rev-parse --verify --quiet HEAD^2 >/dev/null; then
        reason="checkout is not a PR merge commit"
        return 1
      fi
      files=$(git diff --name-only HEAD^1 HEAD) || { reason="git diff failed"; return 1; }
      ;;
    push)
      if [ "${FULL_ON_PUSH:-}" = "true" ]; then
        reason="this workflow runs everything on push"
        return 1
      fi
      local before="${BEFORE:-}"
      if [ -z "$before" ] || [ "$before" = "0000000000000000000000000000000000000000" ]; then
        reason="push has no previous commit"
        return 1
      fi
      if ! git cat-file -e "$before^{commit}" 2>/dev/null; then
        git fetch --no-tags --quiet --depth=1 origin "$before" || { reason="could not fetch $before"; return 1; }
      fi
      files=$(git diff --name-only "$before" HEAD) || { reason="git diff failed"; return 1; }
      ;;
    *)
      reason="event '$event' runs everything"
      return 1
      ;;
  esac
  return 0
}

all=false
if ! compute; then
  all=true
elif [ -z "$files" ]; then
  reason="no files changed"
else
  # The detection itself, and the workflow asking, change what every job does.
  if printf '%s\n' "$files" | grep -qxF -e ".github/scripts/changed-areas.sh" ${self:+-e "$self"}; then
    all=true
    reason="CI configuration changed"
  fi
fi

# changed <name> <extended regex>: true when any changed path matches.
changed() {
  local value=false
  if [ "$all" = true ] || printf '%s\n' "$files" | grep -qE "$2"; then
    value=true
  fi
  printf '%s=%s\n' "$1" "$value" >> "$out"
  eval "area_$1=$value"
}

# ── Areas used by CI and Rust Tests ──────────────────────────────────────────
# The root Rust workspace. Both desktop apps and the map registry DLL build
# crates from it, so anything here reaches all of them.
changed rust       '^(crates/|Cargo\.(toml|lock)$|rust-toolchain(\.toml)?$|\.cargo/)'
changed tag_editor '^(crates/|Cargo\.(toml|lock)$|rust-toolchain(\.toml)?$|\.cargo/|apps/tag-editor/src-tauri/)'
changed launcher   '^(crates/|Cargo\.(toml|lock)$|rust-toolchain(\.toml)?$|\.cargo/|apps/launcher/)'
# native/map_registry links the mjolnir-mglo-cabi staticlib from crates/, and
# the lobby's Discord test drives tools/tests/test_discord_rpc.py.
changed native     '^(native/|crates/|Cargo\.(toml|lock)$|tools/tests/test_discord_rpc\.py$)'
# The hub snapshots docs/, defs/, changelog/ and blog/ at build time
# (scripts/sync-*.mjs), and its tests read tools/fixtures/.
changed hub        '^(hub|docs|defs|changelog|blog)/|^tools/fixtures/'

# ── CodeQL languages ─────────────────────────────────────────────────────────
# By file type, wherever the file is. actions is always analysed: it takes
# under a minute, and it means every commit gets at least one CodeQL upload,
# which the ruleset's code scanning rule waits for.
langs="[actions]"
lang() {
  if [ "$all" = true ] || printf '%s\n' "$files" | grep -qE "$2"; then
    langs="$langs[$1]"
  fi
}
lang c-cpp                 '\.(c|cc|cpp|cxx|h|hh|hpp|hxx|inl|ipp)$'
lang csharp                '\.(cs|csx|cshtml|razor|csproj|sln|props|targets)$'
lang java-kotlin           '\.(java|kt|kts)$|(^|/)(pom\.xml|build\.gradle(\.kts)?|settings\.gradle(\.kts)?)$'
lang javascript-typescript '\.(js|jsx|mjs|cjs|ts|tsx|mts|cts|vue|html?)$|(^|/)(package\.json|tsconfig[^/]*\.json|jsconfig\.json)$'
lang python                '\.(py|pyi|pyw)$|(^|/)(requirements[^/]*\.txt|pyproject\.toml|setup\.(py|cfg)|Pipfile)$'
lang ruby                  '\.(rb|rake|gemspec|erb)$|(^|/)(Gemfile|Rakefile)$'
lang rust                  '\.rs$|(^|/)(Cargo\.(toml|lock)|rust-toolchain(\.toml)?)$|(^|/)\.cargo/'
printf 'codeql=%s\n' "$langs" >> "$out"
printf 'all=%s\n' "$all" >> "$out"

# ── Log ──────────────────────────────────────────────────────────────────────
count=0
[ -n "$files" ] && count=$(printf '%s\n' "$files" | wc -l | tr -d ' ')
summary="Changed files: $count. Everything runs: $all${reason:+ ($reason)}."
echo "$summary"
echo "rust=$area_rust tag_editor=$area_tag_editor launcher=$area_launcher native=$area_native hub=$area_hub"
echo "codeql=$langs"
if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  {
    echo "### Changed areas"
    echo
    echo "$summary"
    echo
    echo "| area | runs |"
    echo "| --- | --- |"
    for a in rust tag_editor launcher native hub; do
      eval "echo \"| $a | \$area_$a |\""
    done
    echo "| CodeQL | $langs |"
  } >> "$GITHUB_STEP_SUMMARY"
fi
exit 0

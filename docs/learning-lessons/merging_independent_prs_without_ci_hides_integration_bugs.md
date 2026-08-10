# Merging independently-developed PRs without CI hides integration bugs each PR's own tests can't see

**Date**: 2026-08-09
**Spec**: N/A — repo-wide (no `.github/workflows/` exists)
**Code**: `src/gamebook_web/api/character.py`, `src/gamebook_web/api/turn.py`

## What happened

Seven PRs (#29–#34, #36), each fixing a distinct issue (#14/#17/#18/#19/#20/#22/#25/#26),
were developed in parallel on separate branches off the same point on `dev`. Each one
passed its own test suite in isolation. Merged sequentially in dependency-safe order
(checking `mergeable`/`mergeStateStatus` between each merge to catch textual conflicts),
all seven merged cleanly with zero git conflicts.

Running the full suite immediately after all seven landed: **35 tests failed.** The root
cause had nothing to do with conflicting file edits — it was a **contract change one PR
made that other PRs, developed against the pre-change contract, never saw**.

PR #34 (`fix(#14,#25)`) changed `CampaignRegistry.get_active_for_account` and
`deps.get_active_campaign` from synchronous to `async def` (to support a real DB
round-trip). `character.py` (last touched in an earlier commit) and part of `turn.py`
(added by PR #36, branched *before* #34 merged) both still called
`get_active_campaign(...)` with no `await` — always legal Python (an unawaited coroutine
is just silently never executed and treated as truthy), so nothing raised an import-time
or type error. It only surfaced as a 500 at request time, because `state.campaign_id`
was accessed on a coroutine object instead of a `CampaignState`.

No single PR's test suite could have caught this: PR #34's tests used its own
already-async call sites; `character.py`/`turn.py`'s existing tests never got PR #34's
changed dependency in the same test run until everything was merged together.

## The resolution

After merging, immediately run the full suite (not just `git status`/`mergeable` checks)
and grep for the actual failure pattern — here, `RuntimeWarning: coroutine '...' was never
awaited` in the pytest warnings section was the tell, not the visible `AttributeError`.
Fixed by adding the missing `await` at all four call sites (`git grep '= get_active_campaign('`
found every one).

## Rule

**A clean git merge (no textual conflicts) is not proof of a correct merge** when there is
no CI to run each PR's changes against the others' before they land. In a repo without CI,
after merging multiple independently-developed PRs together — even ones that merged with
zero conflicts — always run the full test suite once more against the *combined* result
before considering the merge done. A signature change (sync→async, a renamed field, a
narrowed type) is invisible to `git merge` and invisible to any PR's own tests if another
PR's code calling that signature was branched before the change and never re-tested
against it.

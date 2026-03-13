# Remove `stage` CLI Command

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove the `stage` command and all supporting code — its output is a dead end that nothing consumes.

**Architecture:** `stage` writes to `40_staged/<file>` but `package install` only reads from `40_staged/<package-name>/`. The internal `_stage_single_file()` helper stays (used by `package build`). The `DefaultCommandGroup` class is only used by `stage` and goes too.

**Tech Stack:** Python/Click CLI, pytest, bats

---

### Task 1: Delete `stage` CLI commands and `do_stage_files` from `skfl`

**Files:**
- Modify: `skfl`

**Step 1: Delete the `DefaultCommandGroup` class**

Delete lines 563–582 (the section comment and the entire class). This class is only used by the `stage` group.

```
# ── custom group for vet/stage that routes unknown args to a default command ──


class DefaultCommandGroup(click.Group):
    ...entire class...
```

**Step 2: Delete the `do_stage_files` function**

Delete lines 528–560 (the function `do_stage_files`). Only called by the `stage` command.

**Step 3: Delete the `stage` command group and all subcommands**

Delete lines 980–1017 — the section comment, the `stage` group, `stage_default`, and `stage_list` commands.

```
# ── stage ──────────────────────────────────────────────────────────────

@cli.group(cls=DefaultCommandGroup, ...)
def stage(ctx): ...

@stage.command("_default", hidden=True)
def stage_default(profile, files): ...

@stage.command("list")
def stage_list(profile): ...
```

**Step 4: Run the unit tests to confirm only stage tests break**

Run: `cd /Users/jim/code/skfl && python -m pytest tests/test_skfl.py -x --tb=short 2>&1 | head -60`
Expected: Failures in stage-related test classes only.

**Step 5: Commit**

```bash
git add skfl
git commit -m "remove stage CLI command and supporting code

stage output was never consumed by package install; dead-end command."
```

---

### Task 2: Delete stage tests from `tests/test_skfl.py`

**Files:**
- Modify: `tests/test_skfl.py`

**Step 1: Delete `TestStageCommand` class**

Delete the entire class (starts at `class TestStageCommand:`, ~lines 690–824).

**Step 2: Delete `TestStageList` class**

Delete the entire class (starts at `class TestStageList:`, ~lines 830–841).

**Step 3: Delete stage methods from `TestFullWorkflow`**

Delete these three methods from `class TestFullWorkflow`:
- `test_source_vet_stage` (uses `["stage", ...]`)
- `test_source_vet_patch_stage` (uses `["stage", ...]`)
- `test_source_update_re_vet` (uses `["stage", ...]`)

Keep `TestFullWorkflow` itself if it has remaining methods; delete the class if empty.

**Step 4: Delete `TestStageWithProfile` class**

Delete the entire class (starts at `class TestStageWithProfile:`, ~lines 1129–1268).

**Step 5: Delete stage completion wiring tests**

In `TestShellCompletion`, delete:
- `test_stage_default_files_wired`
- `test_stage_default_profile_wired`
- `test_stage_list_profile_wired`

**Step 6: Run tests**

Run: `cd /Users/jim/code/skfl && python -m pytest tests/test_skfl.py -v 2>&1 | tail -30`
Expected: All remaining tests pass.

**Step 7: Commit**

```bash
git add tests/test_skfl.py
git commit -m "remove stage tests from test_skfl.py"
```

---

### Task 3: Delete stage tests from bats suites

**Files:**
- Modify: `tests/bats/skfl.bats`
- Modify: `tests/bats/missing-deps.bats`

**Step 1: Delete stage tests from `skfl.bats`**

Delete these sections:
- Lines 259–260: `# ── stage ──...` section comment
- Lines 261–339: All `@test "stage ..."` tests (6 tests)
- Lines 341–342: `# ── stage list ──...` section comment
- Lines 343–359: Both `@test "stage list ..."` tests
- Lines 361–362: `# ── full workflow ──...` section comment
- Lines 363–403: `@test "full workflow: source -> vet -> stage"` and `@test "full workflow: source -> vet -> patch -> stage"`
- Lines 405–428: `@test "full workflow: source update invalidates vet"` (uses stage throughout)
- Lines 436–446: `@test "stage preserves file content exactly"`
- Lines 448: `# ── profile-based staging ...` section comment
- Lines 450–580: `@test "single source, multiple profiles with different patches"` (uses stage throughout)
- Lines 582–599: `@test "stage list --as shows only that profile"`

**Step 2: Delete stage tests from `missing-deps.bats`**

Delete:
- Lines 92–93: `# ── stage: patch binary missing ──...` section comment
- Lines 94–124: Both `@test "stage: ..."` tests
- Lines 152–160: `@test "stage without patches works without diff"`

**Step 3: Run bats tests (if chroot environment is available)**

Run: `cd /Users/jim/code/skfl && bats tests/bats/skfl.bats 2>&1 | tail -20`
Expected: Remaining tests pass (or skip if chroot isn't set up).

**Step 4: Commit**

```bash
git add tests/bats/skfl.bats tests/bats/missing-deps.bats
git commit -m "remove stage tests from bats suites"
```

---

### Task 4: Update README and TODO

**Files:**
- Modify: `README.md`
- Modify: `TODO.md`

**Step 1: Update README.md theory of operation**

Lines 47–49 currently describe staging as a separate workflow step. Rewrite to reflect that `package build` handles vet-check + patch application + staging:

Replace the staging paragraph (lines 47–49) with a description of packages as the install path. Remove the "Staging" section (lines 115–127) and the "Installation" section that references standalone staging (lines 128–135), replacing with package-based install docs.

Keep the `40_staged/` line in the directory tree (line 64) since `package build` still writes there.

**Step 2: Delete TODO.md line 1**

Remove `- Add stage arguments so you can stage only specific file or directory` — the feature request is moot.

**Step 3: Commit**

```bash
git add README.md TODO.md
git commit -m "update docs: remove stage references, document package workflow"
```

---

### Task 5: Update design docs

**Files:**
- Modify: `docs/decisions/2026-02-28-autocompletion.md`
- Modify: `docs/plans/2026-02-28-packages-design.md`

**Step 1: Update autocompletion decision doc**

- Remove `, \`stage\`` from the `_complete_source_files` usage table
- Remove the `_complete_profiles` / `stage --as` row (keep the `package build --as` usage)
- Update Decision 6 heading and body to reference only `vet`, not `vet`/`stage`
- Remove the line about `DefaultCommandGroup` being retained for `stage`

**Step 2: Update packages design doc**

- Update line 105 which says `skfl stage` is retained as a CLI command — note it was removed
- Update any workflow descriptions that reference `skfl stage` as a step

**Step 3: Commit**

```bash
git add docs/
git commit -m "update design docs: stage command removed"
```

---

### Task 6: Final verification

**Step 1: Grep for remaining stage references**

Run: `grep -rn 'stage' /Users/jim/code/skfl/skfl /Users/jim/code/skfl/tests/ /Users/jim/code/skfl/README.md | grep -v STAGED_DIR | grep -v _stage_single | grep -v staged_path | grep -v '40_staged' | grep -v '.pyc'`

Expected: No references to the `stage` CLI command remain. Internal references to `_stage_single_file`, `STAGED_DIR`, and `40_staged/` are fine (used by `package build`).

**Step 2: Run full test suite**

Run: `cd /Users/jim/code/skfl && python -m pytest tests/test_skfl.py -v`
Expected: All tests pass.

**Step 3: Smoke test the CLI**

Run: `cd /Users/jim/code/skfl && python skfl --help`
Expected: No `stage` in the command list. `vet`, `patch`, `package`, `source` etc. still present.

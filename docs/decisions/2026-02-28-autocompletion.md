# Technical Decisions: Shell Autocompletion

Date: 2026-02-28

## Overview

Added shell autocompletion for bash, zsh, and fish via Click 8.x's built-in
completion mechanism.  Three completion callback functions were added, wired
onto eight Click parameters, and a `skfl completion` command was added to help
users enable completion in their shell.

---

## Decision 1: Use Click's native `shell_complete` parameter

**Options considered:**

1. *Click's native `shell_complete` kwarg on `@click.argument` / `@click.option`* –
   passes a callback `(ctx, param, incomplete) -> list[CompletionItem]` directly
   in the decorator.  Users enable completion by evaluating the script that
   `_SKFL_COMPLETE=bash_source skfl` prints.
2. *Custom `ShellComplete` subclass* – overrides the entire completion engine.
   More powerful, but requires touching Click internals.
3. *External completion scripts* (hand-written Bash/Zsh/Fish files) – portable
   but must be kept in sync with the CLI manually.

**Decision:** Option 1.  It is idiomatic Click 8.x, requires no external files,
and is automatically correct whenever the CLI changes.

---

## Decision 2: Three focused completion helpers, not one generic one

Three functions cover all distinct completion domains:

| Function | Completes | Used by |
|---|---|---|
| `_complete_source_files` | Paths in `10_sources/`, repo-relative | `vet`, `patch create/list` |
| `_complete_patch_files` | `*.patch` files under `30_patches/`, repo-relative from repo root | `patch remove` |
| `_complete_profiles` | Directory names under `30_patches/_profiles/` | `package build --as` |

A fourth function `_complete_source_names` (source keys from `skfl.toml`) was
considered but there is currently no command that accepts an existing source
name as an argument, so it was not added to avoid dead code.

---

## Decision 3: Lazy import of `click.shell_completion`

`from click.shell_completion import CompletionItem` is imported inside each
callback instead of at module level.  This keeps the import invisible during
normal command execution (completion callbacks are only called by the shell
completion machinery) and avoids any risk of import-time side effects from that
submodule.

---

## Decision 4: Repo discovery order and defaults

`find_repo()` tries three locations in order before raising:

1. **cwd walk** – traverse from `start` (default: cwd) up to the filesystem root.
2. **`$SKFL_REPO`** – if set and points at a directory containing `skfl.toml`, use it.
3. **`~/.skfl`** – if `~/.skfl/skfl.toml` exists, use it as the default repo.

This means:
- Commands and completions work from any directory once the user has a repo at
  `~/.skfl` — the common single-user case requires zero configuration.
- Multi-repo users or CI can override with `$SKFL_REPO` without touching cwd.
- `$SKFL_REPO` takes priority over the default so it can point at a different
  repo while `~/.skfl` remains untouched.

All three completion callbacks return `[]` when `find_repo()` still raises after
all three locations are tried.  Raising inside a completion callback would produce
confusing shell output; returning an empty list gives a silent no-op, which is
the least surprising behaviour.

---

## Decision 5: Add `skfl completion [SHELL]` command

Click's built-in completion requires the user to run an `eval` line in their
shell profile—a step that is not obvious from `skfl --help`.  A `completion`
subcommand that prints the exact lines to add was added.  Without a SHELL
argument it prints instructions for all three shells.

The `SHELL` argument uses `click.Choice(["bash", "zsh", "fish"])` so that
invalid shell names are rejected with a clear error message.

---

## Decision 6: `DefaultCommandGroup` removed with `stage`

`DefaultCommandGroup` was a custom `click.Group` subclass that routed
unrecognised tokens to a hidden `_default` command.  It was used solely by the
`stage` command group, which has since been removed.  The class no longer exists
in the codebase.

---

## Decision 8: Separate `vet` and `vet-status` into top-level commands

**Original design:** `vet` was a `DefaultCommandGroup` with a hidden `_default`
subcommand for the actual vetting action and a visible `status` subcommand.
This meant `skfl vet status` showed vet status and `skfl vet <files>` routed
through `_default`.

**Problem:** The `DefaultCommandGroup` routing broke tab-completion for the
first file token: `skfl vet <TAB>` would show `status` instead of source
files.

**Change:** `vet` is now a plain `@cli.command` that takes `files` directly.
`vet-status` is a separate top-level `@cli.command`.  `DefaultCommandGroup` was removed along with the `stage` command.

**Benefits:**
- `skfl vet <TAB>` now completes source files immediately with no workaround.
- No hidden `_default` routing needed for `vet`; the code is simpler.
- `skfl vet-status <TAB>` also completes source files directly.
- The two commands are now independently discoverable in `skfl --help`.

---

## Decision 7: Test strategy

Tests are split into three classes in `tests/test_skfl.py`:

1. **`TestCompletionHelpers`** – calls each function directly with `(None, None,
   incomplete)`.  Covers: all files returned, `.gitkeep` excluded, prefix
   filtering, no-match prefix, no-repo graceful return, correct
   `CompletionItem` types, subdirectory paths, file vs directory discrimination.
2. **`TestCompletionCommand`** – uses Click's `CliRunner` to invoke
   `skfl completion [SHELL]` and asserts on stdout content.
3. **`TestCompletionWiring`** – reads `param._custom_shell_complete` (the
   attribute where Click 8.x stores the callback passed as `shell_complete=`)
   and asserts it is the expected function.  This prevents accidental
   disconnection of a callback from its parameter.

The `_custom_shell_complete` attribute is a Click implementation detail but is
stable across Click 8.x.  If a future Click version renames it, the wiring
tests will fail loudly, which is the desired behaviour.

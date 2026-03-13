# Package Manifest Design

## Goal

Replace symlink-based package definitions with an explicit `package.toml` manifest that supports per-entry patch lists. This enables one source file to appear at multiple dest paths with different patches applied to each — the primary use case being splitting a long source file into multiple shorter skills.

## Problem

Current model: `package add` creates a symlink in `50_packages/<name>/`; `package build --as <profile>` applies one profile to every file. There is no way to apply different patches to different entries within the same build.

## Solution

Each package is defined by a `package.toml` manifest. Patches are no longer auto-applied — they are listed explicitly per entry. Profiles are removed.

## Directory Renumbering

Packages logically precede staged output, so the directories swap:

| Old | New |
|-----|-----|
| `40_staged/` | `50_staged/` |
| `50_packages/` | `40_packages/` |

## Manifest Format

`40_packages/<name>/package.toml`:

```toml
[[file]]
source = "github/BenjaminG/ai-skills/pr/SKILL.md"
dest = "skills/intro.md"
patches = [
    "30_patches/github/BenjaminG/ai-skills/pr/SKILL.md.d/001-extract-intro.patch",
]

[[file]]
source = "github/BenjaminG/ai-skills/pr/SKILL.md"
dest = "skills/advanced.md"
patches = [
    "30_patches/github/BenjaminG/ai-skills/pr/SKILL.md.d/002-extract-advanced.patch",
]

[[file]]
source = "custom/myskills/helper.sh"
dest = "scripts/helper.sh"
```

- `source` — path relative to `10_sources/`
- `dest` — install path within the package (and at the install target)
- `patches` — ordered list of patch file paths relative to the repo root; optional, omit when empty

## CLI Changes

### Kept unchanged
- `skfl package init <name>` — creates `40_packages/<name>/package.toml` (empty)
- `skfl package list` — lists package names
- `skfl package show <name>` — renders dest tree (reads manifest instead of symlinks)
- `skfl patch create/list/remove` — unchanged

### Changed
- `skfl package add <name> <source> <dest> [--with-patch <patch>]...` — appends a `[[file]]` entry to the manifest; `--with-patch` may be repeated
- `skfl package build <name>` — reads manifest, vets sources (drops into vet flow for unvetted), applies listed patches, stages to `50_staged/<name>/`; `--as <profile>` option removed

### Install commands
- `skfl package install rsync/stow` — reads from `50_staged/<name>/` (path update only)

## What Is Removed

- Symlink-based package structure (`_collect_symlinks`, `resolve_package_files`)
- `30_patches/_profiles/` profile convention
- `profile_patches_dir_for`, `_complete_profiles`
- Profile logic in `list_patches_for` and `_stage_single_file`
- `--as <profile>` option on `package build`
- Auto-apply of default patches — patches only apply when explicitly listed

## Error Handling

- Source not in `10_sources/` → error at `package add` time
- Referenced patch file does not exist → error at `package build` time, naming the missing patch
- Unvetted/modified source → drop into vet flow (same as current behavior)

## Testing

- `TestPackageNew`: `package init` creates `package.toml`
- `TestPackageAdd`: appends entries; `--with-patch` stores patches; duplicate dest is rejected
- `TestPackageBuild`: no patches, one patch, multiple patches, multiple entries same source different patches
- `TestPackageShow`: tree from manifest dests
- `TestPackageInstall`: rsync/stow read from `50_staged/`
- Remove all profile-related tests

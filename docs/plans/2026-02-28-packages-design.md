# Packages Design

## Overview

Add a `package` command group to `skfl` that lets users define named, repeatable
subsets of vetted sources for staging and installation. A package is a directory
of symlinks inside the repository; the symlink structure mirrors the desired
installation layout. This replaces the unpackaged `skfl install` / `skfl rsync` /
`skfl stow` workflow — packages are now the only install path.

## Motivation

The existing `skfl stage <files>` + `skfl install rsync <target>` workflow has no
mechanism for selecting a subset of vetted sources. Users always want to install
a curated subset — not everything — and they want that selection to be named and
repeatable. Packages solve this.

## Repository Structure

`skfl init` gains a fifth directory:

```
<repo>/
  skfl.toml
  10_sources/
  20_vetted/
  30_patches/
  40_staged/
  50_packages/           ← new
    <package-name>/
      <dest-path>  ->  ../../10_sources/<source-path>
      ...
```

Each subdirectory of `50_packages/` is a package. Its contents are symlinks
(to files or directories in `10_sources/`) whose paths define the installation
layout. Git versions the symlinks directly — no new config format is needed.

### Example

```
50_packages/
  my-setup/
    skills/   ->  ../../10_sources/github/anthropics__claude-code-skills/skills/
    AGENTS.md ->  ../../10_sources/custom/my-files/AGENTS.md
```

Installing `my-setup` to `~/.claude/` produces:

```
~/.claude/
  skills/       (contents of the source skills directory)
  AGENTS.md
```

## Commands

### New: `skfl package`

```
skfl package new <name>
```
Creates `50_packages/<name>/`. Fails if it already exists.

```
skfl package add <name> <source-path> <dest-path>
```
Creates a symlink at `50_packages/<name>/<dest-path>` pointing to the resolved
path under `10_sources/<source-path>`. Parent directories are created as needed.
Equivalent to a guided `ln -s`; users may also create symlinks manually.

```
skfl package list
```
Lists all defined packages (subdirectories of `50_packages/`).

```
skfl package build <name>
```
Resolves all symlinks in the package, expanding directory symlinks to their
constituent files. For each resolved file:
- Refuses (with a clear error) if any file is unvetted or modified since last vet.
- Applies patches (default + profile, if `--as` is given).
- Writes output to `40_staged/<name>/`, preserving the package's dest-path layout.

```
skfl package build <name> --as <profile>
```
Same as above but applies profile-specific patches on top of default patches.

```
skfl package install rsync <name> <target>
skfl package install stow  <name> <target>
```
Installs `40_staged/<name>/` to `<target>` using rsync or GNU Stow respectively.
Fails if the package has not been built (i.e. `40_staged/<name>/` does not exist).

### Removed

- `skfl install rsync <target>`
- `skfl install stow <target>`
- `skfl rsync <target>` (top-level shortcut)
- `skfl stow <target>` (top-level shortcut)

`skfl stage` has been removed. The `_stage_single_file` internal helper is
retained as it is used by `package build`.

## Full Workflow

```
# Pull a source
skfl source pull https://github.com/anthropics/claude-code-skills

# Vet what you want to use
skfl vet github/anthropics__claude-code-skills/skills/

# Optionally patch a file
skfl patch create github/anthropics__claude-code-skills/skills/some-skill.md

# Define a package
skfl package new my-setup
skfl package add my-setup github/anthropics__claude-code-skills/skills/ skills/

# Build it (refuses if anything unvetted)
skfl package build my-setup

# Install
skfl package install rsync my-setup ~/.claude/
```

## Error Handling

- `package new`: fail if package already exists.
- `package add`: fail if source path does not exist in `10_sources/`; fail if
  dest path already exists in the package directory.
- `package build`: fail with a clear per-file error if any resolved file is
  unvetted or modified. Do not partially build — refuse the whole build if any
  file is not clean.
- `package install`: fail if `40_staged/<name>/` does not exist (package not
  built).

## Relation to Profiles

Packages and profiles are orthogonal. A package selects *which* files to
include; a profile selects *which patches* to apply. `skfl package build --as
<profile>` combines both.

## Tab-Completion

Tab-completion (the other open TODO item) is a separate concern and will be
designed and implemented independently. The `package` subcommands should be
designed to be completion-friendly: package names complete from `50_packages/`,
source paths complete from `10_sources/`.

## Testing

- Unit tests (pytest + CliRunner): `package new`, `package add`, `package list`,
  `package build` (vetted, unvetted, with patches, with profile), `package install`.
- Integration tests (bats): full workflow test covering source → vet → package
  new/add → build → install.
- Removed command tests: verify `skfl install`, `skfl rsync`, `skfl stow`
  (top-level) no longer exist.

## SKFL

`skfl` (pronounced "skillful") helps you manage skills for agentic LLM products... skillfully.

### Goals and Non-Goals

`skfl` is meant to streamline the process of

- pulling skills from common repositories like GitHub repos,
- asking you, a human with judgement and something to lose, to vet the files you want to use,
- managing a history of what you have and haven't read,
- maintaining patches on top of skills for your own customization purposes, and, FINALLY,
- actually "installing" those vetted (and optionally patched) files as skills in your home directory or in a repository.

This is a lot of moving parts. `skfl` offers a layered interface onto these steps -- each can be performed in isolation, but common operations can be bundled together to make things easier. I can't promise they'll be _easy_, but I aim for `skfl` to acknowledge fundamental complexity and simplify everything else.

### Installation

In the spirit of "read before you run", `skfl` is a single Python file. Download it to your `~/Downloads`, read it, and move it to somewhere in your `$PATH`. I like `~/.local/bin`.

#### Runtime Dependencies

It has Python dependencies. If you have Python smarts you can manage a virtualenv yourself if you like, but I recommend you run it as a standalone executable. This requires [installing `uv`](https://docs.astral.sh/uv/getting-started/installation/).

`skfl` will also shell out to other executables. You can check the status of your install by running `skfl doctor` (or `python <path-to-skfl> doctor` if you don't know if you have `uv` installed).

Those dependencies are:

- [`rsync`](https://rsync.samba.org/) for using `skfl install rsync`/`skfl rsync` to "install" skills to a given location using `rsync` for smart `cp`ing.
- [GNU Stow](https://www.gnu.org/software/stow/) for using `skfl install stow`/`skfl stow` to "install" skills to a given location using `stow` to use your `skfl` repo as a symlink farm.
- [`glow`](https://github.com/charmbracelet/glow) for use as a markdown-specific pager when vetting skills.
- [`fzf`](https://github.com/junegunn/fzf) for interactive selection in a number of different workflows.

The `rsync` and `stow` subcommands have no fallbacks for these runtime dependencies.

If `glow` is not available, `less` will be used as a pager for vetting skills, same as it's used for non-markdown files.

If `fzf` is not available, commands will fail and recommend non-interactive ways for the user to specify the parameters for the operation.

### Theory of Operation

The core workflow for `skfl` is:

- Your skills and all data relating to them is managed in a REPOSITORY -- a directory full of plaintext files specifying everything described below.
- You manage a SOURCE or many SOURCES of files to use as skills -- specifying directories of skills you authored or pulling them from various remote sources.
- Before using files from your sources, `skfl` requires that you VET them by reading them. With your squishy human eyeballs. You don't have to vet every file, but `skfl` will only let you use files that have been vetted.
- You may optionally maintain PATCHES on top of vetted files. Patches let you customize skills to your own needs without modifying the source files directly, so your customizations survive source updates. You can maintain multiple patches per file; they are applied in order.
- Once vetted (and optionally patched), files can be STAGED for installation. By staging a file, you're explicitly declaring your intent to use it as a skill. Staging takes the vetted source, applies any patches, and places the result in a staging area ready for installation.
- Staged files (and directories of staged files) can be INSTALLED directly into different locations. `skfl` can be pointed explicitly at a target directory, but it also comes pre-programmed with the directory structure of a few of the popular agentic LLM products and can, for example, be told to install a Kiro Power or a Claude Agent in the appropriate directory.

#### Repository

Start a repository with `skfl init`. This creates the directory structure `skfl` needs to manage your skills:

```
<repo>/
  skfl.toml                   # repository configuration
  .gitignore
  10_sources/                 # raw source files
    github/<owner>/<repo>/
    custom/<name>/
  20_vetted/                  # snapshots of files as they were when vetted
  30_patches/                 # your patches on top of source files
  40_staged/                  # files ready for installation (source + patches)
```

This directory is intended to be managed as a Git repository.

#### Sources

Pull from a GitHub repository with `skfl source pull <url>` or `skfl source pull --owner <owner> --repo <repo> --ref <ref>`. If a ref isn't provided, `skfl` will recommend using a tag if one is available and let you select one interactively. This will put a shallow copy of the entire repository in `skfl`'s source cache at `10_sources/github`.

You can also register a directory of self-authored files with `skfl source custom <name> <path>`; these are managed at `10_sources/custom`.

You can update a non-custom source using `skfl source pull` again. `source pull` with no arguments will pull all sources, or you can identify a specific source to update.

#### Vetting

`skfl` tracks both the source file and your vetting state for each file. This is the key to making source updates painless.

When you first encounter a file, you vet it by reading it in full -- `skfl` opens the file in a pager (`glow` for Markdown, `less` for everything else) and, once you confirm you've reviewed it, records a snapshot of the file content in `20_vetted/`. The snapshot is a copy of the file, mirroring the source tree structure.

When you update a source with `skfl source pull`, you don't need to re-read every file from scratch. `skfl` compares each updated source file against your vetted snapshot:

- Files that haven't changed remain vetted. No action needed.
- Files that have changed are shown to you as a **diff** -- you review only what changed, not the whole file again. Approve the diff and your vetted snapshot is updated to match the new version.
- New files require full vetting, same as the first time.

This is why `skfl` stores the full vetted snapshot, not just a hash: the vetted copy is the baseline for computing diffs when sources are updated.

Check what needs vetting with `skfl vet status`. Interactively vet files with `skfl vet`.

#### Patching

After vetting a file, you can maintain one or more patches on top of it. Patches let you customize skills to your preferences without modifying the source directly. Your customizations are your own, independent of upstream changes, and survive source updates.

Patches are stored in `30_patches/`, organized to mirror the source tree. For a source file at `10_sources/github/owner/repo/skills/my-skill.md`, patches live in `30_patches/github/owner/repo/skills/my-skill.md.d/` as numbered patch files:

```
30_patches/github/owner/repo/skills/my-skill.md.d/
  001-add-context.patch
  002-fix-formatting.patch
```

Multiple patches for the same file are applied in lexicographic order. This lets you layer independent customizations that can be individually added, removed, or reordered.

Key commands:

- `skfl patch create <source-file>` — create a new patch for a vetted source file. Opens your `$EDITOR` with a copy of the file; the diff between the original and your edited version becomes the patch.
- `skfl patch list [source-file]` — list patches, optionally filtered to a specific source file.
- `skfl patch remove <patch>` — remove a patch.

When a source is updated and re-vetted, `skfl` will attempt to apply your existing patches to the new version of the file. If a patch doesn't apply cleanly, `skfl` will warn you so you can update or remove the patch.

#### Staging

Staging is where vetting and patching come together into files ready for installation. When you stage a file, `skfl`:

1. Confirms the file has been vetted.
2. Applies any patches for the file, in order.
3. Places the result in `40_staged/`.

You can only stage vetted files. Attempt to stage an un-vetted file and `skfl` will prompt you to vet it first.

- `skfl stage <file>` — stage a file or directory of files.
- `skfl stage list` — show what's currently staged.

#### Installation

Staged files can be installed to a target directory using one of two strategies:

- `skfl install rsync <target>` (or `skfl rsync <target>`) — copies staged files to the target using `rsync`.
- `skfl install stow <target>` (or `skfl stow <target>`) — uses GNU Stow to create a symlink farm from your staging area to the target.

`skfl` knows the directory structures of several popular agentic LLM products and can install skills to the right place automatically.

### Future Directions

`skfl` may use PACKAGES of vetted files and directories to allow you to install interlocking groups of packages together. This is probably the most critical feature, since many popular packages like `superpowers` bundle together many skills that, nominally, could be installed separately or together.

`skfl` may pull from other sources, such as other skill-management tooling's package managers.

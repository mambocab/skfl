## SKFL

`skfl` (pronounced "skillful") helps you manage skills for agentic LLM products... skillfully.

### Goals and Non-Goals

`skfl` is meant to streamline the process of

- pulling skills from shared repositories like GitHub repos,
- vetting skills with your human eyes and judgement,
- managing a history of what you have and haven't read,
- maintaining patches on top of skills for your own customization purposes, and, finally,
- actually "installing" those vetted (and optionally patched) files as skills in your home directory or in a repository.

This is a lot of moving parts. `skfl` offers a layered interface onto these steps -- each can be performed in isolation, but common operations can be bundled together to make things easier. I aim for `skfl` to acknowledge fundamental complexity, like "you should read skills before you install them", and simplify everything else.

I specifically am uninterested in streamlining the most important parts of the process, in which you apply your human understanding, judgement, risk-assessment, and problem-solving skills to the use of others' text in LLM products.

I was inspired to write this by two things:

- The fear of installing malicious skills, [of which there are many](https://arxiv.org/abs/2602.06547), and
- the desire to customize skills to my own needs, particularly by making them smaller.

### Installation

In the spirit of "read before you run", `skfl` is a single Python file. Download it to your downloads path, read it, and move it to somewhere in your `$PATH`. I like `~/.local/bin`.

### Runtime Dependencies

`skfl` has Python dependencies. If you have Python smarts you can manage a virtualenv yourself if you like, but I recommend you run it as a standalone executable. This requires [installing `uv`](https://docs.astral.sh/uv/getting-started/installation/).

`skfl` will also shell out to other executables. You can check the status of your install by running `skfl doctor` (or `python <path-to-skfl> doctor` if you don't know if you have `uv` installed).

Those dependencies are:

- [`rsync`](https://rsync.samba.org/) for using `skfl package install rsync` to "install" skills to a given location using `rsync` for smart `cp`ing.
- [GNU Stow](https://www.gnu.org/software/stow/) for using `skfl package install stow` to "install" skills to a given location using `stow` to use your `skfl` repo as a symlink farm.
- [`glow`](https://github.com/charmbracelet/glow) for use as a markdown-specific pager when vetting skills.
- [`fzf`](https://github.com/junegunn/fzf) for interactive selection in a number of different workflows.

The `rsync` and `stow` subcommands have no fallbacks for these runtime dependencies.

If `glow` is not available, `less` will be used as a pager for vetting skills, same as it's used for non-markdown files.

If `fzf` is not available, commands will fail and recommend non-interactive ways for the user to specify the parameters for the operation.

### Completions

Shell completions are critical for a good `skfl` experience — they let you tab-complete source file paths, patch files, package names, and repository locations without typing them out by hand.

Generate and install completions once for your shell:

**bash** — run once, then restart your shell:
```sh
skfl completion bash > ~/.local/share/bash-completion/completions/skfl
```

**zsh** — run once, and make sure `~/.zfunc` is in your `fpath` before `compinit`:
```sh
skfl completion zsh > ~/.zfunc/_skfl
```
Add to `~/.zshrc` (before `compinit`):
```sh
fpath=(~/.zfunc $fpath)
autoload -Uz compinit && compinit
```

**fish** — run once; completions are loaded automatically:
```sh
skfl completion fish > ~/.config/fish/completions/skfl.fish
```

> Do not eval the completion script on every shell startup — that would re-invoke `skfl` (and `uv`) each time. Generate the file once and let your shell load it.

For completions to work from any directory, `skfl` falls back to `~/.skfl` if it exists. To use a different location, set `$SKFL_REPO`:
```sh
export SKFL_REPO=~/path/to/your/skfl-repo
```

### Quickstart

Start your repo at the default location of ~/.skfl.

```
$ skfl init
```

Pull in your favorite skills.

```
$ skfl source pull github owner/repo
```

Create a package of skills that you'll install as a group.

```
$ skfl package create my-fave-language
```

Add files to packages. You refer to source files by their location in your sources directory, which starts with the source type:

```
# Add an individual file to a directory in the package.
skfl package add my-fave-language github/owner/repo/skills/lang/SKILL.md lang/SKILL.md
skfl package add my-fave-language github/owner/repo/skills/conventions/SKILL.md lang-conventions/SKILL.md
```

`skfl` helps you manage patches on top of source files. (The ability to do this is one of my primary motivations for writing `skfl`; there are some useful skills out there that are too long, so I'd like to be able to split them as shown in this example.)

```
# Create a patch. `skfl` will drop you into `$EDITOR` to edit the file into your desired state and create the patch for you.
# Make sure you match the skill's name metadata to the path you intend to put it under!
skfl patch create --name querying-tickets github/owner/repo/skills/ticketing-cli/SKILL.md
# `skfl` will interactively request the name for the patch if you don't provide `--name`.
skfl patch create github/owner/repo/skills/ticketing-cli/SKILL.md
# You can add multiple versions of the same file to a single package.
skfl package add my-fave-language github/owner/repo/skills/ticketing-cli/SKILL.md querying-tickets/SKILL.md \
  --with-patch 30_patches/github/owner/repo/skills/ticketing-cli/SKILL.md.d/001-querying-tickets.patch
skfl package add my-fave-language github/owner/repo/skills/ticketing-cli/SKILL.md creating-tickets/SKILL.md \
  --with-patch 30_patches/github/owner/repo/skills/ticketing-cli/SKILL.md.d/002-creating-tickets.patch
```

Once you've curated a set of skills you're happy with, build the package and install it into a repo or your home directory using `rsync` (to copy the files) or GNU Stow (to manage files as symlinks).

```
skfl package build my-fave-language
skfl package install rsync my-fave-language ~/.some-target-dir
# or
skfl package install stow my-fave-language ~/.some-target-dir
```

### Theory of Operation

The core workflow for `skfl` is:

- Your skills and all data relating to them is managed in a REPOSITORY -- a directory full of plaintext files specifying everything described below.
- You manage a SOURCE or many SOURCES of files to use as skills -- specifying directories of skills you authored or pulling them from various remote sources.
- Before using files from your sources, `skfl` requires that you VET them by reading them. With your squishy human eyeballs. You don't have to vet every file, but `skfl` will only let you use files that have been vetted.
- You may optionally maintain PATCHES on top of vetted files. Patches let you customize skills to your own needs without modifying the source files directly, so your customizations survive source updates. You can maintain multiple patches per file; they are applied in order.
- You may organize vetted files into PACKAGES — named, installable subsets of sources. A package declares which files it contains and where they should be installed. Building a package applies all patches and stages the results ready for installation. These should be laid out the same way you want them laid out in the target, so if you want to configure both skills and agents in a `.claude` directory, your package should have top-level directories named `skills/` and `agents/`.
- Packages can be INSTALLED directly into different locations. At time of writing you can use GNU Stow or `rsync` to do so.

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
  40_packages/                # package manifests
  50_staged/                  # files ready for installation (source + patches)
```

This directory is intended to be managed as a Git repository.

#### Sources

Pull from a GitHub repository with `skfl source pull <url>` or `skfl source pull --owner <owner> --repo <repo> --ref <ref>`. If a ref isn't provided, `skfl` will recommend using a tag if one is available and let you select one interactively. This will put a shallow copy of the entire repository in `skfl`'s source cache at `10_sources/github`.

You can also register a directory of self-authored files with `skfl source custom <name> <path>`; these are managed at `10_sources/custom`.

You can update a non-custom source using `skfl source pull` again. `source pull` with no arguments will pull all sources, or you can identify a specific source to update.

#### Vetting

`skfl` tracks both the source file and your vetting state for each file. This is the key to making source updates painless.

When you first encounter a file, you vet it by reading it in full -- `skfl` opens the file in a pager (`glow` for Markdown, `less` for everything else) and, once you confirm you've reviewed it, records a hash of the file content in `20_vetted/`, mirroring the source tree structure.

When a source file changes (e.g. after `skfl source pull`), its hash no longer matches the stored vetted hash and it shows as `modified` in `skfl vet-status`. You must open and re-review the full file to re-vet it.

Check what needs vetting with `skfl vet-status`. Interactively vet files with `skfl vet`.

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

#### Packages

Packages are named, installable subsets of vetted sources. A package declares which source files it contains and where each file should appear at install time.

Key commands:

- `skfl package create <name>` — create a new empty package.
- `skfl package add <name> <source-path> <dest-path> [--with-patch <patch>]...` — add a source file to the package, optionally applying one or more named patches. `--with-patch` is repeatable.
- `skfl package build <name>` — vet-check all files, apply patches declared in the manifest, and stage the result to `50_staged/<name>/`.

#### Installation

Built packages can be installed to a target directory using one of two strategies:

- `skfl package install rsync <name> <target>` — copies the built package to the target using `rsync`.
- `skfl package install stow <name> <target>` — uses GNU Stow to create a symlink farm from the package to the target.

`skfl` knows the directory structures of several popular agentic LLM products and can install skills to the right place automatically.

### Future Directions

`skfl` may use PACKAGES of vetted files and directories to allow you to install interlocking groups of packages together. This is probably the most critical feature, since many popular packages like `superpowers` bundle together many skills that, nominally, could be installed separately or together.

`skfl` may pull from other sources, such as other skill-management tooling's package managers.

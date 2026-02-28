Y'know. You probably ought to read that markdown file before you give it to a persistent robot with no values system that has access to your whole computer.

## SKFL

`skfl` (pronounced "skillful") helps you manage skills for agentic LLM products... skillfully.

### Goals and Non-Goals

`skfl` is meant to streamline the process of

- pulling skills from common repositories like GitHub repos,
- asking you, a human with judgement and something to lose, to vet the files you want to use,
- managing a history of what you have and haven't read,
- maintaining patches on top of skills for your own customization purposes, and, FINALLY,
- actually "installing" those vetted (and optionally patched) files as skills in your home directory or in a repository.

This is a lot of moving parts. `skfl` offers s layered interface onto these steps -- each can be performed in isolation, but common operations can be bundled together to make things easier. I can't promise they'll be _easy_, but I aim for `skfl` to acknowledge fundamental complexity and simplify everything else.

### Installation

In the spirit of "read before you run", `skfl` is a single Python file. Download it to your `~/Downloads`, read it, and move it to somewhere in your `$PATH`. I like `~/.local/bin`.

#### Runtime Dependencies

It has Python dependencies. If you have Python smarts you can manage a virtualenv yourself if you like, but I recommend you run it as a standalone executable. This requires [installing `uv`](https://docs.astral.sh/uv/getting-started/installation/).

`skfl` will also shell out to other executables. You can check the status of your install by running `skfl doctor` (or `python <path-to-skfl> doctor` if you don't know if you have `uv` installed).

Those dependencies are:

<!-- LLM: Add links to sensible homepages/docs pages for each of these tools. -->

- `rsync` for using `skfl install rsync`/`skfl rsync` to "install" skills to a given location using `rsync` for "smark" `cp`ing.
- GNU Stow for using `skfl install stow`/`skfl stow` to "install" skills to a given location using `stow` to use your `skfl` repo as a symlink farm.
- `glow` for use as a markdown-specific pager when vetting skills.
- `fzf` for interactive selection in a number of different workflows.

The `rsync` and `stow` subcommands have no fallbacks for these runtime dependencies.

If `glow` is not available, `less` will be used as a pager for vetting skills, same as it's used for non-markdown files. 

If `fzf` is not available, commands will fail and recommend non-interactive ways for the user to specify the parameters for the operation.

### Theory of Operation

The core workflow for `skfl` is:

- Your skills and all data relating to them is managed in a REPOSITORY -- a directory full of plaintext files specifying everything described below.
- You manage a SOURCE or many SOURCES of files to use as skills -- specifying directories of skills you authored or pulling them from various remote sources.
- Before using files from your sources, `skfl` requires that you VET them by reading them. With your squishy human eyeballs. You don't have to vet every file, but `skfl` will only let you use files that have been vetted.
- `skfl` can STAGE files from your sources into a STAGING area. <!-- LLM: Is there a better way to phrase that? --> By staging a file, you're explicitly declaring your intent to use it in a skill. Since that's the intent, if you attempt to stage an un-vetted file, `skfl` will ask you to vet a file before it will stage it.
- Staged files (and directories of staged files) can be INSTALLED directly into different locations. `skfl` can be pointed explicitly at a target directory, but it also comes pre-programmed with the directory structure of a few of the popular agentic LLM products and can, for example, be told to install a Kiro Power or a Claude Agent in the appropriate directory.

<!-- LLM: I wrote following H4s in this H3 quickly. We'll want to expand it later. If this comment is present, the design has not yet been fully thought through. -->

#### Repository

Start a repository with `skfl init`. This will create, among other things, a `skfl.toml` and  `.gitignore` file. This directory is intended to be managed as a Git repository.

#### Sources

Pull from a GitHub repository with `skfl source pull -- <url>` or `skfl source pull github --owner <owner> --repo <repo> --ref <ref>`. <!-- LLM: If a ref isn't provided, there'll be an interactive process where the user is recommneded to use a tag if available, then select a tag. --> This will put a shallow copy of the entire repository in `skfl`'s source cache at `10_sources/github`.

You can also register a new source of self-authored files with `skfl source custom`; these are managed at `10_sources/custom`. <!-- I don't realy love the word custom here. -->

You can update a non-`custom` source using `skfi source pull` again. `source pull` will pull all sources, or you can identify the source by directory name.

#### Vetting

Typically you won't vet a file until you need to for staging.

#### New Sources



#### 

#### Staging

Note that we're skipping the vetting stage. 

## Future Directions

`skfl` may use PACKAGES of vetted files and directories to allow you to install interlocking groups of packages together. This is probably the most critical feature, since many popular packages like `superpowers` bundle together many skills that, nominally, could be installed separately or together.

`skfl` may pull from other sources, such as other skill-management tooling's package managers.

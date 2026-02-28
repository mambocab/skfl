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

It has dependencies. If you have Python smarts you can manage a virtualenv yourself if you like, but I recommend you run it as a standalone executable. This requires [installing `uv`](https://docs.astral.sh/uv/getting-started/installation/).

#### Runtime Dependencies

`skfl` will shell out to other executables. You can check the status of your install by running `skfl doctor` (or `python <path-to-skfl> doctor` if you don't know if you have `uv` installed).

Those dependencies are:

<!-- LLM: Add links to sensible homepages/docs pages for each of these tools. -->

- `rsync` for using `skfl install rsync` to "install" skills to a given location using `rsync` for "smark" `cp`ing.
- GNU Stow for using `skfl install stow` to "install" skills to a given location using `stow` to use your `skfl` repo as a symlink farm.
- `glow` for use as a markdown-specific pager when vetting skills.

The `install rsync` and `install stow` subcommands have no fallbacks for these runtime dependencies. If `glow` is not available, `less` will be used as a pager for vetting skills.

### Theory of Operation

Skills can come from a number of sources. You can write them yourself

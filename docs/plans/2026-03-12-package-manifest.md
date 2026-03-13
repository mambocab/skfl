# Package Manifest Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace symlink-based package definitions with `package.toml` manifests that support per-entry explicit patch lists, swap directory numbering (40↔50), and remove profiles.

**Architecture:** Each package is defined by `40_packages/<name>/package.toml` (a TOML file with `[[file]]` entries). `package build` reads the manifest, vets sources, applies only the explicitly listed patches, and stages to `50_staged/<name>/`. Profile support (`--as`, `_profiles/`, `_complete_profiles`) is removed entirely. `_stage_single_file` is simplified to accept an explicit patch list instead of discovering patches automatically.

**Tech Stack:** Python 3.11 (`tomllib` stdlib for reading), `tomli-w` (already a dependency) for writing, Click 8.x, pytest.

---

### Task 1: Rename directory constants and update REPO_DIRS

**Files:**
- Modify: `skfl` (lines 26-27, 31)
- Modify: `tests/test_skfl.py` (all references to `STAGED_DIR` value `"40_staged"` and `PACKAGES_DIR` value `"50_packages"`)

The two constants swap values; tests that hardcode the string paths must be updated too.

**Step 1: Write the failing test**

In `tests/test_skfl.py`, find `TestInit` (the class that tests `skfl init`). Add:

```python
def test_repo_dirs_order(self, tmp_path):
    """Packages (40) must come before staged (50)."""
    runner = CliRunner()
    runner.invoke(skfl.cli, ["init", str(tmp_path / "repo")])
    assert skfl.PACKAGES_DIR.startswith("4")
    assert skfl.STAGED_DIR.startswith("5")
```

**Step 2: Run to verify it fails**

Run: `just test 2>&1 | grep test_repo_dirs_order`
Expected: FAILED

**Step 3: Swap the constants in `skfl`**

Change:
```python
STAGED_DIR = "40_staged"
PACKAGES_DIR = "50_packages"
```
To:
```python
PACKAGES_DIR = "40_packages"
STAGED_DIR = "50_staged"
```

**Step 4: Update `REPO_DIRS` list order**

In `skfl`, find `REPO_DIRS = [...]` and reorder to match the new numbering (packages before staged):
```python
REPO_DIRS = [SOURCES_DIR, VETTED_DIR, PATCHES_DIR, PACKAGES_DIR, STAGED_DIR]
```

**Step 5: Update hardcoded strings in tests**

In `tests/test_skfl.py`, search for any test that references the old string values `"40_staged"` or `"50_packages"` and update them. Use `skfl.STAGED_DIR` and `skfl.PACKAGES_DIR` references where possible. Also update `do_build_package`'s echo message in `skfl` which hardcodes `"40_staged/{name}/"`.

**Step 6: Run tests**

Run: `just test 2>&1 | tail -5`
Expected: all pass (or only failures related to features not yet implemented)

**Step 7: Commit**

```bash
git add skfl tests/test_skfl.py
git commit -m "rename: swap 40_staged/50_packages to 40_packages/50_staged"
```

---

### Task 2: Add manifest read/write helpers

**Files:**
- Modify: `skfl` (add two functions after `resolve_package_files`, around line 300)
- Modify: `tests/test_skfl.py` (new `TestPackageManifest` class)

`tomllib` is stdlib in Python 3.11+. `tomli_w` is already imported.

**Step 1: Write failing tests**

Add to `tests/test_skfl.py`:

```python
class TestPackageManifest:
    def test_read_empty_manifest(self, repo):
        runner = CliRunner()
        runner.invoke(skfl.cli, ["package", "init", "mypkg"])
        entries = skfl.read_package_manifest(repo, "mypkg")
        assert entries == []

    def test_read_manifest_with_entries(self, repo):
        pkg_dir = repo / skfl.PACKAGES_DIR / "mypkg"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "package.toml").write_text(
            '[[file]]\nsource = "custom/a.md"\ndest = "skills/a.md"\n'
        )
        entries = skfl.read_package_manifest(repo, "mypkg")
        assert len(entries) == 1
        assert entries[0]["source"] == "custom/a.md"
        assert entries[0]["dest"] == "skills/a.md"
        assert entries[0].get("patches", []) == []

    def test_read_manifest_with_patches(self, repo):
        pkg_dir = repo / skfl.PACKAGES_DIR / "mypkg"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "package.toml").write_text(
            '[[file]]\nsource = "custom/a.md"\ndest = "skills/a.md"\n'
            'patches = ["30_patches/custom/a.md.d/001.patch"]\n'
        )
        entries = skfl.read_package_manifest(repo, "mypkg")
        assert entries[0]["patches"] == ["30_patches/custom/a.md.d/001.patch"]

    def test_read_missing_package_raises(self, repo):
        with pytest.raises(click.ClickException):
            skfl.read_package_manifest(repo, "nonexistent")

    def test_write_then_read_roundtrip(self, repo):
        pkg_dir = repo / skfl.PACKAGES_DIR / "mypkg"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "package.toml").write_text("")
        entries = [
            {"source": "custom/a.md", "dest": "skills/a.md", "patches": ["30_patches/custom/a.md.d/001.patch"]},
            {"source": "custom/b.md", "dest": "skills/b.md"},
        ]
        skfl.write_package_manifest(repo, "mypkg", entries)
        result = skfl.read_package_manifest(repo, "mypkg")
        assert len(result) == 2
        assert result[0]["source"] == "custom/a.md"
        assert result[0]["patches"] == ["30_patches/custom/a.md.d/001.patch"]
        assert result[1]["source"] == "custom/b.md"
        assert result[1].get("patches", []) == []
```

**Step 2: Run to verify failures**

Run: `just test 2>&1 | grep TestPackageManifest`
Expected: errors (functions don't exist yet)

**Step 3: Implement the helpers in `skfl`**

Add after the existing `all_patch_files` function:

```python
def read_package_manifest(repo: Path, name: str) -> list[dict]:
    """Read 40_packages/<name>/package.toml and return list of file entries."""
    manifest_path = repo / PACKAGES_DIR / name / "package.toml"
    if not manifest_path.is_file():
        raise click.ClickException(f"Package '{name}' not found.")
    with open(manifest_path, "rb") as f:
        data = tomllib.load(f)
    return data.get("file", [])


def write_package_manifest(repo: Path, name: str, entries: list[dict]) -> None:
    """Write file entries to 40_packages/<name>/package.toml."""
    manifest_path = repo / PACKAGES_DIR / name / "package.toml"
    data = {"file": [dict(e) for e in entries]}
    # Remove empty patch lists before writing (patches key is optional)
    for entry in data["file"]:
        if not entry.get("patches"):
            entry.pop("patches", None)
    manifest_path.write_bytes(tomli_w.dumps(data).encode())
```

**Step 4: Run tests**

Run: `just test 2>&1 | tail -5`
Expected: `TestPackageManifest` passes, all others still pass.

**Step 5: Commit**

```bash
git add skfl tests/test_skfl.py
git commit -m "feat: add read_package_manifest/write_package_manifest helpers"
```

---

### Task 3: Rewrite `package init`

**Files:**
- Modify: `skfl` (`package_new` function, around line 930)
- Modify: `tests/test_skfl.py` (`TestPackageNew` class, around line 1273)

**Step 1: Update the existing test**

Find `TestPackageNew` in `tests/test_skfl.py`. Replace:

```python
class TestPackageNew:
    def test_package_init_creates_directory(self, repo):
        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["package", "init", "my-pkg"])
        assert result.exit_code == 0
        assert (repo / skfl.PACKAGES_DIR / "my-pkg").is_dir()
```

With:

```python
class TestPackageNew:
    def test_package_init_creates_manifest(self, repo):
        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["package", "init", "my-pkg"])
        assert result.exit_code == 0
        manifest = repo / skfl.PACKAGES_DIR / "my-pkg" / "package.toml"
        assert manifest.is_file()

    def test_package_init_manifest_is_empty(self, repo):
        runner = CliRunner()
        runner.invoke(skfl.cli, ["package", "init", "my-pkg"])
        entries = skfl.read_package_manifest(repo, "my-pkg")
        assert entries == []

    def test_package_init_duplicate_fails(self, repo):
        runner = CliRunner()
        runner.invoke(skfl.cli, ["package", "init", "my-pkg"])
        result = runner.invoke(skfl.cli, ["package", "init", "my-pkg"])
        assert result.exit_code != 0
```

**Step 2: Run to verify failures**

Run: `just test 2>&1 | grep TestPackageNew`
Expected: some FAILED

**Step 3: Rewrite `package_new` in `skfl`**

```python
@package.command("init")
@click.argument("name")
def package_new(name):
    """Create a new empty package."""
    r = find_repo()
    pkg_dir = r / PACKAGES_DIR / name
    manifest_path = pkg_dir / "package.toml"
    if manifest_path.exists():
        raise click.ClickException(f"Package '{name}' already exists.")
    pkg_dir.mkdir(parents=True, exist_ok=True)
    write_package_manifest(r, name, [])
    click.echo(f"Created package '{name}' at {pkg_dir.relative_to(r)}.")
```

**Step 4: Run tests**

Run: `just test 2>&1 | tail -5`
Expected: all pass

**Step 5: Commit**

```bash
git add skfl tests/test_skfl.py
git commit -m "feat: package init creates package.toml manifest"
```

---

### Task 4: Rewrite `package add`

**Files:**
- Modify: `skfl` (`package_add` function, around line 961)
- Modify: `tests/test_skfl.py` (`TestPackageAdd` class)

**Step 1: Write failing tests**

Find `TestPackageAdd` in `tests/test_skfl.py`. Replace its entire contents with:

```python
class TestPackageAdd:
    def test_add_appends_entry(self, repo_with_source):
        runner = CliRunner()
        runner.invoke(skfl.cli, ["package", "init", "mypkg"])
        result = runner.invoke(
            skfl.cli,
            ["package", "add", "mypkg", "custom/test-src/hello.md", "skills/hello.md"],
        )
        assert result.exit_code == 0, result.output
        entries = skfl.read_package_manifest(repo_with_source, "mypkg")
        assert len(entries) == 1
        assert entries[0]["source"] == "custom/test-src/hello.md"
        assert entries[0]["dest"] == "skills/hello.md"
        assert entries[0].get("patches", []) == []

    def test_add_with_patch(self, repo_with_source):
        runner = CliRunner()
        runner.invoke(skfl.cli, ["package", "init", "mypkg"])
        # Create a dummy patch file
        pdir = skfl.patches_dir_for(repo_with_source, Path("custom/test-src/hello.md"))
        pdir.mkdir(parents=True)
        patch_path = pdir / "001-test.patch"
        patch_path.write_text("--- a\n+++ b\n")
        patch_rel = str(patch_path.relative_to(repo_with_source))

        result = runner.invoke(
            skfl.cli,
            ["package", "add", "mypkg", "custom/test-src/hello.md", "skills/hello.md",
             "--with-patch", patch_rel],
        )
        assert result.exit_code == 0, result.output
        entries = skfl.read_package_manifest(repo_with_source, "mypkg")
        assert entries[0]["patches"] == [patch_rel]

    def test_add_multiple_patches(self, repo_with_source):
        runner = CliRunner()
        runner.invoke(skfl.cli, ["package", "init", "mypkg"])
        pdir = skfl.patches_dir_for(repo_with_source, Path("custom/test-src/hello.md"))
        pdir.mkdir(parents=True)
        p1 = pdir / "001-first.patch"
        p2 = pdir / "002-second.patch"
        p1.write_text("--- a\n+++ b\n")
        p2.write_text("--- a\n+++ b\n")
        rel1 = str(p1.relative_to(repo_with_source))
        rel2 = str(p2.relative_to(repo_with_source))

        runner.invoke(
            skfl.cli,
            ["package", "add", "mypkg", "custom/test-src/hello.md", "skills/hello.md",
             "--with-patch", rel1, "--with-patch", rel2],
        )
        entries = skfl.read_package_manifest(repo_with_source, "mypkg")
        assert entries[0]["patches"] == [rel1, rel2]

    def test_add_same_source_twice_different_dests(self, repo_with_source):
        runner = CliRunner()
        runner.invoke(skfl.cli, ["package", "init", "mypkg"])
        runner.invoke(
            skfl.cli,
            ["package", "add", "mypkg", "custom/test-src/hello.md", "skills/intro.md"],
        )
        result = runner.invoke(
            skfl.cli,
            ["package", "add", "mypkg", "custom/test-src/hello.md", "skills/advanced.md"],
        )
        assert result.exit_code == 0, result.output
        entries = skfl.read_package_manifest(repo_with_source, "mypkg")
        assert len(entries) == 2

    def test_add_duplicate_dest_fails(self, repo_with_source):
        runner = CliRunner()
        runner.invoke(skfl.cli, ["package", "init", "mypkg"])
        runner.invoke(
            skfl.cli,
            ["package", "add", "mypkg", "custom/test-src/hello.md", "skills/hello.md"],
        )
        result = runner.invoke(
            skfl.cli,
            ["package", "add", "mypkg", "custom/test-src/hello.md", "skills/hello.md"],
        )
        assert result.exit_code != 0
        assert "already exists" in result.output

    def test_add_source_outside_sources_dir_fails(self, repo):
        runner = CliRunner()
        runner.invoke(skfl.cli, ["package", "init", "mypkg"])
        result = runner.invoke(
            skfl.cli,
            ["package", "add", "mypkg", "/etc/passwd", "skills/bad.md"],
        )
        assert result.exit_code != 0

    def test_add_missing_source_fails(self, repo):
        runner = CliRunner()
        runner.invoke(skfl.cli, ["package", "init", "mypkg"])
        result = runner.invoke(
            skfl.cli,
            ["package", "add", "mypkg", "custom/nonexistent.md", "skills/x.md"],
        )
        assert result.exit_code != 0

    def test_add_missing_patch_fails(self, repo_with_source):
        runner = CliRunner()
        runner.invoke(skfl.cli, ["package", "init", "mypkg"])
        result = runner.invoke(
            skfl.cli,
            ["package", "add", "mypkg", "custom/test-src/hello.md", "skills/hello.md",
             "--with-patch", "30_patches/nonexistent.patch"],
        )
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_add_to_missing_package_fails(self, repo_with_source):
        runner = CliRunner()
        result = runner.invoke(
            skfl.cli,
            ["package", "add", "nopkg", "custom/test-src/hello.md", "skills/hello.md"],
        )
        assert result.exit_code != 0
```

**Step 2: Run to verify failures**

Run: `just test 2>&1 | grep TestPackageAdd`
Expected: many FAILED

**Step 3: Rewrite `package_add` in `skfl`**

```python
@package.command("add")
@click.argument("name", shell_complete=_complete_packages)
@click.argument("source_path", type=click.Path(), shell_complete=_complete_source_files)
@click.argument("dest_path", type=click.Path())
@click.option("--with-patch", "patches", multiple=True, type=click.Path(),
              shell_complete=_complete_patch_files,
              help="Patch to apply to this file (may be repeated, applied in order).")
def package_add(name, source_path, dest_path, patches):
    """Add a source file to a package.

    SOURCE_PATH is relative to 10_sources/.
    DEST_PATH is where the file appears at install time.
    """
    r = find_repo()
    manifest_path = r / PACKAGES_DIR / name / "package.toml"
    if not manifest_path.is_file():
        raise click.ClickException(
            f"Package '{name}' not found. Run 'skfl package init {name}' first."
        )

    sources = r / SOURCES_DIR
    try:
        rel = resolve_to_source_rel(r, source_path)
    except ValueError:
        raise click.ClickException(
            f"Source path '{source_path}' is not inside the sources directory."
        )

    source_abs = sources / rel
    if not source_abs.exists():
        raise click.ClickException(f"Source not found: {source_abs}")

    for p in patches:
        patch_path = r / p if not Path(p).is_absolute() else Path(p)
        if not patch_path.is_file():
            raise click.ClickException(f"Patch file not found: {p}")

    entries = read_package_manifest(r, name)
    if any(e["dest"] == dest_path for e in entries):
        raise click.ClickException(
            f"Destination '{dest_path}' already exists in package '{name}'."
        )

    entry: dict = {"source": str(rel), "dest": dest_path}
    if patches:
        entry["patches"] = list(patches)
    entries.append(entry)
    write_package_manifest(r, name, entries)
    click.echo(f"  added: {dest_path} <- {rel}")
```

**Step 4: Run tests**

Run: `just test 2>&1 | tail -5`
Expected: all pass

**Step 5: Commit**

```bash
git add skfl tests/test_skfl.py
git commit -m "feat: package add writes manifest entries with optional --with-patch"
```

---

### Task 5: Simplify `_stage_single_file` and rewrite `package build`

**Files:**
- Modify: `skfl` (`_stage_single_file`, `do_build_package`, `package_build`, around lines 226–334)
- Modify: `tests/test_skfl.py` (`TestPackageBuild` class)

**Step 1: Write failing tests**

Find `TestPackageBuild` and replace with:

```python
class TestPackageBuild:
    def _add_file(self, runner, repo, pkg, source_rel, dest, patches=()):
        args = ["package", "add", pkg, source_rel, dest]
        for p in patches:
            args += ["--with-patch", p]
        runner.invoke(skfl.cli, args)

    def test_build_no_patches(self, repo_with_vetted):
        repo = repo_with_vetted
        runner = CliRunner()
        runner.invoke(skfl.cli, ["package", "init", "mypkg"])
        self._add_file(runner, repo, "mypkg", "custom/test-src/hello.md", "skills/hello.md")

        result = runner.invoke(skfl.cli, ["package", "build", "mypkg"])
        assert result.exit_code == 0, result.output

        staged = repo / skfl.STAGED_DIR / "mypkg" / "skills" / "hello.md"
        assert staged.is_file()
        source = repo / skfl.SOURCES_DIR / "custom/test-src/hello.md"
        assert staged.read_bytes() == source.read_bytes()

    def test_build_with_patch(self, repo_with_vetted, tmp_path):
        repo = repo_with_vetted
        runner = CliRunner()
        rel = Path("custom/test-src/hello.md")
        original = (repo / skfl.SOURCES_DIR / rel).read_bytes()
        modified = original.replace(b"World", b"Universe")

        orig_f = tmp_path / "orig"
        new_f = tmp_path / "new"
        orig_f.write_bytes(original)
        new_f.write_bytes(modified)
        proc = subprocess.run(["diff", "-u", str(orig_f), str(new_f)], capture_output=True)

        pdir = skfl.patches_dir_for(repo, rel)
        pdir.mkdir(parents=True)
        patch_file = pdir / "001-universe.patch"
        patch_file.write_bytes(proc.stdout)
        patch_rel = str(patch_file.relative_to(repo))

        runner.invoke(skfl.cli, ["package", "init", "mypkg"])
        self._add_file(runner, repo, "mypkg", str(rel), "skills/hello.md", patches=[patch_rel])

        result = runner.invoke(skfl.cli, ["package", "build", "mypkg"])
        assert result.exit_code == 0, result.output

        staged = repo / skfl.STAGED_DIR / "mypkg" / "skills" / "hello.md"
        assert b"Universe" in staged.read_bytes()
        assert b"World" not in staged.read_bytes()

    def test_build_same_source_multiple_dests_different_patches(self, repo_with_vetted, tmp_path):
        repo = repo_with_vetted
        runner = CliRunner()
        rel = Path("custom/test-src/hello.md")
        original = (repo / skfl.SOURCES_DIR / rel).read_bytes()

        def make_patch(find, replace, name):
            pdir = skfl.patches_dir_for(repo, rel)
            pdir.mkdir(parents=True, exist_ok=True)
            modified = original.replace(find, replace)
            orig_f = tmp_path / f"{name}.orig"
            new_f = tmp_path / f"{name}.new"
            orig_f.write_bytes(original)
            new_f.write_bytes(modified)
            proc = subprocess.run(["diff", "-u", str(orig_f), str(new_f)], capture_output=True)
            p = pdir / f"{name}.patch"
            p.write_bytes(proc.stdout)
            return str(p.relative_to(repo))

        p1 = make_patch(b"World", b"Universe", "001-universe")
        p2 = make_patch(b"World", b"Earth", "002-earth")

        runner.invoke(skfl.cli, ["package", "init", "mypkg"])
        self._add_file(runner, repo, "mypkg", str(rel), "skills/intro.md", patches=[p1])
        self._add_file(runner, repo, "mypkg", str(rel), "skills/advanced.md", patches=[p2])

        result = runner.invoke(skfl.cli, ["package", "build", "mypkg"])
        assert result.exit_code == 0, result.output

        intro = (repo / skfl.STAGED_DIR / "mypkg" / "skills" / "intro.md").read_bytes()
        advanced = (repo / skfl.STAGED_DIR / "mypkg" / "skills" / "advanced.md").read_bytes()
        assert b"Universe" in intro
        assert b"Earth" in advanced

    def test_build_unvetted_drops_into_vet_flow(self, repo_with_source):
        runner = CliRunner()
        runner.invoke(skfl.cli, ["package", "init", "mypkg"])
        runner.invoke(
            skfl.cli,
            ["package", "add", "mypkg", "custom/test-src/hello.md", "skills/hello.md"],
        )
        result = runner.invoke(skfl.cli, ["package", "build", "mypkg"])
        assert result.exit_code != 0

    def test_build_missing_patch_file_fails(self, repo_with_vetted):
        repo = repo_with_vetted
        runner = CliRunner()
        runner.invoke(skfl.cli, ["package", "init", "mypkg"])
        # Manually write a manifest with a nonexistent patch
        pkg_dir = repo / skfl.PACKAGES_DIR / "mypkg"
        (pkg_dir / "package.toml").write_text(
            '[[file]]\nsource = "custom/test-src/hello.md"\n'
            'dest = "skills/hello.md"\n'
            'patches = ["30_patches/nonexistent.patch"]\n'
        )
        result = runner.invoke(skfl.cli, ["package", "build", "mypkg"])
        assert result.exit_code != 0
        assert "not found" in result.output
```

**Step 2: Run to verify failures**

Run: `just test 2>&1 | grep TestPackageBuild`
Expected: many FAILED

**Step 3: Simplify `_stage_single_file`**

Replace the current signature (which auto-discovers patches) with one that takes an explicit list:

```python
def _stage_single_file(
    source_abs: Path,
    staged_path: Path,
    patch_paths: list[Path],
) -> int:
    """Read source, apply patches, write to staged location. Returns patch count."""
    content = source_abs.read_bytes()
    if patch_paths:
        content = apply_patches(content, patch_paths)
    staged_path.parent.mkdir(parents=True, exist_ok=True)
    staged_path.write_bytes(content)
    if os.access(source_abs, os.X_OK):
        staged_path.chmod(staged_path.stat().st_mode | 0o111)
    return len(patch_paths)
```

**Step 4: Rewrite `do_build_package`**

```python
def do_build_package(repo: Path, name: str) -> None:
    """Build a package: read manifest, vet sources, apply patches, stage."""
    entries = read_package_manifest(repo, name)
    if not entries:
        raise click.ClickException(f"Package '{name}' has no files.")

    sources = repo / SOURCES_DIR

    for entry in entries:
        rel = Path(entry["source"])
        dest_rel = Path(entry["dest"])
        patch_strs = entry.get("patches", [])

        source_abs = sources / rel
        if not source_abs.is_file():
            raise click.ClickException(f"Source not found: {rel}")

        # Validate patch files exist before touching disk
        patch_paths = []
        for p in patch_strs:
            patch_path = repo / p
            if not patch_path.is_file():
                raise click.ClickException(f"Patch not found: {p}")
            patch_paths.append(patch_path)

        # Vet check — drop into interactive flow
        status = vet_status_for_file(repo, rel)
        if status in ("unvetted", "modified"):
            if not vet_single_file(repo, rel):
                raise click.ClickException(
                    f"Cannot build package: {rel} was not vetted."
                )

        staged_path = repo / STAGED_DIR / name / dest_rel
        n = _stage_single_file(source_abs, staged_path, patch_paths)
        patch_note = f" ({n} patch{'es' if n != 1 else ''} applied)" if n else ""
        click.echo(f"  staged: {dest_rel}{patch_note}")

    click.echo(f"Built package '{name}': {len(entries)} file(s) staged to {STAGED_DIR}/{name}/.")
```

**Step 5: Rewrite `package_build` command (remove `--as`)**

```python
@package.command("build")
@click.argument("name", shell_complete=_complete_packages)
def package_build(name):
    """Build a package: vet-check, apply patches, stage to 50_staged/<name>/."""
    r = find_repo()
    do_build_package(r, name)
```

**Step 6: Run tests**

Run: `just test 2>&1 | tail -5`
Expected: all pass (or only pre-existing failures)

**Step 7: Commit**

```bash
git add skfl tests/test_skfl.py
git commit -m "feat: package build reads manifest, applies per-entry patches"
```

---

### Task 6: Update `package show` and `package list`

**Files:**
- Modify: `skfl` (`package_show`, `package_list`, around lines 942–1033)
- Modify: `tests/test_skfl.py` (`TestPackageShow` class)

**Step 1: Write failing tests**

Find `TestPackageShow` (or add it) in `tests/test_skfl.py`:

```python
class TestPackageShow:
    def test_show_empty_package(self, repo):
        runner = CliRunner()
        runner.invoke(skfl.cli, ["package", "init", "mypkg"])
        result = runner.invoke(skfl.cli, ["package", "show", "mypkg"])
        assert result.exit_code == 0
        assert "no files" in result.output

    def test_show_renders_tree(self, repo_with_source):
        runner = CliRunner()
        runner.invoke(skfl.cli, ["package", "init", "mypkg"])
        runner.invoke(skfl.cli, ["package", "add", "mypkg",
                                  "custom/test-src/hello.md", "skills/hello.md"])
        runner.invoke(skfl.cli, ["package", "add", "mypkg",
                                  "custom/test-src/script.py", "scripts/helper.py"])
        result = runner.invoke(skfl.cli, ["package", "show", "mypkg"])
        assert result.exit_code == 0
        assert "mypkg" in result.output
        assert "hello.md" in result.output
        assert "helper.py" in result.output

    def test_show_missing_package_fails(self, repo):
        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["package", "show", "nope"])
        assert result.exit_code != 0
```

**Step 2: Run to verify**

Run: `just test 2>&1 | grep TestPackageShow`
Expected: some FAILED (show currently uses `resolve_package_files` which uses symlinks)

**Step 3: Update `package_show` to read manifest**

```python
@package.command("show")
@click.argument("name", shell_complete=_complete_packages)
def package_show(name):
    """Show files in a package as a tree."""
    r = find_repo()
    entries = read_package_manifest(r, name)
    if not entries:
        click.echo(f"Package '{name}' has no files.")
        return

    tree: dict = {}
    for entry in entries:
        dest_rel = Path(entry["dest"])
        node = tree
        for part in dest_rel.parts[:-1]:
            node = node.setdefault(part, {})
        node[dest_rel.parts[-1]] = None

    def render(node: dict, prefix: str = "") -> None:
        entries_list = sorted(node.keys(), key=lambda k: (node[k] is not None, k))
        for i, key in enumerate(entries_list):
            connector = "└── " if i == len(entries_list) - 1 else "├── "
            child = node[key]
            click.echo(prefix + connector + key)
            if child is not None:
                extension = "    " if i == len(entries_list) - 1 else "│   "
                render(child, prefix + extension)

    click.echo(name)
    render(tree)
```

**Step 4: Update `package_list` to detect packages by manifest existence**

```python
@package.command("list")
def package_list():
    """List all defined packages."""
    r = find_repo()
    pkgs_dir = r / PACKAGES_DIR
    if not pkgs_dir.is_dir():
        click.echo("No packages defined.")
        return
    packages = sorted(
        p.name for p in pkgs_dir.iterdir()
        if p.is_dir() and (p / "package.toml").is_file()
    )
    if not packages:
        click.echo("No packages defined.")
        return
    for name in packages:
        click.echo(f"  {name}")
```

**Step 5: Run tests**

Run: `just test 2>&1 | tail -5`
Expected: all pass

**Step 6: Commit**

```bash
git add skfl tests/test_skfl.py
git commit -m "feat: package show/list read from manifest"
```

---

### Task 7: Remove profile code and dead symlink code

**Files:**
- Modify: `skfl` (remove `_collect_symlinks`, `resolve_package_files`, `profile_patches_dir_for`, `_complete_profiles`, profile logic from `list_patches_for`)
- Modify: `tests/test_skfl.py` (remove all profile-related tests and references)

**Step 1: Remove from `skfl`**

Delete:
- `_collect_symlinks` function
- `resolve_package_files` function
- `profile_patches_dir_for` function
- `_complete_profiles` function and its `# ── _complete_profiles ──` section header (around line 498)
- In `list_patches_for`: remove the `if profile:` block and `profile` parameter — simplify to just return default patches for a file:

```python
def list_patches_for(repo: Path, rel: Path) -> list[Path]:
    """List patches for a source file (files in its .d directory, sorted)."""
    patches = []
    d = patches_dir_for(repo, rel)
    if d.is_dir():
        patches.extend(sorted(p for p in d.iterdir() if p.suffix == ".patch"))
    return patches
```

Note: `list_patches_for` is still used by `patch list` command — keep it.

**Step 2: Remove from tests**

Delete from `tests/test_skfl.py`:
- `TestProfilePatchesDirFor` class
- `TestListPatchesFor` tests that test the profile parameter (keep tests for default patches)
- `_complete_profiles` tests in `TestCompletionHelpers` (the block from `# ── _complete_profiles ──` through `test_profiles_ignores_files_in_profiles_dir`)
- Wiring test `test_package_build_profile_wired` in `TestCompletionWiring`
- Test `test_patch_files_profile_patches_included` in `TestCompletionHelpers`

**Step 3: Run tests**

Run: `just test 2>&1 | tail -5`
Expected: all pass

**Step 4: Commit**

```bash
git add skfl tests/test_skfl.py
git commit -m "remove: profiles, symlink-based package code, dead helpers"
```

---

### Task 8: Update `_resolve_install_paths` and install commands

**Files:**
- Modify: `skfl` (`_resolve_install_paths`, around line 1045)

The only change here is that `_resolve_install_paths` currently calls `do_build_package(repo, name)` to auto-build if `50_staged/<name>/` doesn't exist. Update the path (already updated by constant rename) and remove the profile arg.

**Step 1: Verify `_resolve_install_paths` still works**

After the constant rename in Task 1, `STAGED_DIR` already points to `"50_staged"` so the path is correct. But the auto-build call `do_build_package(repo, name)` no longer takes a `profile` arg (removed in Task 5). Verify the signature matches.

Run: `just test 2>&1 | grep install`
Expected: install tests pass

**Step 2: If any failures, fix `_resolve_install_paths`**

```python
def _resolve_install_paths(repo: Path, name: str, tool: str, target: str) -> tuple[Path, Path]:
    staged = repo / STAGED_DIR / name
    if not staged.is_dir():
        do_build_package(repo, name)
    if not shutil.which(tool):
        raise click.ClickException(f"{tool} is not installed. Install it and try again.")
    target_path = Path(target).resolve()
    target_path.mkdir(parents=True, exist_ok=True)
    return staged, target_path
```

**Step 3: Run full test suite**

Run: `just test 2>&1 | tail -5`
Expected: all pass

**Step 4: Commit if changes were needed**

```bash
git add skfl
git commit -m "fix: update _resolve_install_paths for new do_build_package signature"
```

---

### Task 9: Update README and completion wiring tests

**Files:**
- Modify: `README.md`
- Modify: `tests/test_skfl.py` (wiring tests referencing removed profile)

**Step 1: Remove stale wiring tests**

In `TestCompletionWiring`, delete:
- `test_package_build_profile_wired` (references `skfl._complete_profiles` which no longer exists)

Add wiring test for `--with-patch`:
```python
def test_package_add_with_patch_wired(self):
    assert self._custom_complete(skfl.package_add, "patches") is skfl._complete_patch_files
```

**Step 2: Update README**

In `README.md`, update the Packages section to reflect the new `package add --with-patch` option and remove profile references. Key lines to update:

- `skfl package add <name> <source-path> <dest-path>` → add `[--with-patch <patch>]...`
- `skfl package build <name>` — remove `--as <profile>` mention
- Remove any mention of profiles

**Step 3: Run full test suite**

Run: `just test 2>&1 | tail -5`
Expected: all pass, 0 failures

**Step 4: Commit**

```bash
git add README.md tests/test_skfl.py
git commit -m "docs: update README and wiring tests for manifest-based packages"
```

---

### Task 10: Final verification

**Step 1: Run full test suite clean**

Run: `just test`
Expected: all pass

**Step 2: Smoke-test the CLI**

Run: `./skfl --help`
Expected: no `stage` in output, `package` group present

Run: `./skfl package --help`
Expected: `init`, `add`, `build`, `show`, `list`, `install` — no `--as` on `build`

**Step 3: Verify directory structure in a dev shell**

Run: `./dev-shell`
Then inside: `skfl init /tmp/test-repo && ls /tmp/test-repo`
Expected: `40_packages/  50_staged/` (new numbering)

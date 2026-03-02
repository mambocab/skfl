"""Unit tests for skfl."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch as mock_patch

import pytest
from click.testing import CliRunner

# Import the skfl module by path (no .py extension)
import importlib.util
import importlib.machinery

SKFL_PATH = Path(__file__).parent.parent / "skfl"
loader = importlib.machinery.SourceFileLoader("skfl_mod", str(SKFL_PATH))
spec = importlib.util.spec_from_loader("skfl_mod", loader, origin=str(SKFL_PATH))
skfl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(skfl)


@pytest.fixture
def tmp_dir(tmp_path):
    """Provide a clean temporary directory and chdir into it."""
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(old_cwd)


@pytest.fixture
def repo(tmp_dir):
    """Provide an initialized skfl repository."""
    runner = CliRunner()
    result = runner.invoke(skfl.cli, ["init", str(tmp_dir)])
    assert result.exit_code == 0
    return tmp_dir


@pytest.fixture
def repo_with_source(repo):
    """Provide a repo with a custom source containing test files."""
    source_dir = repo / "src_files"
    source_dir.mkdir()
    (source_dir / "hello.md").write_text("# Hello\n\nWorld\n")
    (source_dir / "script.py").write_text("print('hello')\n")
    (source_dir / "sub").mkdir()
    (source_dir / "sub" / "nested.txt").write_text("nested content\n")

    runner = CliRunner()
    result = runner.invoke(skfl.cli, ["source", "custom", "test-src", str(source_dir)])
    assert result.exit_code == 0
    return repo


@pytest.fixture
def repo_with_vetted(repo_with_source):
    """Provide a repo with custom source files that have been vetted."""
    repo = repo_with_source
    sources = repo / skfl.SOURCES_DIR
    # Manually vet all files by storing their hashes
    for src_file in sources.rglob("*"):
        if src_file.is_file() and src_file.name != ".gitkeep":
            rel = src_file.relative_to(sources)
            skfl.write_vetted_hash(repo, rel, skfl.file_hash(src_file))
    return repo


# ── find_repo ──────────────────────────────────────────────────────────


class TestFindRepo:
    def test_finds_repo_in_current_dir(self, repo):
        assert skfl.find_repo(repo) == repo

    def test_finds_repo_in_parent(self, repo):
        child = repo / "some" / "nested" / "dir"
        child.mkdir(parents=True)
        assert skfl.find_repo(child) == repo

    def test_raises_when_no_repo(self, tmp_dir):
        with pytest.raises(Exception, match="Not inside an skfl repository"):
            skfl.find_repo(tmp_dir)

    def test_skfl_repo_env_var_used_as_fallback(self, repo, tmp_dir):
        # cwd is tmp_dir (not inside any repo), but $SKFL_REPO points at repo
        with mock_patch.dict(os.environ, {"SKFL_REPO": str(repo)}):
            assert skfl.find_repo(tmp_dir) == repo

    def test_skfl_repo_env_var_ignored_when_local_repo_found(self, repo, tmp_path):
        other_repo = tmp_path / "other"
        other_repo.mkdir()
        runner = CliRunner()
        runner.invoke(skfl.cli, ["init", str(other_repo)])
        # $SKFL_REPO points elsewhere, but cwd is inside repo — use repo
        with mock_patch.dict(os.environ, {"SKFL_REPO": str(other_repo)}):
            assert skfl.find_repo(repo) == repo

    def test_skfl_repo_env_var_invalid_path_still_raises(self, tmp_dir):
        with mock_patch.dict(os.environ, {"SKFL_REPO": "/nonexistent/path"}):
            with pytest.raises(Exception, match="Not inside an skfl repository"):
                skfl.find_repo(tmp_dir)

    def test_completion_works_via_skfl_repo(self, repo_with_source, tmp_dir):
        # Completions from a directory outside the repo work when $SKFL_REPO is set
        with mock_patch.dict(os.environ, {"SKFL_REPO": str(repo_with_source)}):
            results = skfl._complete_source_files(None, None, "")
        values = {r.value for r in results}
        assert "custom/test-src/hello.md" in values

    def test_default_home_repo_used_when_no_repo_found(self, tmp_path, monkeypatch):
        # When cwd is outside any repo and $SKFL_REPO is unset, ~/.skfl is tried
        monkeypatch.delenv("SKFL_REPO", raising=False)
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        skfl_repo = fake_home / ".skfl"
        CliRunner().invoke(skfl.cli, ["init", str(skfl_repo)])
        outside = tmp_path / "outside"
        outside.mkdir()
        monkeypatch.setattr(skfl.Path, "home", staticmethod(lambda: fake_home))
        assert skfl.find_repo(outside) == skfl_repo

    def test_default_home_repo_ignored_when_no_skfl_toml(self, tmp_dir, monkeypatch, tmp_path):
        # ~/.skfl exists but has no skfl.toml → still raises
        monkeypatch.delenv("SKFL_REPO", raising=False)
        fake_home = tmp_path / "home"
        (fake_home / ".skfl").mkdir(parents=True)  # exists but no skfl.toml
        monkeypatch.setattr(skfl.Path, "home", staticmethod(lambda: fake_home))
        with pytest.raises(Exception, match="Not inside an skfl repository"):
            skfl.find_repo(tmp_dir)

    def test_local_repo_takes_priority_over_default_home_repo(self, repo, tmp_path, monkeypatch):
        # When cwd is inside a repo, the local repo wins over ~/.skfl
        monkeypatch.delenv("SKFL_REPO", raising=False)
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        # Put a valid skfl repo at fake_home/.skfl too
        other = fake_home / ".skfl"
        CliRunner().invoke(skfl.cli, ["init", str(other)])
        monkeypatch.setattr(skfl.Path, "home", staticmethod(lambda: fake_home))
        assert skfl.find_repo(repo) == repo

    def test_completion_works_via_default_home_repo(self, tmp_path, monkeypatch):
        # Completions work when the repo lives at ~/.skfl and $SKFL_REPO is unset
        monkeypatch.delenv("SKFL_REPO", raising=False)
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        skfl_repo = fake_home / ".skfl"
        CliRunner().invoke(skfl.cli, ["init", str(skfl_repo)])
        # Manually place a source file (avoids cwd dependency on the CLI)
        src_file = skfl_repo / skfl.SOURCES_DIR / "custom" / "test-src" / "hello.md"
        src_file.parent.mkdir(parents=True, exist_ok=True)
        src_file.write_text("# Hello\n")
        monkeypatch.setattr(skfl.Path, "home", staticmethod(lambda: fake_home))
        results = skfl._complete_source_files(None, None, "")
        values = {r.value for r in results}
        assert "custom/test-src/hello.md" in values


# ── init ───────────────────────────────────────────────────────────────


class TestInit:
    def test_creates_directory_structure(self, tmp_dir):
        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["init", str(tmp_dir)])
        assert result.exit_code == 0
        assert (tmp_dir / skfl.SKFL_TOML).exists()
        for d in skfl.REPO_DIRS:
            assert (tmp_dir / d).is_dir()

    def test_creates_gitignore(self, tmp_dir):
        runner = CliRunner()
        runner.invoke(skfl.cli, ["init", str(tmp_dir)])
        assert (tmp_dir / ".gitignore").exists()

    def test_creates_gitkeep_files(self, tmp_dir):
        runner = CliRunner()
        runner.invoke(skfl.cli, ["init", str(tmp_dir)])
        for d in skfl.REPO_DIRS:
            assert (tmp_dir / d / ".gitkeep").exists()

    def test_fails_if_already_initialized(self, repo):
        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["init", str(repo)])
        assert result.exit_code != 0
        assert "already exists" in result.output

    def test_creates_valid_toml(self, tmp_dir):
        runner = CliRunner()
        runner.invoke(skfl.cli, ["init", str(tmp_dir)])
        config = skfl.load_config(tmp_dir)
        assert config["repository"]["version"] == 1
        assert config["sources"] == {}

    def test_init_creates_parent_dirs(self, tmp_dir):
        target = tmp_dir / "a" / "b" / "c"
        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["init", str(target)])
        assert result.exit_code == 0
        assert (target / skfl.SKFL_TOML).exists()

    def test_creates_packages_directory(self, tmp_dir):
        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["init", str(tmp_dir)])
        assert result.exit_code == 0
        assert (tmp_dir / skfl.PACKAGES_DIR).is_dir()

    def test_creates_gitkeep_in_packages(self, tmp_dir):
        runner = CliRunner()
        runner.invoke(skfl.cli, ["init", str(tmp_dir)])
        assert (tmp_dir / skfl.PACKAGES_DIR / ".gitkeep").is_file()


# ── config ─────────────────────────────────────────────────────────────


class TestConfig:
    def test_load_and_save_roundtrip(self, repo):
        config = skfl.load_config(repo)
        config["test_key"] = "test_value"
        skfl.save_config(repo, config)
        reloaded = skfl.load_config(repo)
        assert reloaded["test_key"] == "test_value"


# ── file_hash ──────────────────────────────────────────────────────────


class TestFileHash:
    def test_same_content_same_hash(self, tmp_dir):
        f1 = tmp_dir / "a.txt"
        f2 = tmp_dir / "b.txt"
        f1.write_text("same content")
        f2.write_text("same content")
        assert skfl.file_hash(f1) == skfl.file_hash(f2)

    def test_different_content_different_hash(self, tmp_dir):
        f1 = tmp_dir / "a.txt"
        f2 = tmp_dir / "b.txt"
        f1.write_text("content a")
        f2.write_text("content b")
        assert skfl.file_hash(f1) != skfl.file_hash(f2)

    def test_hash_is_sha256_hex(self, tmp_dir):
        f = tmp_dir / "test.txt"
        f.write_text("hello")
        h = skfl.file_hash(f)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


# ── source custom ─────────────────────────────────────────────────────


class TestSourceCustom:
    def test_registers_custom_source(self, repo):
        src = repo / "my_files"
        src.mkdir()
        (src / "skill.md").write_text("# Skill\n")

        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["source", "custom", "my-src", str(src)])
        assert result.exit_code == 0
        assert "Registered" in result.output

        config = skfl.load_config(repo)
        assert "my-src" in config["sources"]
        assert config["sources"]["my-src"]["type"] == "custom"

    def test_copies_files_to_sources(self, repo):
        src = repo / "my_files"
        src.mkdir()
        (src / "a.txt").write_text("aaa")
        (src / "sub").mkdir()
        (src / "sub" / "b.txt").write_text("bbb")

        runner = CliRunner()
        runner.invoke(skfl.cli, ["source", "custom", "test", str(src)])

        dest = repo / skfl.SOURCES_DIR / "custom" / "test"
        assert (dest / "a.txt").read_text() == "aaa"
        assert (dest / "sub" / "b.txt").read_text() == "bbb"

    def test_fails_on_duplicate_name(self, repo):
        src = repo / "my_files"
        src.mkdir()
        (src / "a.txt").write_text("aaa")

        runner = CliRunner()
        runner.invoke(skfl.cli, ["source", "custom", "dup", str(src)])
        result = runner.invoke(skfl.cli, ["source", "custom", "dup", str(src)])
        assert result.exit_code != 0
        assert "already exists" in result.output


# ── source list ────────────────────────────────────────────────────────


class TestSourceList:
    def test_no_sources(self, repo):
        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["source", "list"])
        assert "No sources" in result.output

    def test_lists_sources(self, repo_with_source):
        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["source", "list"])
        assert result.exit_code == 0
        assert "test-src" in result.output
        assert "custom" in result.output


# ── all_source_files ───────────────────────────────────────────────────


class TestAllSourceFiles:
    def test_lists_all_files(self, repo_with_source):
        files = skfl.all_source_files(repo_with_source)
        names = [str(f) for f in files]
        assert "custom/test-src/hello.md" in names
        assert "custom/test-src/script.py" in names
        assert "custom/test-src/sub/nested.txt" in names

    def test_excludes_gitkeep(self, repo_with_source):
        files = skfl.all_source_files(repo_with_source)
        names = [f.name for f in files]
        assert ".gitkeep" not in names

    def test_empty_sources(self, repo):
        files = skfl.all_source_files(repo)
        assert files == []


# ── vet_status_for_file ───────────────────────────────────────────────


class TestVetStatus:
    def test_unvetted(self, repo_with_source):
        rel = Path("custom/test-src/hello.md")
        assert skfl.vet_status_for_file(repo_with_source, rel) == "unvetted"

    def test_vetted(self, repo_with_vetted):
        rel = Path("custom/test-src/hello.md")
        assert skfl.vet_status_for_file(repo_with_vetted, rel) == "vetted"

    def test_modified(self, repo_with_vetted):
        rel = Path("custom/test-src/hello.md")
        source = repo_with_vetted / skfl.SOURCES_DIR / rel
        source.write_text("# Hello Updated\n")
        assert skfl.vet_status_for_file(repo_with_vetted, rel) == "modified"

    def test_missing_source(self, repo):
        rel = Path("nonexistent/file.txt")
        assert skfl.vet_status_for_file(repo, rel) == "missing"


# ── vet status command ─────────────────────────────────────────────────


class TestVetStatusCommand:
    def test_shows_all_files(self, repo_with_source):
        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["vet-status"])
        assert result.exit_code == 0
        assert "unvetted" in result.output
        assert "hello.md" in result.output

    def test_shows_vetted_status(self, repo_with_vetted):
        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["vet-status"])
        assert result.exit_code == 0
        assert "vetted" in result.output

    def test_shows_modified_status(self, repo_with_vetted):
        rel = Path("custom/test-src/hello.md")
        source = repo_with_vetted / skfl.SOURCES_DIR / rel
        source.write_text("# Modified\n")

        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["vet-status"])
        assert result.exit_code == 0
        assert "modified" in result.output

    def test_no_source_files(self, repo):
        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["vet-status"])
        assert "No source files" in result.output


# ── vet command ────────────────────────────────────────────────────────


class TestVetCommand:
    def test_vet_already_vetted(self, repo_with_vetted):
        runner = CliRunner()
        result = runner.invoke(
            skfl.cli, ["vet", "custom/test-src/hello.md"]
        )
        assert result.exit_code == 0
        assert "already vetted" in result.output

    def test_vet_unvetted_approve(self, repo_with_source):
        runner = CliRunner()
        # Mock subprocess.run to skip pager, and answer 'y' to confirmation
        with mock_patch("subprocess.run"):
            result = runner.invoke(
                skfl.cli, ["vet", "custom/test-src/hello.md"], input="y\n"
            )
        assert result.exit_code == 0
        assert "vetted" in result.output

        # Verify the vetted hash was stored
        rel = Path("custom/test-src/hello.md")
        assert skfl.read_vetted_hash(repo_with_source, rel) is not None

    def test_vet_unvetted_reject(self, repo_with_source):
        runner = CliRunner()
        with mock_patch("subprocess.run"):
            result = runner.invoke(
                skfl.cli, ["vet", "custom/test-src/hello.md"], input="n\n"
            )
        assert result.exit_code == 0
        assert "Skipping" in result.output

        # Verify no hash was stored
        rel = Path("custom/test-src/hello.md")
        assert skfl.read_vetted_hash(repo_with_source, rel) is None

    def test_vet_modified_approve(self, repo_with_vetted):
        rel = Path("custom/test-src/hello.md")
        source = repo_with_vetted / skfl.SOURCES_DIR / rel
        source.write_text("# Hello Updated\n")

        runner = CliRunner()
        with mock_patch("subprocess.run"):
            result = runner.invoke(
                skfl.cli, ["vet", "custom/test-src/hello.md"], input="y\n"
            )
        assert result.exit_code == 0
        assert "vetted" in result.output

        # Verify vetted hash was updated to match new source
        rel = Path("custom/test-src/hello.md")
        assert skfl.read_vetted_hash(repo_with_vetted, rel) == skfl.file_hash(source)

    def test_vet_directory(self, repo_with_source):
        runner = CliRunner()
        # Approve all 3 files in the directory
        with mock_patch("subprocess.run"):
            result = runner.invoke(
                skfl.cli, ["vet", "custom/test-src"], input="y\ny\ny\n"
            )
        assert result.exit_code == 0
        assert result.output.count(": vetted.") == 3

        # Verify all files are now vetted
        for name in ["hello.md", "script.py", "sub/nested.txt"]:
            rel = Path(f"custom/test-src/{name}")
            assert skfl.vet_status_for_file(repo_with_source, rel) == "vetted"

    def test_vet_nonexistent_file(self, repo_with_source):
        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["vet", "custom/test-src/nope.md"])
        assert result.exit_code != 0


# ── patches_dir_for ───────────────────────────────────────────────────


class TestPatchesDirFor:
    def test_returns_d_directory(self, repo):
        rel = Path("custom/test-src/hello.md")
        d = skfl.patches_dir_for(repo, rel)
        assert str(d).endswith("hello.md.d")
        assert skfl.PATCHES_DIR in str(d)


# ── list_patches_for ──────────────────────────────────────────────────


class TestListPatchesFor:
    def test_no_patches(self, repo):
        rel = Path("custom/test-src/hello.md")
        assert skfl.list_patches_for(repo, rel) == []

    def test_lists_patches_sorted(self, repo):
        rel = Path("custom/test-src/hello.md")
        d = skfl.patches_dir_for(repo, rel)
        d.mkdir(parents=True)
        (d / "002-second.patch").write_text("patch 2")
        (d / "001-first.patch").write_text("patch 1")
        (d / "not-a-patch.txt").write_text("ignore me")

        patches = skfl.list_patches_for(repo, rel)
        assert len(patches) == 2
        assert patches[0].name == "001-first.patch"
        assert patches[1].name == "002-second.patch"


# ── apply_patches ─────────────────────────────────────────────────────


class TestApplyPatches:
    def test_apply_single_patch(self, tmp_path):
        original = b"line1\nline2\nline3\n"
        modified = b"line1\nline2 modified\nline3\n"

        # Generate a valid patch
        orig_file = tmp_path / "orig"
        new_file = tmp_path / "new"
        orig_file.write_bytes(original)
        new_file.write_bytes(modified)

        proc = subprocess.run(
            ["diff", "-u", str(orig_file), str(new_file)],
            capture_output=True,
        )
        patch_file = tmp_path / "test.patch"
        patch_file.write_bytes(proc.stdout)

        result = skfl.apply_patches(original, [patch_file])
        assert result == modified

    def test_apply_multiple_patches(self, tmp_path):
        v0 = b"aaa\nbbb\nccc\n"
        v1 = b"aaa\nBBB\nccc\n"
        v2 = b"aaa\nBBB\nCCC\n"

        # Patch 1: bbb -> BBB
        f0 = tmp_path / "v0"
        f1 = tmp_path / "v1"
        f0.write_bytes(v0)
        f1.write_bytes(v1)
        p1_proc = subprocess.run(
            ["diff", "-u", str(f0), str(f1)], capture_output=True
        )
        patch1 = tmp_path / "001.patch"
        patch1.write_bytes(p1_proc.stdout)

        # Patch 2: ccc -> CCC (applied on top of v1)
        f1b = tmp_path / "v1b"
        f2 = tmp_path / "v2"
        f1b.write_bytes(v1)
        f2.write_bytes(v2)
        p2_proc = subprocess.run(
            ["diff", "-u", str(f1b), str(f2)], capture_output=True
        )
        patch2 = tmp_path / "002.patch"
        patch2.write_bytes(p2_proc.stdout)

        result = skfl.apply_patches(v0, [patch1, patch2])
        assert result == v2

    def test_bad_patch_raises(self, tmp_path):
        patch_file = tmp_path / "bad.patch"
        patch_file.write_text("this is not a valid patch\n")

        with pytest.raises(Exception, match="failed to apply"):
            skfl.apply_patches(b"original content\n", [patch_file])


# ── patch create ───────────────────────────────────────────────────────


class TestPatchCreate:
    def test_requires_vetted_file(self, repo_with_source):
        runner = CliRunner()
        result = runner.invoke(
            skfl.cli, ["patch", "create", "custom/test-src/hello.md"]
        )
        assert result.exit_code != 0
        assert "not been vetted" in result.output

    def test_no_changes_no_patch(self, repo_with_vetted):
        runner = CliRunner()
        # Mock editor to not change the file
        with mock_patch.dict(os.environ, {"EDITOR": "true"}):
            result = runner.invoke(
                skfl.cli, ["patch", "create", "custom/test-src/hello.md"]
            )
        assert result.exit_code == 0
        assert "No changes" in result.output

    def test_create_patch_with_editor(self, repo_with_vetted, tmp_path):
        runner = CliRunner()
        # Create a shell script that acts as an editor
        editor_script = tmp_path / "editor.sh"
        editor_script.write_text("#!/bin/sh\nsed -i '' 's/World/Universe/' \"$1\"\n")
        editor_script.chmod(0o755)

        with mock_patch.dict(os.environ, {"EDITOR": str(editor_script)}):
            result = runner.invoke(
                skfl.cli,
                ["patch", "create", "custom/test-src/hello.md", "-n", "universe"],
            )
        assert result.exit_code == 0, result.output
        assert "Created patch" in result.output

        patches = skfl.list_patches_for(
            repo_with_vetted, Path("custom/test-src/hello.md")
        )
        assert len(patches) == 1
        assert "universe" in patches[0].name


# ── patch list ─────────────────────────────────────────────────────────


class TestPatchList:
    def test_no_patches(self, repo_with_vetted):
        runner = CliRunner()
        result = runner.invoke(
            skfl.cli, ["patch", "list", "custom/test-src/hello.md"]
        )
        assert "No patches" in result.output

    def test_lists_patches(self, repo_with_vetted):
        rel = Path("custom/test-src/hello.md")
        d = skfl.patches_dir_for(repo_with_vetted, rel)
        d.mkdir(parents=True)
        (d / "001-test.patch").write_text("patch content")

        runner = CliRunner()
        result = runner.invoke(
            skfl.cli, ["patch", "list", "custom/test-src/hello.md"]
        )
        assert "001-test.patch" in result.output

    def test_list_all_patches(self, repo_with_vetted):
        for fname in ["hello.md", "script.py"]:
            rel = Path(f"custom/test-src/{fname}")
            d = skfl.patches_dir_for(repo_with_vetted, rel)
            d.mkdir(parents=True)
            (d / "001-test.patch").write_text("patch")

        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["patch", "list"])
        assert result.output.count(".patch") == 2


# ── patch remove ───────────────────────────────────────────────────────


class TestPatchRemove:
    def test_removes_patch(self, repo_with_vetted):
        rel = Path("custom/test-src/hello.md")
        d = skfl.patches_dir_for(repo_with_vetted, rel)
        d.mkdir(parents=True)
        patch_file = d / "001-test.patch"
        patch_file.write_text("patch content")

        runner = CliRunner()
        result = runner.invoke(
            skfl.cli,
            ["patch", "remove", str(patch_file.relative_to(repo_with_vetted))],
        )
        assert result.exit_code == 0
        assert "Removed" in result.output
        assert not patch_file.exists()

    def test_cleans_empty_dir(self, repo_with_vetted):
        rel = Path("custom/test-src/hello.md")
        d = skfl.patches_dir_for(repo_with_vetted, rel)
        d.mkdir(parents=True)
        patch_file = d / "001-test.patch"
        patch_file.write_text("patch content")

        runner = CliRunner()
        runner.invoke(
            skfl.cli,
            ["patch", "remove", str(patch_file.relative_to(repo_with_vetted))],
        )
        assert not d.exists()

    def test_remove_nonexistent_fails(self, repo_with_vetted):
        runner = CliRunner()
        result = runner.invoke(
            skfl.cli, ["patch", "remove", "nonexistent.patch"]
        )
        assert result.exit_code != 0
        assert "not found" in result.output


# ── stage command ──────────────────────────────────────────────────────


class TestStageCommand:
    def test_stage_vetted_file(self, repo_with_vetted):
        runner = CliRunner()
        result = runner.invoke(
            skfl.cli, ["stage", "custom/test-src/hello.md"]
        )
        assert result.exit_code == 0
        assert "staged" in result.output

        staged = repo_with_vetted / skfl.STAGED_DIR / "custom/test-src/hello.md"
        assert staged.exists()
        assert staged.read_text() == "# Hello\n\nWorld\n"

    def test_stage_unvetted_prompts_and_stages_on_approve(self, repo_with_source):
        runner = CliRunner()
        with mock_patch("subprocess.run"):
            result = runner.invoke(
                skfl.cli, ["stage", "custom/test-src/hello.md"], input="y\n"
            )
        assert result.exit_code == 0
        assert "unvetted" in result.output
        assert "staged:" in result.output

        staged = repo_with_source / skfl.STAGED_DIR / "custom/test-src/hello.md"
        assert staged.exists()

    def test_stage_unvetted_skips_on_reject(self, repo_with_source):
        runner = CliRunner()
        with mock_patch("subprocess.run"):
            result = runner.invoke(
                skfl.cli, ["stage", "custom/test-src/hello.md"], input="n\n"
            )
        assert result.exit_code == 0
        assert "Skipping" in result.output

        staged = repo_with_source / skfl.STAGED_DIR / "custom/test-src/hello.md"
        assert not staged.exists()

    def test_stage_modified_prompts_and_stages_on_approve(self, repo_with_vetted):
        source = repo_with_vetted / skfl.SOURCES_DIR / "custom/test-src/hello.md"
        source.write_text("# Changed\n")

        runner = CliRunner()
        with mock_patch("subprocess.run"):
            result = runner.invoke(
                skfl.cli, ["stage", "custom/test-src/hello.md"], input="y\n"
            )
        assert result.exit_code == 0
        assert "changed since last vet" in result.output
        assert "staged:" in result.output

        staged = repo_with_vetted / skfl.STAGED_DIR / "custom/test-src/hello.md"
        assert staged.read_text() == "# Changed\n"

    def test_stage_modified_skips_on_reject(self, repo_with_vetted):
        source = repo_with_vetted / skfl.SOURCES_DIR / "custom/test-src/hello.md"
        source.write_text("# Changed\n")

        runner = CliRunner()
        with mock_patch("subprocess.run"):
            result = runner.invoke(
                skfl.cli, ["stage", "custom/test-src/hello.md"], input="n\n"
            )
        assert result.exit_code == 0
        assert "Skipping" in result.output

        staged = repo_with_vetted / skfl.STAGED_DIR / "custom/test-src/hello.md"
        assert not staged.exists()

    def test_stage_with_patches(self, repo_with_vetted, tmp_path):
        repo = repo_with_vetted
        rel = Path("custom/test-src/hello.md")

        # Create a valid patch
        original = (repo / skfl.SOURCES_DIR / rel).read_bytes()
        modified = original.replace(b"World", b"Universe")
        orig_f = tmp_path / "orig"
        new_f = tmp_path / "new"
        orig_f.write_bytes(original)
        new_f.write_bytes(modified)
        proc = subprocess.run(
            ["diff", "-u", str(orig_f), str(new_f)], capture_output=True
        )

        d = skfl.patches_dir_for(repo, rel)
        d.mkdir(parents=True)
        (d / "001-test.patch").write_bytes(proc.stdout)

        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["stage", "custom/test-src/hello.md"])
        assert result.exit_code == 0
        assert "1 patch applied" in result.output

        staged = repo / skfl.STAGED_DIR / "custom/test-src/hello.md"
        assert b"Universe" in staged.read_bytes()

    def test_stage_multiple_files(self, repo_with_vetted):
        runner = CliRunner()
        result = runner.invoke(
            skfl.cli,
            ["stage", "custom/test-src/hello.md", "custom/test-src/script.py"],
        )
        assert result.exit_code == 0
        assert result.output.count("staged:") == 2

    def test_stage_directory(self, repo_with_vetted):
        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["stage", "custom/test-src"])
        assert result.exit_code == 0
        assert result.output.count("staged:") == 3

        repo = repo_with_vetted
        assert (repo / skfl.STAGED_DIR / "custom/test-src/hello.md").exists()
        assert (repo / skfl.STAGED_DIR / "custom/test-src/script.py").exists()
        assert (repo / skfl.STAGED_DIR / "custom/test-src/sub/nested.txt").exists()

    def test_stage_subdirectory(self, repo_with_vetted):
        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["stage", "custom/test-src/sub"])
        assert result.exit_code == 0
        assert result.output.count("staged:") == 1
        assert (repo_with_vetted / skfl.STAGED_DIR / "custom/test-src/sub/nested.txt").exists()

    def test_stage_directory_with_profile(self, repo_with_vetted):
        runner = CliRunner()
        result = runner.invoke(
            skfl.cli, ["stage", "--as", "myprofile", "custom/test-src/sub"]
        )
        assert result.exit_code == 0
        assert "profile: myprofile" in result.output
        assert (
            repo_with_vetted
            / skfl.STAGED_DIR
            / "myprofile/custom/test-src/sub/nested.txt"
        ).exists()


# ── stage list ─────────────────────────────────────────────────────────


class TestStageList:
    def test_no_staged_files(self, repo):
        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["stage", "list"])
        assert "No staged files" in result.output

    def test_lists_staged_files(self, repo_with_vetted):
        runner = CliRunner()
        runner.invoke(skfl.cli, ["stage", "custom/test-src/hello.md"])
        result = runner.invoke(skfl.cli, ["stage", "list"])
        assert result.exit_code == 0
        assert "hello.md" in result.output


# ── doctor ─────────────────────────────────────────────────────────────


class TestDoctor:
    def test_runs(self, repo):
        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["doctor"])
        # Should at least find python3
        assert "python3" in result.output

    def test_shows_required_tools(self, repo):
        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["doctor"])
        assert "git" in result.output
        assert "diff" in result.output
        assert "patch" in result.output


# ── source pull URL parsing ────────────────────────────────────────────


class TestSourcePullParsing:
    def test_rejects_non_github_url(self, repo):
        runner = CliRunner()
        result = runner.invoke(
            skfl.cli, ["source", "pull", "https://gitlab.com/user/repo"]
        )
        assert result.exit_code != 0
        assert "Could not parse" in result.output

    def test_requires_url_or_options(self, repo):
        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["source", "pull"])
        assert result.exit_code != 0
        assert "Specify" in result.output

    def test_owner_repo_shorthand_accepted(self, repo):
        runner = CliRunner()
        with mock_patch("subprocess.run"):
            result = runner.invoke(skfl.cli, ["source", "pull", "BenjaminG/ai-skills"])
        assert result.exit_code == 0

    def test_github_shorthand_rejects_missing_slash(self, repo):
        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["source", "pull", "github", "noslash"])
        assert result.exit_code != 0
        assert "OWNER/REPO" in result.output

    def test_github_shorthand_rejects_extra_arg_after_url(self, repo):
        runner = CliRunner()
        result = runner.invoke(
            skfl.cli,
            ["source", "pull", "https://github.com/obra/superpowers", "extra"],
        )
        assert result.exit_code != 0
        assert "Unexpected argument" in result.output


# ── resolve_to_source_rel ─────────────────────────────────────────────


# ── expand_paths ───────────────────────────────────────────────────────


class TestExpandPaths:
    def test_expands_directory_to_files(self, repo_with_source):
        result = skfl.expand_paths(repo_with_source, ["custom/test-src"])
        assert len(result) == 3
        assert "custom/test-src/hello.md" in result
        assert "custom/test-src/script.py" in result
        assert "custom/test-src/sub/nested.txt" in result

    def test_expands_subdirectory(self, repo_with_source):
        result = skfl.expand_paths(repo_with_source, ["custom/test-src/sub"])
        assert result == ["custom/test-src/sub/nested.txt"]

    def test_leaves_files_unchanged(self, repo_with_source):
        result = skfl.expand_paths(
            repo_with_source, ["custom/test-src/hello.md"]
        )
        assert result == ["custom/test-src/hello.md"]

    def test_mixed_files_and_dirs(self, repo_with_source):
        result = skfl.expand_paths(
            repo_with_source,
            ["custom/test-src/hello.md", "custom/test-src/sub"],
        )
        assert "custom/test-src/hello.md" in result
        assert "custom/test-src/sub/nested.txt" in result
        assert len(result) == 2

    def test_excludes_gitkeep(self, repo_with_source):
        # .gitkeep exists in the sources dir
        result = skfl.expand_paths(repo_with_source, ["."])
        names = [Path(f).name for f in result]
        assert ".gitkeep" not in names

    def test_passes_through_invalid_paths(self, repo_with_source):
        # Invalid paths are passed through for downstream error handling
        result = skfl.expand_paths(repo_with_source, ["/tmp/nonexistent"])
        assert result == ["/tmp/nonexistent"]

    def test_absolute_directory_path(self, repo_with_source):
        abs_dir = str(
            repo_with_source / skfl.SOURCES_DIR / "custom" / "test-src" / "sub"
        )
        result = skfl.expand_paths(repo_with_source, [abs_dir])
        assert result == ["custom/test-src/sub/nested.txt"]


# ── resolve_to_source_rel ─────────────────────────────────────────────


class TestResolveToSourceRel:
    def test_relative_path(self, repo_with_source):
        rel = skfl.resolve_to_source_rel(
            repo_with_source, "custom/test-src/hello.md"
        )
        assert rel == Path("custom/test-src/hello.md")

    def test_absolute_path(self, repo_with_source):
        abs_path = (
            repo_with_source / skfl.SOURCES_DIR / "custom/test-src/hello.md"
        )
        rel = skfl.resolve_to_source_rel(repo_with_source, abs_path)
        assert rel == Path("custom/test-src/hello.md")

    def test_outside_sources_raises(self, repo_with_source):
        with pytest.raises(ValueError):
            skfl.resolve_to_source_rel(repo_with_source, "/tmp/outside.txt")


# ── integration: full workflow ─────────────────────────────────────────


class TestFullWorkflow:
    def test_source_vet_stage(self, repo_with_vetted):
        """Test the complete source → vet → stage workflow."""
        repo = repo_with_vetted
        runner = CliRunner()

        # Verify source files exist and are vetted
        result = runner.invoke(skfl.cli, ["vet-status"])
        assert "vetted" in result.output

        # Stage a file
        result = runner.invoke(
            skfl.cli, ["stage", "custom/test-src/hello.md"]
        )
        assert result.exit_code == 0

        # Verify staged file matches source
        staged = repo / skfl.STAGED_DIR / "custom/test-src/hello.md"
        source = repo / skfl.SOURCES_DIR / "custom/test-src/hello.md"
        assert staged.read_text() == source.read_text()

    def test_source_vet_patch_stage(self, repo_with_vetted, tmp_path):
        """Test source → vet → patch → stage workflow."""
        repo = repo_with_vetted
        runner = CliRunner()
        rel = Path("custom/test-src/script.py")

        # Create patch
        original = (repo / skfl.SOURCES_DIR / rel).read_bytes()
        modified = b"print('hello world')\n"
        orig_f = tmp_path / "orig"
        new_f = tmp_path / "new"
        orig_f.write_bytes(original)
        new_f.write_bytes(modified)
        proc = subprocess.run(
            ["diff", "-u", str(orig_f), str(new_f)], capture_output=True
        )
        d = skfl.patches_dir_for(repo, rel)
        d.mkdir(parents=True)
        (d / "001-improve.patch").write_bytes(proc.stdout)

        # Stage
        result = runner.invoke(skfl.cli, ["stage", "custom/test-src/script.py"])
        assert result.exit_code == 0
        assert "1 patch applied" in result.output

        # Verify staged content has patch applied
        staged = repo / skfl.STAGED_DIR / rel
        assert staged.read_bytes() == modified

    def test_source_update_re_vet(self, repo_with_vetted):
        """Test that modifying source triggers inline re-vetting during stage."""
        repo = repo_with_vetted
        runner = CliRunner()
        rel = Path("custom/test-src/hello.md")

        # Modify source (simulating a source pull update)
        source = repo / skfl.SOURCES_DIR / rel
        source.write_text("# Hello Updated\n\nNew content\n")

        # Vet status should show modified
        result = runner.invoke(skfl.cli, ["vet-status"])
        assert "modified" in result.output

        # Staging should prompt for re-vetting, then stage on approval
        with mock_patch("subprocess.run"):
            result = runner.invoke(
                skfl.cli, ["stage", "custom/test-src/hello.md"], input="y\n"
            )
        assert result.exit_code == 0
        assert "changed since last vet" in result.output
        assert "staged:" in result.output

        staged = repo / skfl.STAGED_DIR / rel
        assert staged.read_text() == "# Hello Updated\n\nNew content\n"


# ── profile-based staging ─────────────────────────────────────────────


def _make_patch(tmp_path, original: bytes, modified: bytes, name: str = "patch") -> bytes:
    """Helper: generate a unified diff patch from original to modified."""
    orig_f = tmp_path / f"{name}.orig"
    new_f = tmp_path / f"{name}.new"
    orig_f.write_bytes(original)
    new_f.write_bytes(modified)
    proc = subprocess.run(
        ["diff", "-u", str(orig_f), str(new_f)], capture_output=True
    )
    return proc.stdout


class TestProfilePatchesDirFor:
    def test_returns_profile_d_directory(self, repo):
        rel = Path("custom/test-src/hello.md")
        d = skfl.profile_patches_dir_for(repo, "claude", rel)
        assert "_profiles/claude" in str(d)
        assert str(d).endswith("hello.md.d")


class TestListPatchesWithProfile:
    def test_no_profile_returns_default_only(self, repo):
        rel = Path("custom/test-src/hello.md")
        d = skfl.patches_dir_for(repo, rel)
        d.mkdir(parents=True)
        (d / "001-default.patch").write_text("default patch")

        patches = skfl.list_patches_for(repo, rel)
        assert len(patches) == 1
        assert patches[0].name == "001-default.patch"

    def test_profile_includes_default_and_profile(self, repo):
        rel = Path("custom/test-src/hello.md")
        # Default patch
        d = skfl.patches_dir_for(repo, rel)
        d.mkdir(parents=True)
        (d / "001-default.patch").write_text("default")
        # Profile patch
        pd = skfl.profile_patches_dir_for(repo, "claude", rel)
        pd.mkdir(parents=True)
        (pd / "001-claude.patch").write_text("claude")

        patches = skfl.list_patches_for(repo, rel, profile="claude")
        assert len(patches) == 2
        names = [p.name for p in patches]
        assert "001-default.patch" in names
        assert "001-claude.patch" in names
        # Default patches come first
        assert patches[0].name == "001-default.patch"

    def test_profile_only_no_defaults(self, repo):
        rel = Path("custom/test-src/hello.md")
        pd = skfl.profile_patches_dir_for(repo, "kiro", rel)
        pd.mkdir(parents=True)
        (pd / "001-kiro.patch").write_text("kiro")

        patches = skfl.list_patches_for(repo, rel, profile="kiro")
        assert len(patches) == 1
        assert patches[0].name == "001-kiro.patch"

    def test_no_profile_ignores_profile_patches(self, repo):
        rel = Path("custom/test-src/hello.md")
        pd = skfl.profile_patches_dir_for(repo, "claude", rel)
        pd.mkdir(parents=True)
        (pd / "001-claude.patch").write_text("claude only")

        patches = skfl.list_patches_for(repo, rel)
        assert len(patches) == 0


class TestStageWithProfile:
    def test_stage_as_profile(self, repo_with_vetted):
        runner = CliRunner()
        result = runner.invoke(
            skfl.cli, ["stage", "--as", "claude", "custom/test-src/hello.md"]
        )
        assert result.exit_code == 0
        assert "profile: claude" in result.output

        staged = repo_with_vetted / skfl.STAGED_DIR / "claude/custom/test-src/hello.md"
        assert staged.exists()
        assert staged.read_text() == "# Hello\n\nWorld\n"

    def test_stage_two_profiles_coexist(self, repo_with_vetted):
        runner = CliRunner()
        runner.invoke(
            skfl.cli, ["stage", "--as", "alpha", "custom/test-src/hello.md"]
        )
        runner.invoke(
            skfl.cli, ["stage", "--as", "beta", "custom/test-src/hello.md"]
        )
        runner.invoke(
            skfl.cli, ["stage", "custom/test-src/hello.md"]
        )

        repo = repo_with_vetted
        assert (repo / skfl.STAGED_DIR / "alpha/custom/test-src/hello.md").exists()
        assert (repo / skfl.STAGED_DIR / "beta/custom/test-src/hello.md").exists()
        assert (repo / skfl.STAGED_DIR / "custom/test-src/hello.md").exists()

    def test_stage_profiles_apply_different_patches(self, repo_with_vetted, tmp_path):
        repo = repo_with_vetted
        rel = Path("custom/test-src/hello.md")
        original = (repo / skfl.SOURCES_DIR / rel).read_bytes()
        runner = CliRunner()

        # Default patch: World -> Earth
        default_patch = _make_patch(
            tmp_path, original, original.replace(b"World", b"Earth"), "default"
        )
        d = skfl.patches_dir_for(repo, rel)
        d.mkdir(parents=True)
        (d / "001-earth.patch").write_bytes(default_patch)

        # Profile 'claude' patch: Earth -> Claude-Earth (on top of default)
        after_default = original.replace(b"World", b"Earth")
        claude_patch = _make_patch(
            tmp_path, after_default, after_default.replace(b"Earth", b"Claude-Earth"), "claude"
        )
        pd_claude = skfl.profile_patches_dir_for(repo, "claude", rel)
        pd_claude.mkdir(parents=True)
        (pd_claude / "001-claude.patch").write_bytes(claude_patch)

        # Profile 'kiro' patch: Earth -> Kiro-Earth (on top of default)
        kiro_patch = _make_patch(
            tmp_path, after_default, after_default.replace(b"Earth", b"Kiro-Earth"), "kiro"
        )
        pd_kiro = skfl.profile_patches_dir_for(repo, "kiro", rel)
        pd_kiro.mkdir(parents=True)
        (pd_kiro / "001-kiro.patch").write_bytes(kiro_patch)

        # Stage all three
        result = runner.invoke(skfl.cli, ["stage", "custom/test-src/hello.md"])
        assert result.exit_code == 0
        result = runner.invoke(
            skfl.cli, ["stage", "--as", "claude", "custom/test-src/hello.md"]
        )
        assert result.exit_code == 0
        result = runner.invoke(
            skfl.cli, ["stage", "--as", "kiro", "custom/test-src/hello.md"]
        )
        assert result.exit_code == 0

        # Verify: default has Earth, claude has Claude-Earth, kiro has Kiro-Earth
        default_staged = (repo / skfl.STAGED_DIR / rel).read_bytes()
        claude_staged = (repo / skfl.STAGED_DIR / "claude" / rel).read_bytes()
        kiro_staged = (repo / skfl.STAGED_DIR / "kiro" / rel).read_bytes()

        assert b"Earth" in default_staged
        assert b"Claude-Earth" not in default_staged
        assert b"Claude-Earth" in claude_staged
        assert b"Kiro-Earth" in kiro_staged

        # All three are different
        assert default_staged != claude_staged
        assert default_staged != kiro_staged
        assert claude_staged != kiro_staged

    def test_stage_list_with_profile(self, repo_with_vetted):
        runner = CliRunner()
        runner.invoke(
            skfl.cli, ["stage", "--as", "myprofile", "custom/test-src/hello.md"]
        )
        result = runner.invoke(skfl.cli, ["stage", "list", "--as", "myprofile"])
        assert result.exit_code == 0
        assert "hello.md" in result.output

    def test_stage_profile_multiple_files_different_patches(
        self, repo_with_vetted, tmp_path
    ):
        """Test staging multiple files where each has different profile patches."""
        repo = repo_with_vetted
        runner = CliRunner()

        rel_md = Path("custom/test-src/hello.md")
        rel_py = Path("custom/test-src/script.py")
        original_md = (repo / skfl.SOURCES_DIR / rel_md).read_bytes()
        original_py = (repo / skfl.SOURCES_DIR / rel_py).read_bytes()

        # Profile patch for hello.md only
        md_patch = _make_patch(
            tmp_path, original_md, original_md.replace(b"World", b"Profiled"), "md"
        )
        pd_md = skfl.profile_patches_dir_for(repo, "test-profile", rel_md)
        pd_md.mkdir(parents=True)
        (pd_md / "001-profiled.patch").write_bytes(md_patch)

        # Profile patch for script.py only
        py_patch = _make_patch(
            tmp_path, original_py, b"print('profiled')\n", "py"
        )
        pd_py = skfl.profile_patches_dir_for(repo, "test-profile", rel_py)
        pd_py.mkdir(parents=True)
        (pd_py / "001-profiled.patch").write_bytes(py_patch)

        # Stage both files under the profile
        result = runner.invoke(
            skfl.cli,
            ["stage", "--as", "test-profile",
             "custom/test-src/hello.md", "custom/test-src/script.py"],
        )
        assert result.exit_code == 0
        assert result.output.count("staged:") == 2

        # Verify each file got its own profile patch
        staged_md = (repo / skfl.STAGED_DIR / "test-profile" / rel_md).read_bytes()
        staged_py = (repo / skfl.STAGED_DIR / "test-profile" / rel_py).read_bytes()
        assert b"Profiled" in staged_md
        assert b"profiled" in staged_py


# ── package init / package list ────────────────────────────────────────


class TestPackageNew:
    def test_package_init_creates_directory(self, repo):
        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["package", "init", "my-pkg"])
        assert result.exit_code == 0
        assert (repo / skfl.PACKAGES_DIR / "my-pkg").is_dir()

    def test_package_init_fails_on_duplicate(self, repo):
        runner = CliRunner()
        runner.invoke(skfl.cli, ["package", "init", "my-pkg"])
        result = runner.invoke(skfl.cli, ["package", "init", "my-pkg"])
        assert result.exit_code != 0
        assert "already exists" in result.output


class TestPackageList:
    def test_package_list_empty(self, repo):
        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["package", "list"])
        assert result.exit_code == 0
        assert "No packages" in result.output

    def test_package_list_shows_packages(self, repo):
        runner = CliRunner()
        runner.invoke(skfl.cli, ["package", "init", "alpha"])
        runner.invoke(skfl.cli, ["package", "init", "beta"])
        result = runner.invoke(skfl.cli, ["package", "list"])
        assert result.exit_code == 0
        assert "alpha" in result.output
        assert "beta" in result.output


# ── package add ────────────────────────────────────────────────────────


class TestPackageAdd:
    def test_package_add_creates_file_symlink(self, repo_with_source):
        runner = CliRunner()
        runner.invoke(skfl.cli, ["package", "init", "my-pkg"])
        result = runner.invoke(
            skfl.cli,
            ["package", "add", "my-pkg", "custom/test-src/hello.md", "hello.md"],
        )
        assert result.exit_code == 0
        symlink = repo_with_source / skfl.PACKAGES_DIR / "my-pkg" / "hello.md"
        assert symlink.is_symlink()
        assert symlink.resolve() == (
            repo_with_source / "10_sources" / "custom" / "test-src" / "hello.md"
        ).resolve()

    def test_package_add_creates_directory_symlink(self, repo_with_source):
        runner = CliRunner()
        runner.invoke(skfl.cli, ["package", "init", "my-pkg"])
        result = runner.invoke(
            skfl.cli,
            ["package", "add", "my-pkg", "custom/test-src/sub", "subdir"],
        )
        assert result.exit_code == 0
        symlink = repo_with_source / skfl.PACKAGES_DIR / "my-pkg" / "subdir"
        assert symlink.is_symlink()
        assert symlink.resolve() == (
            repo_with_source / "10_sources" / "custom" / "test-src" / "sub"
        ).resolve()

    def test_package_add_creates_nested_dest(self, repo_with_source):
        runner = CliRunner()
        runner.invoke(skfl.cli, ["package", "init", "my-pkg"])
        result = runner.invoke(
            skfl.cli,
            ["package", "add", "my-pkg", "custom/test-src/hello.md", "deep/nested/hello.md"],
        )
        assert result.exit_code == 0
        symlink = repo_with_source / skfl.PACKAGES_DIR / "my-pkg" / "deep" / "nested" / "hello.md"
        assert symlink.is_symlink()

    def test_package_add_fails_if_package_missing(self, repo_with_source):
        runner = CliRunner()
        result = runner.invoke(
            skfl.cli,
            ["package", "add", "no-such-pkg", "custom/test-src/hello.md", "hello.md"],
        )
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_package_add_fails_if_source_missing(self, repo_with_source):
        runner = CliRunner()
        runner.invoke(skfl.cli, ["package", "init", "my-pkg"])
        result = runner.invoke(
            skfl.cli,
            ["package", "add", "my-pkg", "custom/test-src/nonexistent.md", "x.md"],
        )
        assert result.exit_code != 0

    def test_package_add_fails_if_dest_exists(self, repo_with_source):
        runner = CliRunner()
        runner.invoke(skfl.cli, ["package", "init", "my-pkg"])
        runner.invoke(
            skfl.cli,
            ["package", "add", "my-pkg", "custom/test-src/hello.md", "hello.md"],
        )
        result = runner.invoke(
            skfl.cli,
            ["package", "add", "my-pkg", "custom/test-src/script.py", "hello.md"],
        )
        assert result.exit_code != 0
        assert "already exists" in result.output


# ── resolve_package_files ─────────────────────────────────────────────


class TestResolvePackageFiles:
    def test_resolve_package_files_file_symlink(self, repo_with_source):
        runner = CliRunner()
        runner.invoke(skfl.cli, ["package", "init", "my-pkg"])
        runner.invoke(
            skfl.cli,
            ["package", "add", "my-pkg", "custom/test-src/hello.md", "hello.md"],
        )
        pairs = skfl.resolve_package_files(repo_with_source, "my-pkg")
        assert len(pairs) == 1
        source_abs, dest_rel = pairs[0]
        assert source_abs.name == "hello.md"
        assert dest_rel == Path("hello.md")

    def test_resolve_package_files_directory_symlink(self, repo_with_source):
        runner = CliRunner()
        runner.invoke(skfl.cli, ["package", "init", "my-pkg"])
        runner.invoke(
            skfl.cli,
            ["package", "add", "my-pkg", "custom/test-src/sub", "subdir"],
        )
        pairs = skfl.resolve_package_files(repo_with_source, "my-pkg")
        dest_rels = [str(d) for _, d in pairs]
        assert "subdir/nested.txt" in dest_rels

    def test_resolve_package_files_missing_package(self, repo):
        with pytest.raises(Exception):
            skfl.resolve_package_files(repo, "no-such-pkg")


# ── package build ─────────────────────────────────────────────────────


def _vet(repo, rel_str):
    """Helper: write a vetted hash for a source-relative path."""
    rel = Path(rel_str)
    skfl.write_vetted_hash(repo, rel, skfl.file_hash(repo / "10_sources" / rel))


class TestPackageBuild:
    def test_package_build_stages_file(self, repo_with_source):
        runner = CliRunner()
        _vet(repo_with_source, "custom/test-src/hello.md")
        runner.invoke(skfl.cli, ["package", "init", "my-pkg"])
        runner.invoke(
            skfl.cli,
            ["package", "add", "my-pkg", "custom/test-src/hello.md", "hello.md"],
        )
        result = runner.invoke(skfl.cli, ["package", "build", "my-pkg"])
        assert result.exit_code == 0
        staged = repo_with_source / "40_staged" / "my-pkg" / "hello.md"
        assert staged.is_file()
        assert staged.read_text() == "# Hello\n\nWorld\n"

    def test_package_build_refuses_unvetted(self, repo_with_source):
        runner = CliRunner()
        runner.invoke(skfl.cli, ["package", "init", "my-pkg"])
        runner.invoke(
            skfl.cli,
            ["package", "add", "my-pkg", "custom/test-src/hello.md", "hello.md"],
        )
        result = runner.invoke(skfl.cli, ["package", "build", "my-pkg"])
        assert result.exit_code != 0
        assert "unvetted" in result.output.lower() or "not vetted" in result.output.lower()

    def test_package_build_refuses_modified(self, repo_with_source):
        runner = CliRunner()
        _vet(repo_with_source, "custom/test-src/hello.md")
        (repo_with_source / "10_sources" / "custom" / "test-src" / "hello.md").write_text(
            "changed\n"
        )
        runner.invoke(skfl.cli, ["package", "init", "my-pkg"])
        runner.invoke(
            skfl.cli,
            ["package", "add", "my-pkg", "custom/test-src/hello.md", "hello.md"],
        )
        result = runner.invoke(skfl.cli, ["package", "build", "my-pkg"])
        assert result.exit_code != 0
        assert "modified" in result.output.lower()

    def test_package_build_applies_patches(self, repo_with_source, tmp_path):
        runner = CliRunner()
        _vet(repo_with_source, "custom/test-src/hello.md")
        src = repo_with_source / "10_sources" / "custom" / "test-src" / "hello.md"
        original = src.read_bytes()
        patched = original + b"\nPatched line\n"
        patch_dir = repo_with_source / "30_patches" / "custom" / "test-src" / "hello.md.d"
        patch_dir.mkdir(parents=True)
        orig_f = tmp_path / "orig"
        new_f = tmp_path / "new"
        orig_f.write_bytes(original)
        new_f.write_bytes(patched)
        proc = subprocess.run(
            ["diff", "-u", str(orig_f), str(new_f)], capture_output=True
        )
        (patch_dir / "001-append.patch").write_bytes(proc.stdout)

        runner.invoke(skfl.cli, ["package", "init", "my-pkg"])
        runner.invoke(
            skfl.cli,
            ["package", "add", "my-pkg", "custom/test-src/hello.md", "hello.md"],
        )
        result = runner.invoke(skfl.cli, ["package", "build", "my-pkg"])
        assert result.exit_code == 0
        staged = repo_with_source / "40_staged" / "my-pkg" / "hello.md"
        assert "Patched line" in staged.read_text()

    def test_package_build_expands_directory_symlink(self, repo_with_source):
        runner = CliRunner()
        _vet(repo_with_source, "custom/test-src/sub/nested.txt")
        runner.invoke(skfl.cli, ["package", "init", "my-pkg"])
        runner.invoke(
            skfl.cli,
            ["package", "add", "my-pkg", "custom/test-src/sub", "mydir"],
        )
        result = runner.invoke(skfl.cli, ["package", "build", "my-pkg"])
        assert result.exit_code == 0
        assert (
            repo_with_source / "40_staged" / "my-pkg" / "mydir" / "nested.txt"
        ).is_file()

    def test_package_build_with_profile(self, repo_with_source, tmp_path):
        runner = CliRunner()
        _vet(repo_with_source, "custom/test-src/hello.md")
        src = repo_with_source / "10_sources" / "custom" / "test-src" / "hello.md"
        original = src.read_bytes()
        patched = original + b"\nProfile line\n"
        patch_dir = (
            repo_with_source
            / "30_patches"
            / "_profiles"
            / "myprofile"
            / "custom"
            / "test-src"
            / "hello.md.d"
        )
        patch_dir.mkdir(parents=True)
        orig_f = tmp_path / "orig"
        new_f = tmp_path / "new"
        orig_f.write_bytes(original)
        new_f.write_bytes(patched)
        proc = subprocess.run(
            ["diff", "-u", str(orig_f), str(new_f)], capture_output=True
        )
        (patch_dir / "001-profile.patch").write_bytes(proc.stdout)

        runner.invoke(skfl.cli, ["package", "init", "my-pkg"])
        runner.invoke(
            skfl.cli,
            ["package", "add", "my-pkg", "custom/test-src/hello.md", "hello.md"],
        )
        result = runner.invoke(skfl.cli, ["package", "build", "my-pkg", "--as", "myprofile"])
        assert result.exit_code == 0
        staged = repo_with_source / "40_staged" / "my-pkg" / "hello.md"
        assert "Profile line" in staged.read_text()


# ── package install ────────────────────────────────────────────────────


class TestPackageInstall:
    def test_package_install_rsync(self, repo_with_source, tmp_path):
        runner = CliRunner()
        _vet(repo_with_source, "custom/test-src/hello.md")
        runner.invoke(skfl.cli, ["package", "init", "my-pkg"])
        runner.invoke(
            skfl.cli,
            ["package", "add", "my-pkg", "custom/test-src/hello.md", "hello.md"],
        )
        runner.invoke(skfl.cli, ["package", "build", "my-pkg"])
        target = tmp_path / "install-target"
        result = runner.invoke(
            skfl.cli, ["package", "install", "rsync", "my-pkg", str(target)]
        )
        assert result.exit_code == 0
        assert (target / "hello.md").is_file()
        assert (target / "hello.md").read_text() == "# Hello\n\nWorld\n"

    def test_package_install_rsync_builds_on_demand(self, repo_with_source, tmp_path):
        runner = CliRunner()
        _vet(repo_with_source, "custom/test-src/hello.md")
        runner.invoke(skfl.cli, ["package", "init", "my-pkg"])
        runner.invoke(
            skfl.cli,
            ["package", "add", "my-pkg", "custom/test-src/hello.md", "hello.md"],
        )
        # No explicit build — install should trigger it automatically
        target = tmp_path / "install-target"
        result = runner.invoke(
            skfl.cli, ["package", "install", "rsync", "my-pkg", str(target)]
        )
        assert result.exit_code == 0
        assert (target / "hello.md").is_file()

    def test_package_install_rsync_fails_on_unvetted(self, repo_with_source, tmp_path):
        runner = CliRunner()
        runner.invoke(skfl.cli, ["package", "init", "my-pkg"])
        runner.invoke(
            skfl.cli,
            ["package", "add", "my-pkg", "custom/test-src/hello.md", "hello.md"],
        )
        result = runner.invoke(
            skfl.cli, ["package", "install", "rsync", "my-pkg", str(tmp_path)]
        )
        assert result.exit_code != 0
        assert "not vetted" in result.output.lower() or "unvetted" in result.output.lower()


# ── removed commands ───────────────────────────────────────────────────


class TestRemovedCommands:
    def test_install_command_removed(self, repo):
        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["install", "rsync", "/tmp/x"])
        assert result.exit_code != 0

    def test_rsync_shortcut_removed(self, repo):
        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["rsync", "/tmp/x"])
        assert result.exit_code != 0

    def test_stow_shortcut_removed(self, repo):
        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["stow", "/tmp/x"])
        assert result.exit_code != 0


# ── completion helpers ─────────────────────────────────────────────────


class TestCompletionHelpers:
    """Tests for the three shell-completion callback functions."""

    # ── _complete_source_files ────────────────────────────────────────

    def test_source_files_returns_all_files(self, repo_with_source):
        results = skfl._complete_source_files(None, None, "")
        values = {r.value for r in results}
        assert "custom/test-src/hello.md" in values
        assert "custom/test-src/script.py" in values
        assert "custom/test-src/sub/nested.txt" in values

    def test_source_files_excludes_gitkeep(self, repo_with_source):
        results = skfl._complete_source_files(None, None, "")
        values = [r.value for r in results]
        assert not any(".gitkeep" in v for v in values)

    def test_source_files_filters_by_prefix(self, repo_with_source):
        results = skfl._complete_source_files(None, None, "custom/test-src/h")
        values = {r.value for r in results}
        assert "custom/test-src/hello.md" in values
        assert "custom/test-src/script.py" not in values
        assert "custom/test-src/sub/nested.txt" not in values

    def test_source_files_prefix_no_match(self, repo_with_source):
        results = skfl._complete_source_files(None, None, "nonexistent/")
        assert results == []

    def test_source_files_empty_sources_dir(self, repo):
        # Repo exists but no sources added yet
        results = skfl._complete_source_files(None, None, "")
        assert results == []

    def test_source_files_no_repo(self, tmp_dir):
        # cwd is not inside any skfl repo — must return [] not raise
        results = skfl._complete_source_files(None, None, "")
        assert results == []

    def test_source_files_returns_completion_items(self, repo_with_source):
        from click.shell_completion import CompletionItem
        results = skfl._complete_source_files(None, None, "")
        assert all(isinstance(r, CompletionItem) for r in results)

    def test_source_files_subdirectory_prefix(self, repo_with_source):
        results = skfl._complete_source_files(None, None, "custom/test-src/sub/")
        values = {r.value for r in results}
        assert "custom/test-src/sub/nested.txt" in values

    def test_source_files_full_match(self, repo_with_source):
        results = skfl._complete_source_files(None, None, "custom/test-src/script.py")
        assert len(results) == 1
        assert results[0].value == "custom/test-src/script.py"

    # ── _complete_patch_files ─────────────────────────────────────────

    def _create_patch(self, repo, rel_path, patch_name="001-test.patch"):
        """Helper: write a minimal patch file at the expected location."""
        pdir = skfl.patches_dir_for(repo, rel_path)
        pdir.mkdir(parents=True, exist_ok=True)
        patch_path = pdir / patch_name
        patch_path.write_text("--- a\n+++ b\n@@ -1 +1 @@\n-old\n+new\n")
        return patch_path

    def test_patch_files_returns_patches(self, repo_with_vetted):
        repo = repo_with_vetted
        rel = Path("custom/test-src/hello.md")
        self._create_patch(repo, rel)

        results = skfl._complete_patch_files(None, None, "")
        values = [r.value for r in results]
        assert any("001-test.patch" in v for v in values)

    def test_patch_files_returns_completion_items(self, repo_with_vetted):
        from click.shell_completion import CompletionItem
        repo = repo_with_vetted
        self._create_patch(repo, Path("custom/test-src/script.py"))

        results = skfl._complete_patch_files(None, None, "")
        assert all(isinstance(r, CompletionItem) for r in results)

    def test_patch_files_paths_are_repo_relative(self, repo_with_vetted):
        repo = repo_with_vetted
        self._create_patch(repo, Path("custom/test-src/hello.md"))

        results = skfl._complete_patch_files(None, None, "")
        assert all(r.value.startswith("30_patches/") for r in results)

    def test_patch_files_filters_by_prefix(self, repo_with_vetted):
        repo = repo_with_vetted
        self._create_patch(repo, Path("custom/test-src/hello.md"), "001-alpha.patch")
        self._create_patch(repo, Path("custom/test-src/script.py"), "001-beta.patch")

        results = skfl._complete_patch_files(None, None, "30_patches/custom/test-src/hello")
        values = [r.value for r in results]
        assert any("001-alpha.patch" in v for v in values)
        assert not any("001-beta.patch" in v for v in values)

    def test_patch_files_no_patches(self, repo):
        results = skfl._complete_patch_files(None, None, "")
        assert results == []

    def test_patch_files_no_repo(self, tmp_dir):
        results = skfl._complete_patch_files(None, None, "")
        assert results == []

    def test_patch_files_profile_patches_included(self, repo_with_vetted):
        repo = repo_with_vetted
        rel = Path("custom/test-src/hello.md")
        pdir = skfl.profile_patches_dir_for(repo, "work", rel)
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "001-work.patch").write_text("--- a\n+++ b\n@@ -1 +1 @@\n-old\n+new\n")

        results = skfl._complete_patch_files(None, None, "")
        values = [r.value for r in results]
        assert any("001-work.patch" in v for v in values)

    # ── _complete_profiles ────────────────────────────────────────────

    def _make_profile(self, repo, name):
        d = repo / skfl.PATCHES_DIR / "_profiles" / name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def test_profiles_returns_all_profiles(self, repo_with_source):
        repo = repo_with_source
        self._make_profile(repo, "work")
        self._make_profile(repo, "home")

        results = skfl._complete_profiles(None, None, "")
        values = {r.value for r in results}
        assert "work" in values
        assert "home" in values

    def test_profiles_filters_by_prefix(self, repo_with_source):
        repo = repo_with_source
        self._make_profile(repo, "work")
        self._make_profile(repo, "home")

        results = skfl._complete_profiles(None, None, "w")
        values = {r.value for r in results}
        assert "work" in values
        assert "home" not in values

    def test_profiles_prefix_no_match(self, repo_with_source):
        repo = repo_with_source
        self._make_profile(repo, "work")

        results = skfl._complete_profiles(None, None, "xyz")
        assert results == []

    def test_profiles_empty_prefix_dir(self, repo):
        # _profiles/ dir doesn't exist
        results = skfl._complete_profiles(None, None, "")
        assert results == []

    def test_profiles_no_repo(self, tmp_dir):
        results = skfl._complete_profiles(None, None, "")
        assert results == []

    def test_profiles_returns_completion_items(self, repo_with_source):
        from click.shell_completion import CompletionItem
        repo = repo_with_source
        self._make_profile(repo, "laptop")

        results = skfl._complete_profiles(None, None, "")
        assert all(isinstance(r, CompletionItem) for r in results)

    def test_profiles_ignores_files_in_profiles_dir(self, repo_with_source):
        # Only directories should be listed, not stray files
        repo = repo_with_source
        self._make_profile(repo, "work")
        # Write a stray file directly in _profiles/
        (repo / skfl.PATCHES_DIR / "_profiles" / "stray.txt").write_text("oops")

        results = skfl._complete_profiles(None, None, "")
        values = {r.value for r in results}
        assert "work" in values
        assert "stray.txt" not in values

    # ── _complete_packages ────────────────────────────────────────────

    def test_packages_returns_all_packages(self, repo):
        (repo / skfl.PACKAGES_DIR / "dotfiles").mkdir(parents=True, exist_ok=True)
        (repo / skfl.PACKAGES_DIR / "work-tools").mkdir(parents=True, exist_ok=True)
        results = skfl._complete_packages(None, None, "")
        values = {r.value for r in results}
        assert "dotfiles" in values
        assert "work-tools" in values

    def test_packages_filters_by_prefix(self, repo):
        (repo / skfl.PACKAGES_DIR / "dotfiles").mkdir(parents=True, exist_ok=True)
        (repo / skfl.PACKAGES_DIR / "work-tools").mkdir(parents=True, exist_ok=True)
        results = skfl._complete_packages(None, None, "dot")
        values = {r.value for r in results}
        assert "dotfiles" in values
        assert "work-tools" not in values

    def test_packages_no_packages_dir(self, repo):
        results = skfl._complete_packages(None, None, "")
        assert results == []

    def test_packages_no_repo(self, tmp_dir):
        results = skfl._complete_packages(None, None, "")
        assert results == []

    def test_packages_returns_completion_items(self, repo):
        from click.shell_completion import CompletionItem
        (repo / skfl.PACKAGES_DIR / "dotfiles").mkdir(parents=True, exist_ok=True)
        results = skfl._complete_packages(None, None, "")
        assert all(isinstance(r, CompletionItem) for r in results)

    # ── -C context ────────────────────────────────────────────────────

    def _make_ctx(self, repo_dir):
        """Return a minimal mock Click context with repo_dir in params."""
        class FakeCtx:
            parent = None
            params = {"repo_dir": str(repo_dir)}
        return FakeCtx()

    def test_source_files_respects_dash_C(self, repo_with_source, tmp_dir):
        # cwd is tmp_dir (no repo), but ctx carries -C pointing at the repo
        ctx = self._make_ctx(repo_with_source)
        results = skfl._complete_source_files(ctx, None, "")
        values = {r.value for r in results}
        assert any("hello.md" in v for v in values)

    def test_patch_files_respects_dash_C(self, repo_with_vetted, tmp_dir):
        ctx = self._make_ctx(repo_with_vetted)
        # Just verify it doesn't raise and returns a list
        results = skfl._complete_patch_files(ctx, None, "")
        assert isinstance(results, list)

    def test_profiles_respects_dash_C(self, repo_with_source, tmp_dir):
        profiles_dir = repo_with_source / skfl.PATCHES_DIR / "_profiles" / "work"
        profiles_dir.mkdir(parents=True, exist_ok=True)
        ctx = self._make_ctx(repo_with_source)
        results = skfl._complete_profiles(ctx, None, "")
        values = {r.value for r in results}
        assert "work" in values

    def test_packages_respects_dash_C(self, repo, tmp_dir):
        (repo / skfl.PACKAGES_DIR / "dotfiles").mkdir(parents=True, exist_ok=True)
        ctx = self._make_ctx(repo)
        results = skfl._complete_packages(ctx, None, "")
        values = {r.value for r in results}
        assert "dotfiles" in values

    def test_dash_C_via_parent_context(self, repo_with_source, tmp_dir):
        # Simulate a subcommand ctx whose parent holds the -C value
        class ParentCtx:
            parent = None
            params = {"repo_dir": str(repo_with_source)}
        class ChildCtx:
            parent = ParentCtx()
            params = {}
        results = skfl._complete_source_files(ChildCtx(), None, "")
        values = {r.value for r in results}
        assert any("hello.md" in v for v in values)

    def test_dash_C_overrides_standard_repos(self, tmp_path, monkeypatch):
        # Even when find_all_repos() returns repos, -C must scope to its repo only.
        # Set up a standard ~/.skfl with a 'standard' source file.
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        home_repo = fake_home / ".skfl"
        CliRunner().invoke(skfl.cli, ["init", str(home_repo)])
        std_file = home_repo / skfl.SOURCES_DIR / "custom" / "std" / "standard.md"
        std_file.parent.mkdir(parents=True, exist_ok=True)
        std_file.write_text("standard\n")
        monkeypatch.setattr(skfl.Path, "home", staticmethod(lambda: fake_home))

        # Set up a separate repo with a 'target' source file.
        target_repo = tmp_path / "other.skfl"
        CliRunner().invoke(skfl.cli, ["init", str(target_repo)])
        tgt_file = target_repo / skfl.SOURCES_DIR / "custom" / "tgt" / "target.md"
        tgt_file.parent.mkdir(parents=True, exist_ok=True)
        tgt_file.write_text("target\n")

        ctx = self._make_ctx(target_repo)
        results = skfl._complete_source_files(ctx, None, "")
        values = {r.value for r in results}
        assert any("target.md" in v for v in values)
        assert not any("standard.md" in v for v in values)


# ── completion command ────────────────────────────────────────────────


class TestCompletionCommand:
    """Tests for 'skfl completion' — outputs the actual completion script."""

    def test_bash_outputs_script(self, tmp_dir):
        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["completion", "bash"])
        assert result.exit_code == 0
        # Click generates a bash function and wires it up with 'complete'
        assert "complete" in result.output
        assert "skfl" in result.output

    def test_zsh_outputs_script(self, tmp_dir):
        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["completion", "zsh"])
        assert result.exit_code == 0
        assert "skfl" in result.output
        assert len(result.output) > 50  # non-trivial script

    def test_fish_outputs_script(self, tmp_dir):
        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["completion", "fish"])
        assert result.exit_code == 0
        assert "skfl" in result.output
        assert len(result.output) > 50

    def test_no_arg_fails(self, tmp_dir):
        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["completion"])
        assert result.exit_code != 0

    def test_invalid_shell_rejected(self, tmp_dir):
        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["completion", "powershell"])
        assert result.exit_code != 0


# ── completion wiring (parameter introspection) ───────────────────────


class TestCompletionWiring:
    """Verify shell_complete callbacks are wired onto the right Click parameters.

    Click 8.x stores the custom completion callback at param._custom_shell_complete
    (the param.shell_complete name is taken by the method that invokes it).
    """

    def _custom_complete(self, command, param_name):
        p = next(p for p in command.params if p.name == param_name)
        return p._custom_shell_complete

    def test_vet_files_wired(self):
        assert self._custom_complete(skfl.vet, "files") is skfl._complete_source_files

    def test_vet_status_files_wired(self):
        assert self._custom_complete(skfl.vet_status, "files") is skfl._complete_source_files

    def test_patch_create_source_file_wired(self):
        assert self._custom_complete(skfl.patch_create, "source_file") is skfl._complete_source_files

    def test_patch_list_source_file_wired(self):
        assert self._custom_complete(skfl.patch_list, "source_file") is skfl._complete_source_files

    def test_patch_remove_patch_file_wired(self):
        assert self._custom_complete(skfl.patch_remove, "patch_file") is skfl._complete_patch_files

    def test_stage_default_files_wired(self):
        assert self._custom_complete(skfl.stage_default, "files") is skfl._complete_source_files

    def test_stage_default_profile_wired(self):
        assert self._custom_complete(skfl.stage_default, "profile") is skfl._complete_profiles

    def test_stage_list_profile_wired(self):
        assert self._custom_complete(skfl.stage_list, "profile") is skfl._complete_profiles

    def test_package_add_name_wired(self):
        assert self._custom_complete(skfl.package_add, "name") is skfl._complete_packages

    def test_package_add_source_path_wired(self):
        assert self._custom_complete(skfl.package_add, "source_path") is skfl._complete_source_files

    def test_package_build_name_wired(self):
        assert self._custom_complete(skfl.package_build, "name") is skfl._complete_packages

    def test_package_build_profile_wired(self):
        assert self._custom_complete(skfl.package_build, "profile") is skfl._complete_profiles

    def test_package_install_rsync_name_wired(self):
        assert self._custom_complete(skfl.package_install_rsync, "name") is skfl._complete_packages

    def test_package_install_stow_name_wired(self):
        assert self._custom_complete(skfl.package_install_stow, "name") is skfl._complete_packages


# ── multi-repo: find_all_repos ────────────────────────────────────────


def _init_repo(path: Path) -> Path:
    """Helper: initialise an skfl repo at path and return path."""
    CliRunner().invoke(skfl.cli, ["init", str(path)])
    return path


class TestFindAllRepos:
    """Tests for find_all_repos() — standard-location discovery."""

    def test_finds_dot_skfl_repo(self, tmp_path, monkeypatch):
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        _init_repo(fake_home / ".skfl")
        monkeypatch.setattr(skfl.Path, "home", staticmethod(lambda: fake_home))
        repos = skfl.find_all_repos()
        assert fake_home / ".skfl" in [p for _, p in repos]

    def test_finds_local_skfl_repo(self, tmp_path, monkeypatch):
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        _init_repo(fake_home / ".local" / ".skfl")
        monkeypatch.setattr(skfl.Path, "home", staticmethod(lambda: fake_home))
        repos = skfl.find_all_repos()
        assert fake_home / ".local" / ".skfl" in [p for _, p in repos]

    def test_finds_glob_skfl_repos(self, tmp_path, monkeypatch):
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        _init_repo(fake_home / "work.skfl")
        _init_repo(fake_home / "personal.skfl")
        monkeypatch.setattr(skfl.Path, "home", staticmethod(lambda: fake_home))
        repos = skfl.find_all_repos()
        names = {n for n, _ in repos}
        assert "work.skfl" in names
        assert "personal.skfl" in names

    def test_finds_multiple_standard_repos(self, tmp_path, monkeypatch):
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        _init_repo(fake_home / ".skfl")
        _init_repo(fake_home / "work.skfl")
        monkeypatch.setattr(skfl.Path, "home", staticmethod(lambda: fake_home))
        repos = skfl.find_all_repos()
        assert len(repos) == 2

    def test_deduplicates_repos(self, tmp_path, monkeypatch):
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        # ~/.skfl — found both by explicit check and by *.skfl glob if dotfiles match
        _init_repo(fake_home / ".skfl")
        monkeypatch.setattr(skfl.Path, "home", staticmethod(lambda: fake_home))
        repos = skfl.find_all_repos()
        resolved = [p.resolve() for _, p in repos]
        assert len(resolved) == len(set(resolved))

    def test_ignores_dirs_without_skfl_toml(self, tmp_path, monkeypatch):
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        (fake_home / "not-a-repo.skfl").mkdir()  # no skfl.toml
        monkeypatch.setattr(skfl.Path, "home", staticmethod(lambda: fake_home))
        repos = skfl.find_all_repos()
        names = {n for n, _ in repos}
        assert "not-a-repo.skfl" not in names

    def test_returns_empty_when_no_repos(self, tmp_path, monkeypatch):
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(skfl.Path, "home", staticmethod(lambda: fake_home))
        assert skfl.find_all_repos() == []

    def test_repo_names_relative_to_home(self, tmp_path, monkeypatch):
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        _init_repo(fake_home / ".skfl")
        _init_repo(fake_home / "work.skfl")
        monkeypatch.setattr(skfl.Path, "home", staticmethod(lambda: fake_home))
        repos = skfl.find_all_repos()
        names = {n for n, _ in repos}
        assert ".skfl" in names
        assert "work.skfl" in names

    def test_local_skfl_name(self, tmp_path, monkeypatch):
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        _init_repo(fake_home / ".local" / ".skfl")
        monkeypatch.setattr(skfl.Path, "home", staticmethod(lambda: fake_home))
        repos = skfl.find_all_repos()
        names = {n for n, _ in repos}
        assert ".local/.skfl" in names


# ── multi-repo: _resolve_repo_and_fpath ──────────────────────────────


class TestResolveRepoAndFpath:
    """Tests for _resolve_repo_and_fpath()."""

    def _make_repos(self, tmp_path, monkeypatch):
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(skfl.Path, "home", staticmethod(lambda: fake_home))
        repo1 = _init_repo(fake_home / ".skfl")
        repo2 = _init_repo(fake_home / "work.skfl")
        repos = [(".skfl", repo1), ("work.skfl", repo2)]
        return repo1, repo2, repos

    def test_strips_first_repo_prefix(self, tmp_path, monkeypatch, tmp_dir):
        repo1, repo2, repos = self._make_repos(tmp_path, monkeypatch)
        os.chdir(repo1)
        r, path = skfl._resolve_repo_and_fpath(".skfl/custom/foo.md", repos)
        assert r == repo1
        assert path == "custom/foo.md"

    def test_strips_second_repo_prefix(self, tmp_path, monkeypatch, tmp_dir):
        repo1, repo2, repos = self._make_repos(tmp_path, monkeypatch)
        os.chdir(repo1)
        r, path = skfl._resolve_repo_and_fpath("work.skfl/custom/bar.md", repos)
        assert r == repo2
        assert path == "custom/bar.md"

    def test_no_prefix_falls_back_to_find_repo(self, tmp_path, monkeypatch, tmp_dir):
        repo1, repo2, repos = self._make_repos(tmp_path, monkeypatch)
        os.chdir(repo1)
        r, path = skfl._resolve_repo_and_fpath("custom/baz.md", repos)
        assert r == repo1
        assert path == "custom/baz.md"

    def test_empty_repos_list_falls_back(self, tmp_path, monkeypatch, repo):
        """With empty repos list, always falls back to find_repo() (cwd)."""
        r, path = skfl._resolve_repo_and_fpath("custom/foo.md", [])
        assert r == repo
        assert path == "custom/foo.md"

    def test_no_match_raises_when_not_in_repo(self, tmp_dir):
        with pytest.raises(Exception, match="Not inside an skfl repository"):
            skfl._resolve_repo_and_fpath("custom/foo.md", [])


# ── multi-repo: _expand_repo_files ───────────────────────────────────


class TestExpandRepoFiles:
    def _make_two_repos(self, tmp_path, monkeypatch):
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(skfl.Path, "home", staticmethod(lambda: fake_home))
        repo1 = _init_repo(fake_home / ".skfl")
        repo2 = _init_repo(fake_home / "work.skfl")
        # Add a source file to each repo
        src1 = repo1 / skfl.SOURCES_DIR / "custom" / "s1" / "a.md"
        src1.parent.mkdir(parents=True)
        src1.write_text("# A\n")
        src2 = repo2 / skfl.SOURCES_DIR / "custom" / "s2" / "b.md"
        src2.parent.mkdir(parents=True)
        src2.write_text("# B\n")
        repos = [(".skfl", repo1), ("work.skfl", repo2)]
        return repo1, repo2, repos

    def test_routes_prefixed_path_to_correct_repo(self, tmp_path, monkeypatch, tmp_dir):
        repo1, repo2, repos = self._make_two_repos(tmp_path, monkeypatch)
        os.chdir(repo1)
        result = skfl._expand_repo_files([".skfl/custom/s1/a.md"], repos)
        assert len(result) == 1
        assert result[0][0] == repo1
        assert result[0][1] == "custom/s1/a.md"

    def test_expands_directory(self, tmp_path, monkeypatch, tmp_dir):
        repo1, repo2, repos = self._make_two_repos(tmp_path, monkeypatch)
        # Add a second file to repo1 so directory expansion returns multiple
        extra = repo1 / skfl.SOURCES_DIR / "custom" / "s1" / "c.md"
        extra.write_text("# C\n")
        os.chdir(repo1)
        result = skfl._expand_repo_files([".skfl/custom/s1"], repos)
        paths = [p for _, p in result]
        assert "custom/s1/a.md" in paths
        assert "custom/s1/c.md" in paths

    def test_multiple_repos_in_one_call(self, tmp_path, monkeypatch, tmp_dir):
        repo1, repo2, repos = self._make_two_repos(tmp_path, monkeypatch)
        result = skfl._expand_repo_files(
            [".skfl/custom/s1/a.md", "work.skfl/custom/s2/b.md"], repos
        )
        assert len(result) == 2
        assert result[0][0] == repo1
        assert result[1][0] == repo2


# ── multi-repo: completion ────────────────────────────────────────────


class TestMultiRepoSourceFilesCompletion:
    """_complete_source_files behaviour with multiple repositories."""

    def _make_two_repos_with_files(self, tmp_path, monkeypatch):
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(skfl.Path, "home", staticmethod(lambda: fake_home))
        repo1 = _init_repo(fake_home / ".skfl")
        repo2 = _init_repo(fake_home / "work.skfl")
        f1 = repo1 / skfl.SOURCES_DIR / "custom" / "src1" / "hello.md"
        f1.parent.mkdir(parents=True)
        f1.write_text("# Hello\n")
        f2 = repo2 / skfl.SOURCES_DIR / "custom" / "src2" / "world.md"
        f2.parent.mkdir(parents=True)
        f2.write_text("# World\n")
        return repo1, repo2

    def test_single_repo_no_prefix(self, tmp_path, monkeypatch, tmp_dir):
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(skfl.Path, "home", staticmethod(lambda: fake_home))
        repo = _init_repo(fake_home / ".skfl")
        src = repo / skfl.SOURCES_DIR / "custom" / "test" / "file.md"
        src.parent.mkdir(parents=True)
        src.write_text("# File\n")

        results = skfl._complete_source_files(None, None, "")
        values = {r.value for r in results}
        # Single repo — no prefix
        assert "custom/test/file.md" in values
        assert not any(v.startswith(".skfl/") for v in values)

    def test_multi_repo_adds_prefix(self, tmp_path, monkeypatch, tmp_dir):
        self._make_two_repos_with_files(tmp_path, monkeypatch)
        results = skfl._complete_source_files(None, None, "")
        values = {r.value for r in results}
        assert ".skfl/custom/src1/hello.md" in values
        assert "work.skfl/custom/src2/world.md" in values

    def test_multi_repo_filter_by_prefix(self, tmp_path, monkeypatch, tmp_dir):
        self._make_two_repos_with_files(tmp_path, monkeypatch)
        results = skfl._complete_source_files(None, None, ".skfl/")
        values = {r.value for r in results}
        assert ".skfl/custom/src1/hello.md" in values
        assert "work.skfl/custom/src2/world.md" not in values

    def test_multi_repo_help_text_set(self, tmp_path, monkeypatch, tmp_dir):
        self._make_two_repos_with_files(tmp_path, monkeypatch)
        results = skfl._complete_source_files(None, None, "")
        assert all(r.help is not None for r in results)

    def test_single_repo_no_help_text(self, tmp_path, monkeypatch, tmp_dir):
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(skfl.Path, "home", staticmethod(lambda: fake_home))
        repo = _init_repo(fake_home / ".skfl")
        src = repo / skfl.SOURCES_DIR / "custom" / "test" / "file.md"
        src.parent.mkdir(parents=True)
        src.write_text("# File\n")
        results = skfl._complete_source_files(None, None, "")
        assert all(r.help is None for r in results)

    def test_no_repos_returns_empty(self, tmp_path, monkeypatch, tmp_dir):
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(skfl.Path, "home", staticmethod(lambda: fake_home))
        results = skfl._complete_source_files(None, None, "")
        assert results == []

    def test_files_from_both_repos_present(self, tmp_path, monkeypatch, tmp_dir):
        self._make_two_repos_with_files(tmp_path, monkeypatch)
        results = skfl._complete_source_files(None, None, "")
        values = {r.value for r in results}
        assert any(".skfl/" in v for v in values)
        assert any("work.skfl/" in v for v in values)


class TestMultiRepoPatchFilesCompletion:
    """_complete_patch_files behaviour with multiple repositories."""

    def _make_two_repos_with_patches(self, tmp_path, monkeypatch):
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(skfl.Path, "home", staticmethod(lambda: fake_home))
        repo1 = _init_repo(fake_home / ".skfl")
        repo2 = _init_repo(fake_home / "work.skfl")
        # Create a patch in each repo
        rel = Path("custom/test/hello.md")
        for repo in (repo1, repo2):
            pdir = skfl.patches_dir_for(repo, rel)
            pdir.mkdir(parents=True, exist_ok=True)
            (pdir / "001-test.patch").write_text("--- a\n+++ b\n@@ -1 +1 @@\n-old\n+new\n")
        return repo1, repo2

    def test_multi_repo_patch_completion_has_prefix(self, tmp_path, monkeypatch, tmp_dir):
        self._make_two_repos_with_patches(tmp_path, monkeypatch)
        results = skfl._complete_patch_files(None, None, "")
        values = {r.value for r in results}
        assert any(v.startswith(".skfl/") for v in values)
        assert any(v.startswith("work.skfl/") for v in values)

    def test_single_repo_patch_no_prefix(self, tmp_path, monkeypatch, tmp_dir):
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(skfl.Path, "home", staticmethod(lambda: fake_home))
        repo = _init_repo(fake_home / ".skfl")
        rel = Path("custom/test/hello.md")
        pdir = skfl.patches_dir_for(repo, rel)
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "001-test.patch").write_text("--- a\n+++ b\n@@ -1 +1 @@\n-old\n+new\n")

        results = skfl._complete_patch_files(None, None, "")
        values = {r.value for r in results}
        assert all(v.startswith("30_patches/") for v in values)
        assert not any(v.startswith(".skfl/") for v in values)


# ── multi-repo: vet command ───────────────────────────────────────────


class TestMultiRepoVetCommand:
    """End-to-end tests for 'skfl vet' with repo-prefixed paths."""

    def test_vet_with_repo_prefix(self, tmp_path, monkeypatch, tmp_dir):
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(skfl.Path, "home", staticmethod(lambda: fake_home))
        repo = _init_repo(fake_home / ".skfl")
        src = repo / skfl.SOURCES_DIR / "custom" / "test" / "hello.md"
        src.parent.mkdir(parents=True)
        src.write_text("# Hello\n")

        runner = CliRunner()
        with mock_patch("subprocess.run"):
            result = runner.invoke(
                skfl.cli, ["vet", ".skfl/custom/test/hello.md"], input="y\n"
            )
        assert result.exit_code == 0
        assert "vetted" in result.output

    def test_vet_correct_repo_selected(self, tmp_path, monkeypatch, tmp_dir):
        """File in work.skfl repo is vetted in the right repo."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(skfl.Path, "home", staticmethod(lambda: fake_home))
        _init_repo(fake_home / ".skfl")
        repo2 = _init_repo(fake_home / "work.skfl")
        src = repo2 / skfl.SOURCES_DIR / "custom" / "test" / "skill.md"
        src.parent.mkdir(parents=True)
        src.write_text("# Skill\n")

        runner = CliRunner()
        with mock_patch("subprocess.run"):
            result = runner.invoke(
                skfl.cli, ["vet", "work.skfl/custom/test/skill.md"], input="y\n"
            )
        assert result.exit_code == 0
        # Verify the vetted hash was stored in work.skfl, not .skfl
        rel = Path("custom/test/skill.md")
        assert skfl.read_vetted_hash(repo2, rel) is not None
        default_repo = fake_home / ".skfl"
        assert skfl.read_vetted_hash(default_repo, rel) is None


# ── multi-repo: vet-status command ───────────────────────────────────


class TestMultiRepoVetStatusCommand:
    def test_no_args_shows_all_repos(self, tmp_path, monkeypatch, tmp_dir):
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(skfl.Path, "home", staticmethod(lambda: fake_home))
        repo1 = _init_repo(fake_home / ".skfl")
        repo2 = _init_repo(fake_home / "work.skfl")
        (repo1 / skfl.SOURCES_DIR / "custom" / "r1" / "a.md").parent.mkdir(parents=True)
        (repo1 / skfl.SOURCES_DIR / "custom" / "r1" / "a.md").write_text("# A\n")
        (repo2 / skfl.SOURCES_DIR / "custom" / "r2" / "b.md").parent.mkdir(parents=True)
        (repo2 / skfl.SOURCES_DIR / "custom" / "r2" / "b.md").write_text("# B\n")

        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["vet-status"])
        assert result.exit_code == 0
        assert ".skfl/custom/r1/a.md" in result.output
        assert "work.skfl/custom/r2/b.md" in result.output

    def test_with_repo_prefix_arg(self, tmp_path, monkeypatch, tmp_dir):
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setattr(skfl.Path, "home", staticmethod(lambda: fake_home))
        repo = _init_repo(fake_home / ".skfl")
        src = repo / skfl.SOURCES_DIR / "custom" / "test" / "hello.md"
        src.parent.mkdir(parents=True)
        src.write_text("# Hello\n")

        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["vet-status", ".skfl/custom/test/hello.md"])
        assert result.exit_code == 0
        assert "unvetted" in result.output


# ── -C global option ───────────────────────────────────────────────────


class TestDashC:
    def test_source_custom_targets_specified_repo(self, tmp_path, tmp_dir):
        """skfl -C <repo> source custom ... writes to <repo>, not cwd repo."""
        target_repo = tmp_path / "target"
        cwd_repo = tmp_dir  # tmp_dir is already chdir'd here

        # Init both repos; cwd is inside cwd_repo
        runner = CliRunner()
        runner.invoke(skfl.cli, ["init", str(cwd_repo)])
        runner.invoke(skfl.cli, ["init", str(target_repo)])

        src = tmp_path / "skills"
        src.mkdir()
        (src / "skill.md").write_text("# Skill\n")

        result = runner.invoke(
            skfl.cli, ["-C", str(target_repo), "source", "custom", "my-src", str(src)]
        )
        assert result.exit_code == 0, result.output

        # Source must appear in target_repo, not cwd_repo
        assert (target_repo / skfl.SOURCES_DIR / "custom" / "my-src" / "skill.md").exists()
        assert not (cwd_repo / skfl.SOURCES_DIR / "custom" / "my-src").exists()

    def test_source_pull_targets_specified_repo(self, tmp_path, tmp_dir):
        """skfl -C <repo> source pull ... writes to <repo>."""
        target_repo = tmp_path / "target"
        cwd_repo = tmp_dir

        runner = CliRunner()
        runner.invoke(skfl.cli, ["init", str(cwd_repo)])
        runner.invoke(skfl.cli, ["init", str(target_repo)])

        with mock_patch("subprocess.run"):
            result = runner.invoke(
                skfl.cli,
                ["-C", str(target_repo), "source", "pull", "github", "obra/superpowers"],
            )
        assert result.exit_code == 0, result.output

        config = skfl.load_config(target_repo)
        assert "obra/superpowers" in config.get("sources", {})
        assert "obra/superpowers" not in skfl.load_config(cwd_repo).get("sources", {})

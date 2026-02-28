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
    vetted = repo / skfl.VETTED_DIR
    # Manually vet all files (simulating interactive approval)
    for src_file in sources.rglob("*"):
        if src_file.is_file() and src_file.name != ".gitkeep":
            rel = src_file.relative_to(sources)
            dst = vetted / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst)
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
        result = runner.invoke(skfl.cli, ["vet", "status"])
        assert result.exit_code == 0
        assert "unvetted" in result.output
        assert "hello.md" in result.output

    def test_shows_vetted_status(self, repo_with_vetted):
        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["vet", "status"])
        assert result.exit_code == 0
        assert "vetted" in result.output

    def test_shows_modified_status(self, repo_with_vetted):
        rel = Path("custom/test-src/hello.md")
        source = repo_with_vetted / skfl.SOURCES_DIR / rel
        source.write_text("# Modified\n")

        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["vet", "status"])
        assert result.exit_code == 0
        assert "modified" in result.output

    def test_no_source_files(self, repo):
        runner = CliRunner()
        result = runner.invoke(skfl.cli, ["vet", "status"])
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

        # Verify the vetted snapshot was created
        vetted = repo_with_source / skfl.VETTED_DIR / "custom/test-src/hello.md"
        assert vetted.exists()

    def test_vet_unvetted_reject(self, repo_with_source):
        runner = CliRunner()
        with mock_patch("subprocess.run"):
            result = runner.invoke(
                skfl.cli, ["vet", "custom/test-src/hello.md"], input="n\n"
            )
        assert result.exit_code == 0
        assert "Skipping" in result.output

        vetted = repo_with_source / skfl.VETTED_DIR / "custom/test-src/hello.md"
        assert not vetted.exists()

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

        # Verify vetted snapshot was updated
        vetted = repo_with_vetted / skfl.VETTED_DIR / rel
        assert vetted.read_text() == "# Hello Updated\n"

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
        editor_script.write_text("#!/bin/sh\nsed -i 's/World/Universe/' \"$1\"\n")
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

    def test_stage_unvetted_fails(self, repo_with_source):
        runner = CliRunner()
        result = runner.invoke(
            skfl.cli, ["stage", "custom/test-src/hello.md"]
        )
        assert result.exit_code != 0
        assert "not been vetted" in result.output

    def test_stage_modified_fails(self, repo_with_vetted):
        source = repo_with_vetted / skfl.SOURCES_DIR / "custom/test-src/hello.md"
        source.write_text("# Changed\n")

        runner = CliRunner()
        result = runner.invoke(
            skfl.cli, ["stage", "custom/test-src/hello.md"]
        )
        assert result.exit_code != 0
        assert "modified" in result.output

    def test_stage_with_patches(self, repo_with_vetted, tmp_path):
        repo = repo_with_vetted
        rel = Path("custom/test-src/hello.md")

        # Create a valid patch
        original = (repo / skfl.VETTED_DIR / rel).read_bytes()
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
        result = runner.invoke(skfl.cli, ["vet", "status"])
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
        """Test that modifying source makes file require re-vetting."""
        repo = repo_with_vetted
        runner = CliRunner()
        rel = Path("custom/test-src/hello.md")

        # Modify source (simulating a source pull update)
        source = repo / skfl.SOURCES_DIR / rel
        source.write_text("# Hello Updated\n\nNew content\n")

        # Vet status should show modified
        result = runner.invoke(skfl.cli, ["vet", "status"])
        assert "modified" in result.output

        # Staging should fail
        result = runner.invoke(skfl.cli, ["stage", "custom/test-src/hello.md"])
        assert result.exit_code != 0
        assert "modified" in result.output

        # Re-vet (approve changes)
        with mock_patch("subprocess.run"):
            result = runner.invoke(
                skfl.cli, ["vet", "custom/test-src/hello.md"], input="y\n"
            )
        assert result.exit_code == 0

        # Now staging should work
        result = runner.invoke(skfl.cli, ["stage", "custom/test-src/hello.md"])
        assert result.exit_code == 0

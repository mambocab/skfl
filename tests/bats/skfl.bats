#!/usr/bin/env bats
# Integration tests for skfl. Every test runs under chroot.

load setup_chroot

setup() {
    setup_chroot
}

teardown() {
    teardown_chroot
}

# ── init ───────────────────────────────────────────────────────────────

@test "init creates skfl.toml" {
    skfl_in_chroot init "$REPO"
    run chroot "$CHROOT" /usr/bin/cat "$REPO/skfl.toml"
    [ "$status" -eq 0 ]
    [[ "$output" == *"version = 1"* ]]
}

@test "init creates all five directories" {
    skfl_in_chroot init "$REPO"
    run chroot "$CHROOT" /bin/sh -c "ls -d $REPO/10_sources $REPO/20_vetted $REPO/30_patches $REPO/40_staged $REPO/50_packages"
    [ "$status" -eq 0 ]
    [[ "$output" == *"10_sources"* ]]
    [[ "$output" == *"20_vetted"* ]]
    [[ "$output" == *"30_patches"* ]]
    [[ "$output" == *"40_staged"* ]]
    [[ "$output" == *"50_packages"* ]]
}

@test "init creates .gitignore" {
    skfl_in_chroot init "$REPO"
    run chroot "$CHROOT" /usr/bin/cat "$REPO/.gitignore"
    [ "$status" -eq 0 ]
}

@test "init creates .gitkeep in each directory" {
    skfl_in_chroot init "$REPO"
    for dir in 10_sources 20_vetted 30_patches 40_staged; do
        run chroot "$CHROOT" /bin/sh -c "test -f $REPO/$dir/.gitkeep"
        [ "$status" -eq 0 ]
    done
}

@test "init fails if already initialized" {
    skfl_in_chroot init "$REPO"
    run skfl_in_chroot init "$REPO"
    [ "$status" -ne 0 ]
    [[ "$output" == *"already exists"* ]]
}

@test "init in a subdirectory" {
    skfl_in_chroot init "$REPO/sub/dir"
    run chroot "$CHROOT" /bin/sh -c "test -f $REPO/sub/dir/skfl.toml"
    [ "$status" -eq 0 ]
}

# ── doctor ─────────────────────────────────────────────────────────────

@test "doctor reports python3" {
    skfl_in_chroot init "$REPO"
    run skfl_in_chroot doctor
    [[ "$output" == *"python3"* ]]
}

@test "doctor reports diff" {
    skfl_in_chroot init "$REPO"
    run skfl_in_chroot doctor
    [[ "$output" == *"diff"* ]]
}

@test "doctor reports patch" {
    skfl_in_chroot init "$REPO"
    run skfl_in_chroot doctor
    [[ "$output" == *"patch"* ]]
}

# ── source custom ─────────────────────────────────────────────────────

@test "source custom registers a source" {
    skfl_in_chroot init "$REPO"
    # Create custom source files in chroot
    chroot "$CHROOT" /bin/sh -c "mkdir -p /tmp/src && echo '# Skill' > /tmp/src/skill.md"
    run skfl_in_chroot source custom my-skills /tmp/src
    [ "$status" -eq 0 ]
    [[ "$output" == *"Registered"* ]]
}

@test "source custom copies files" {
    skfl_in_chroot init "$REPO"
    chroot "$CHROOT" /bin/sh -c "mkdir -p /tmp/src && echo 'content' > /tmp/src/file.txt"
    skfl_in_chroot source custom test-src /tmp/src
    run chroot "$CHROOT" /usr/bin/cat "$REPO/10_sources/custom/test-src/file.txt"
    [ "$status" -eq 0 ]
    [[ "$output" == "content" ]]
}

@test "source custom fails on duplicate" {
    skfl_in_chroot init "$REPO"
    chroot "$CHROOT" /bin/sh -c "mkdir -p /tmp/src && echo 'x' > /tmp/src/a.txt"
    skfl_in_chroot source custom dup /tmp/src
    run skfl_in_chroot source custom dup /tmp/src
    [ "$status" -ne 0 ]
    [[ "$output" == *"already exists"* ]]
}

@test "source custom preserves subdirectory structure" {
    skfl_in_chroot init "$REPO"
    chroot "$CHROOT" /bin/sh -c "mkdir -p /tmp/src/sub/deep && echo 'deep' > /tmp/src/sub/deep/f.txt"
    skfl_in_chroot source custom nested /tmp/src
    run chroot "$CHROOT" /usr/bin/cat "$REPO/10_sources/custom/nested/sub/deep/f.txt"
    [ "$status" -eq 0 ]
    [[ "$output" == "deep" ]]
}

# ── source list ────────────────────────────────────────────────────────

@test "source list shows no sources initially" {
    skfl_in_chroot init "$REPO"
    run skfl_in_chroot source list
    [ "$status" -eq 0 ]
    [[ "$output" == *"No sources"* ]]
}

@test "source list shows registered sources" {
    skfl_in_chroot init "$REPO"
    chroot "$CHROOT" /bin/sh -c "mkdir -p /tmp/src && echo 'x' > /tmp/src/a.txt"
    skfl_in_chroot source custom my-source /tmp/src
    run skfl_in_chroot source list
    [ "$status" -eq 0 ]
    [[ "$output" == *"my-source"* ]]
    [[ "$output" == *"custom"* ]]
}

# ── vet status ─────────────────────────────────────────────────────────

@test "vet status shows unvetted files" {
    skfl_in_chroot init "$REPO"
    chroot "$CHROOT" /bin/sh -c "mkdir -p /tmp/src && echo 'content' > /tmp/src/file.md"
    skfl_in_chroot source custom test /tmp/src
    run skfl_in_chroot vet status
    [ "$status" -eq 0 ]
    [[ "$output" == *"unvetted"* ]]
    [[ "$output" == *"file.md"* ]]
}

@test "vet status shows vetted files" {
    skfl_in_chroot init "$REPO"
    chroot "$CHROOT" /bin/sh -c "mkdir -p /tmp/src && echo 'content' > /tmp/src/file.md"
    skfl_in_chroot source custom test /tmp/src
    vet_file_in_chroot custom/test/file.md
    run skfl_in_chroot vet status
    [ "$status" -eq 0 ]
    [[ "$output" == *"vetted"* ]]
}

@test "vet status shows modified files" {
    skfl_in_chroot init "$REPO"
    chroot "$CHROOT" /bin/sh -c "mkdir -p /tmp/src && echo 'original' > /tmp/src/file.md"
    skfl_in_chroot source custom test /tmp/src
    vet_file_in_chroot custom/test/file.md
    # Modify the source
    chroot "$CHROOT" /bin/sh -c "echo 'modified' > $REPO/10_sources/custom/test/file.md"
    run skfl_in_chroot vet status
    [ "$status" -eq 0 ]
    [[ "$output" == *"modified"* ]]
}

@test "vet status with no source files" {
    skfl_in_chroot init "$REPO"
    run skfl_in_chroot vet status
    [ "$status" -eq 0 ]
    [[ "$output" == *"No source files"* ]]
}

@test "vet status shows multiple files" {
    skfl_in_chroot init "$REPO"
    chroot "$CHROOT" /bin/sh -c "mkdir -p /tmp/src && echo 'a' > /tmp/src/a.txt && echo 'b' > /tmp/src/b.txt"
    skfl_in_chroot source custom multi /tmp/src
    run skfl_in_chroot vet status
    [ "$status" -eq 0 ]
    [[ "$output" == *"a.txt"* ]]
    [[ "$output" == *"b.txt"* ]]
}

# ── vet command ────────────────────────────────────────────────────────

@test "vet reports already vetted file" {
    skfl_in_chroot init "$REPO"
    chroot "$CHROOT" /bin/sh -c "mkdir -p /tmp/src && echo 'content' > /tmp/src/file.md"
    skfl_in_chroot source custom test /tmp/src
    vet_file_in_chroot custom/test/file.md
    run skfl_in_chroot vet custom/test/file.md
    [ "$status" -eq 0 ]
    [[ "$output" == *"already vetted"* ]]
}

# ── patch list ─────────────────────────────────────────────────────────

@test "patch list shows no patches" {
    skfl_in_chroot init "$REPO"
    run skfl_in_chroot patch list
    [ "$status" -eq 0 ]
    [[ "$output" == *"No patches"* ]]
}

@test "patch list shows patches for a file" {
    skfl_in_chroot init "$REPO"
    chroot "$CHROOT" /bin/sh -c "mkdir -p /tmp/src && echo 'hello' > /tmp/src/file.md"
    skfl_in_chroot source custom test /tmp/src
    # Create a patch directory with a patch
    chroot "$CHROOT" /bin/sh -c "mkdir -p '$REPO/30_patches/custom/test/file.md.d' && echo 'patch data' > '$REPO/30_patches/custom/test/file.md.d/001-fix.patch'"
    run skfl_in_chroot patch list custom/test/file.md
    [ "$status" -eq 0 ]
    [[ "$output" == *"001-fix.patch"* ]]
}

@test "patch list shows all patches" {
    skfl_in_chroot init "$REPO"
    chroot "$CHROOT" /bin/sh -c "mkdir -p '$REPO/30_patches/custom/test/a.md.d' && echo 'p' > '$REPO/30_patches/custom/test/a.md.d/001-x.patch'"
    chroot "$CHROOT" /bin/sh -c "mkdir -p '$REPO/30_patches/custom/test/b.md.d' && echo 'p' > '$REPO/30_patches/custom/test/b.md.d/001-y.patch'"
    run skfl_in_chroot patch list
    [ "$status" -eq 0 ]
    [[ "$output" == *"001-x.patch"* ]]
    [[ "$output" == *"001-y.patch"* ]]
}

# ── patch remove ───────────────────────────────────────────────────────

@test "patch remove deletes a patch file" {
    skfl_in_chroot init "$REPO"
    chroot "$CHROOT" /bin/sh -c "mkdir -p '$REPO/30_patches/custom/test/file.md.d' && echo 'p' > '$REPO/30_patches/custom/test/file.md.d/001-fix.patch'"
    run skfl_in_chroot patch remove '30_patches/custom/test/file.md.d/001-fix.patch'
    [ "$status" -eq 0 ]
    [[ "$output" == *"Removed"* ]]
    # Verify file is gone
    run chroot "$CHROOT" /bin/sh -c "test -f '$REPO/30_patches/custom/test/file.md.d/001-fix.patch'"
    [ "$status" -ne 0 ]
}

@test "patch remove cleans up empty .d directory" {
    skfl_in_chroot init "$REPO"
    chroot "$CHROOT" /bin/sh -c "mkdir -p '$REPO/30_patches/custom/test/file.md.d' && echo 'p' > '$REPO/30_patches/custom/test/file.md.d/001-fix.patch'"
    skfl_in_chroot patch remove '30_patches/custom/test/file.md.d/001-fix.patch'
    run chroot "$CHROOT" /bin/sh -c "test -d '$REPO/30_patches/custom/test/file.md.d'"
    [ "$status" -ne 0 ]
}

@test "patch remove fails for nonexistent patch" {
    skfl_in_chroot init "$REPO"
    run skfl_in_chroot patch remove nonexistent.patch
    [ "$status" -ne 0 ]
    [[ "$output" == *"not found"* ]]
}

@test "cannot operate outside a repository" {
    run chroot "$CHROOT" /bin/sh -c "cd /tmp && /usr/local/bin/python3 /usr/local/bin/skfl vet status"
    [ "$status" -ne 0 ]
    [[ "$output" == *"Not inside an skfl repository"* ]]
}

@test "multiple sources can coexist" {
    skfl_in_chroot init "$REPO"
    chroot "$CHROOT" /bin/sh -c "mkdir -p /tmp/src1 && echo 'from source 1' > /tmp/src1/a.txt"
    chroot "$CHROOT" /bin/sh -c "mkdir -p /tmp/src2 && echo 'from source 2' > /tmp/src2/b.txt"
    skfl_in_chroot source custom source1 /tmp/src1
    skfl_in_chroot source custom source2 /tmp/src2
    run skfl_in_chroot source list
    [ "$status" -eq 0 ]
    [[ "$output" == *"source1"* ]]
    [[ "$output" == *"source2"* ]]
    run skfl_in_chroot vet status
    [[ "$output" == *"a.txt"* ]]
    [[ "$output" == *"b.txt"* ]]
}

# ── package ────────────────────────────────────────────────────────────────

@test "init creates 50_packages directory" {
    skfl_in_chroot init "$REPO"
    run chroot "$CHROOT" /bin/sh -c "test -d $REPO/50_packages"
    [ "$status" -eq 0 ]
}

@test "package init creates directory" {
    skfl_in_chroot init "$REPO"
    run skfl_in_chroot package init my-setup
    [ "$status" -eq 0 ]
    run chroot "$CHROOT" /bin/sh -c "test -d $REPO/50_packages/my-setup"
    [ "$status" -eq 0 ]
}

@test "package init fails on duplicate" {
    skfl_in_chroot init "$REPO"
    skfl_in_chroot package init my-setup
    run skfl_in_chroot package init my-setup
    [ "$status" -ne 0 ]
    [[ "$output" == *"already exists"* ]]
}

@test "package add creates symlink to file" {
    skfl_in_chroot init "$REPO"
    chroot "$CHROOT" /bin/sh -c "mkdir -p /tmp/src && echo '# Skill' > /tmp/src/skill.md"
    skfl_in_chroot source custom test /tmp/src
    skfl_in_chroot package init my-setup
    run skfl_in_chroot package add my-setup custom/test/skill.md skill.md
    [ "$status" -eq 0 ]
    run chroot "$CHROOT" /bin/sh -c "test -L $REPO/50_packages/my-setup/skill.md"
    [ "$status" -eq 0 ]
}

@test "package add creates symlink to directory" {
    skfl_in_chroot init "$REPO"
    chroot "$CHROOT" /bin/sh -c "mkdir -p /tmp/src/skills && echo '# Skill' > /tmp/src/skills/skill.md"
    skfl_in_chroot source custom test /tmp/src
    skfl_in_chroot package init my-setup
    run skfl_in_chroot package add my-setup custom/test/skills skills
    [ "$status" -eq 0 ]
    run chroot "$CHROOT" /bin/sh -c "test -L $REPO/50_packages/my-setup/skills"
    [ "$status" -eq 0 ]
}

@test "package build refuses unvetted file" {
    skfl_in_chroot init "$REPO"
    chroot "$CHROOT" /bin/sh -c "mkdir -p /tmp/src && echo '# Skill' > /tmp/src/skill.md"
    skfl_in_chroot source custom test /tmp/src
    skfl_in_chroot package init my-setup
    skfl_in_chroot package add my-setup custom/test/skill.md skill.md
    run skfl_in_chroot package build my-setup
    [ "$status" -ne 0 ]
}

@test "package full workflow: init -> add -> install rsync (build on demand)" {
    skfl_in_chroot init "$REPO"
    chroot "$CHROOT" /bin/sh -c "mkdir -p /tmp/src && echo '# Skill' > /tmp/src/skill.md"
    skfl_in_chroot source custom test /tmp/src
    vet_file_in_chroot custom/test/skill.md
    skfl_in_chroot package init my-setup
    skfl_in_chroot package add my-setup custom/test/skill.md skills/skill.md
    # Install without explicit build — should build on demand
    chroot "$CHROOT" /bin/sh -c "mkdir -p /tmp/target"
    run skfl_in_chroot package install rsync my-setup /tmp/target
    [ "$status" -eq 0 ]
    run chroot "$CHROOT" /usr/bin/cat /tmp/target/skills/skill.md
    [ "$status" -eq 0 ]
    [[ "$output" == "# Skill" ]]
}

@test "package build applies patches" {
    skfl_in_chroot init "$REPO"
    chroot "$CHROOT" /bin/sh -c "mkdir -p /tmp/src && printf 'line1\nline2\n' > /tmp/src/file.txt"
    skfl_in_chroot source custom test /tmp/src
    vet_file_in_chroot custom/test/file.txt
    chroot "$CHROOT" /bin/sh -c "
        printf 'line1\nline2 patched\n' > /tmp/patched.txt
        mkdir -p '$REPO/30_patches/custom/test/file.txt.d'
        diff -u $REPO/10_sources/custom/test/file.txt /tmp/patched.txt > '$REPO/30_patches/custom/test/file.txt.d/001-fix.patch' || true
    "
    skfl_in_chroot package init my-setup
    skfl_in_chroot package add my-setup custom/test/file.txt file.txt
    run skfl_in_chroot package build my-setup
    [ "$status" -eq 0 ]
    run chroot "$CHROOT" /usr/bin/cat "$REPO/40_staged/my-setup/file.txt"
    [[ "$output" == *"line2 patched"* ]]
}

@test "old install command is gone" {
    skfl_in_chroot init "$REPO"
    run skfl_in_chroot install rsync /tmp/x
    [ "$status" -ne 0 ]
}

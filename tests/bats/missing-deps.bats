#!/usr/bin/env bats
# Tests for behavior when runtime dependencies are missing.
# These tests verify skfl handles absent tools gracefully.
# Each test sets up a chroot and then removes specific binaries to
# simulate missing dependencies in a controlled way.

load setup_chroot

setup() {
    setup_chroot
}

teardown() {
    teardown_chroot
}

# Helper: remove a named binary from every location in the chroot.
remove_from_chroot() {
    local tool="$1"
    find "$CHROOT" -name "$tool" \( -type f -o -type l \) -delete 2>/dev/null || true
}

# ── doctor: optional tools ─────────────────────────────────────────────

@test "doctor: exits zero when only optional tools are missing" {
    skfl_in_chroot init "$REPO"
    remove_from_chroot rsync
    remove_from_chroot stow
    remove_from_chroot glow
    remove_from_chroot fzf
    run skfl_in_chroot doctor
    [ "$status" -eq 0 ]
    [[ "$output" == *"All required dependencies"* ]]
}

@test "doctor: reports missing rsync as optional" {
    skfl_in_chroot init "$REPO"
    remove_from_chroot rsync
    run skfl_in_chroot doctor
    [[ "$output" == *"miss"*"rsync"* ]]
}

@test "doctor: reports missing stow as optional" {
    skfl_in_chroot init "$REPO"
    remove_from_chroot stow
    run skfl_in_chroot doctor
    [[ "$output" == *"miss"*"stow"* ]]
}

# ── doctor: required tools ─────────────────────────────────────────────

@test "doctor: exits non-zero when required tool is missing" {
    skfl_in_chroot init "$REPO"
    remove_from_chroot diff
    run skfl_in_chroot doctor
    [ "$status" -ne 0 ]
    [[ "$output" == *"MISS"* ]]
}

@test "doctor: reports missing diff as required" {
    skfl_in_chroot init "$REPO"
    remove_from_chroot diff
    run skfl_in_chroot doctor
    [[ "$output" == *"MISS"*"diff"* ]]
}

@test "doctor: reports missing patch as required" {
    skfl_in_chroot init "$REPO"
    remove_from_chroot patch
    run skfl_in_chroot doctor
    [[ "$output" == *"MISS"*"patch"* ]]
}

# ── package install without tools ──────────────────────────────────────

@test "package install rsync: fails gracefully without rsync" {
    skfl_in_chroot init "$REPO"
    chroot "$CHROOT" /bin/sh -c "mkdir -p /tmp/src && echo '# Skill' > /tmp/src/skill.md"
    skfl_in_chroot source custom test /tmp/src
    vet_file_in_chroot custom/test/skill.md
    skfl_in_chroot package new my-pkg
    skfl_in_chroot package add my-pkg custom/test/skill.md skill.md
    skfl_in_chroot package build my-pkg
    # Remove rsync
    remove_from_chroot rsync
    chroot "$CHROOT" /bin/sh -c "mkdir -p /tmp/target"
    run skfl_in_chroot package install rsync my-pkg /tmp/target
    [ "$status" -ne 0 ]
    [[ "$output" == *"not installed"* ]]
}

# ── stage: patch binary missing ────────────────────────────────────────

@test "stage: succeeds without patches even when patch binary is absent" {
    skfl_in_chroot init "$REPO"
    chroot "$CHROOT" /bin/sh -c "mkdir -p /tmp/src && echo 'hello' > /tmp/src/file.md"
    skfl_in_chroot source custom test /tmp/src
    vet_file_in_chroot custom/test/file.md
    # Remove patch binary
    remove_from_chroot patch
    # Stage without any patches should still work (no patches to apply)
    run skfl_in_chroot stage custom/test/file.md
    [ "$status" -eq 0 ]
    run chroot "$CHROOT" /usr/bin/cat "$REPO/40_staged/custom/test/file.md"
    [[ "$output" == "hello" ]]
}

@test "stage: fails when patches exist but patch binary is absent" {
    skfl_in_chroot init "$REPO"
    chroot "$CHROOT" /bin/sh -c "mkdir -p /tmp/src && printf 'line1\nline2\n' > /tmp/src/file.txt"
    skfl_in_chroot source custom test /tmp/src
    vet_file_in_chroot custom/test/file.txt
    # Create a patch while diff and patch are still available
    chroot "$CHROOT" /bin/sh -c "
        printf 'line1\nLINE2\n' > /tmp/modified.txt
        mkdir -p '$REPO/30_patches/custom/test/file.txt.d'
        diff -u $REPO/10_sources/custom/test/file.txt /tmp/modified.txt > '$REPO/30_patches/custom/test/file.txt.d/001-fix.patch' || true
    "
    # Remove patch binary
    remove_from_chroot patch
    # Stage should fail because patches cannot be applied
    run skfl_in_chroot stage custom/test/file.txt
    [ "$status" -ne 0 ]
}

# ── core operations without diff ───────────────────────────────────────

@test "init works without diff" {
    remove_from_chroot diff
    run skfl_in_chroot init "$REPO"
    [ "$status" -eq 0 ]
}

@test "source custom works without diff" {
    skfl_in_chroot init "$REPO"
    remove_from_chroot diff
    chroot "$CHROOT" /bin/sh -c "mkdir -p /tmp/src && echo 'content' > /tmp/src/file.md"
    run skfl_in_chroot source custom test /tmp/src
    [ "$status" -eq 0 ]
}

@test "vet-status works without diff" {
    skfl_in_chroot init "$REPO"
    chroot "$CHROOT" /bin/sh -c "mkdir -p /tmp/src && echo 'content' > /tmp/src/file.md"
    skfl_in_chroot source custom test /tmp/src
    remove_from_chroot diff
    run skfl_in_chroot vet-status
    [ "$status" -eq 0 ]
    [[ "$output" == *"file.md"* ]]
}

@test "stage without patches works without diff" {
    skfl_in_chroot init "$REPO"
    chroot "$CHROOT" /bin/sh -c "mkdir -p /tmp/src && echo 'content' > /tmp/src/file.md"
    skfl_in_chroot source custom test /tmp/src
    vet_file_in_chroot custom/test/file.md
    remove_from_chroot diff
    run skfl_in_chroot stage custom/test/file.md
    [ "$status" -eq 0 ]
}

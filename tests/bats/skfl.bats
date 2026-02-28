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

@test "init creates all four directories" {
    skfl_in_chroot init "$REPO"
    run chroot "$CHROOT" /bin/sh -c "ls -d $REPO/10_sources $REPO/20_vetted $REPO/30_patches $REPO/40_staged"
    [ "$status" -eq 0 ]
    [[ "$output" == *"10_sources"* ]]
    [[ "$output" == *"20_vetted"* ]]
    [[ "$output" == *"30_patches"* ]]
    [[ "$output" == *"40_staged"* ]]
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
    # Manually vet by copying to vetted dir
    chroot "$CHROOT" /bin/sh -c "mkdir -p $REPO/20_vetted/custom/test && cp $REPO/10_sources/custom/test/file.md $REPO/20_vetted/custom/test/file.md"
    run skfl_in_chroot vet status
    [ "$status" -eq 0 ]
    [[ "$output" == *"vetted"* ]]
}

@test "vet status shows modified files" {
    skfl_in_chroot init "$REPO"
    chroot "$CHROOT" /bin/sh -c "mkdir -p /tmp/src && echo 'original' > /tmp/src/file.md"
    skfl_in_chroot source custom test /tmp/src
    # Vet the file
    chroot "$CHROOT" /bin/sh -c "mkdir -p $REPO/20_vetted/custom/test && cp $REPO/10_sources/custom/test/file.md $REPO/20_vetted/custom/test/file.md"
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
    chroot "$CHROOT" /bin/sh -c "mkdir -p $REPO/20_vetted/custom/test && cp $REPO/10_sources/custom/test/file.md $REPO/20_vetted/custom/test/file.md"
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

# ── stage ──────────────────────────────────────────────────────────────

@test "stage vetted file" {
    skfl_in_chroot init "$REPO"
    chroot "$CHROOT" /bin/sh -c "mkdir -p /tmp/src && echo 'hello world' > /tmp/src/file.md"
    skfl_in_chroot source custom test /tmp/src
    # Vet the file
    chroot "$CHROOT" /bin/sh -c "mkdir -p $REPO/20_vetted/custom/test && cp $REPO/10_sources/custom/test/file.md $REPO/20_vetted/custom/test/file.md"
    run skfl_in_chroot stage custom/test/file.md
    [ "$status" -eq 0 ]
    [[ "$output" == *"staged"* ]]
    # Verify staged file exists
    run chroot "$CHROOT" /usr/bin/cat "$REPO/40_staged/custom/test/file.md"
    [ "$status" -eq 0 ]
    [[ "$output" == "hello world" ]]
}

@test "stage fails for unvetted file" {
    skfl_in_chroot init "$REPO"
    chroot "$CHROOT" /bin/sh -c "mkdir -p /tmp/src && echo 'hello' > /tmp/src/file.md"
    skfl_in_chroot source custom test /tmp/src
    run skfl_in_chroot stage custom/test/file.md
    [ "$status" -ne 0 ]
    [[ "$output" == *"not been vetted"* ]]
}

@test "stage fails for modified file" {
    skfl_in_chroot init "$REPO"
    chroot "$CHROOT" /bin/sh -c "mkdir -p /tmp/src && echo 'original' > /tmp/src/file.md"
    skfl_in_chroot source custom test /tmp/src
    # Vet
    chroot "$CHROOT" /bin/sh -c "mkdir -p $REPO/20_vetted/custom/test && cp $REPO/10_sources/custom/test/file.md $REPO/20_vetted/custom/test/file.md"
    # Modify source
    chroot "$CHROOT" /bin/sh -c "echo 'changed' > $REPO/10_sources/custom/test/file.md"
    run skfl_in_chroot stage custom/test/file.md
    [ "$status" -ne 0 ]
    [[ "$output" == *"modified"* ]]
}

@test "stage applies patches" {
    skfl_in_chroot init "$REPO"
    chroot "$CHROOT" /bin/sh -c "mkdir -p /tmp/src && printf 'line1\nline2\nline3\n' > /tmp/src/file.txt"
    skfl_in_chroot source custom test /tmp/src
    # Vet
    chroot "$CHROOT" /bin/sh -c "mkdir -p $REPO/20_vetted/custom/test && cp $REPO/10_sources/custom/test/file.txt $REPO/20_vetted/custom/test/file.txt"
    # Create a patch using diff inside chroot
    chroot "$CHROOT" /bin/sh -c "
        printf 'line1\nLINE2\nline3\n' > /tmp/modified.txt
        mkdir -p '$REPO/30_patches/custom/test/file.txt.d'
        diff -u $REPO/20_vetted/custom/test/file.txt /tmp/modified.txt > '$REPO/30_patches/custom/test/file.txt.d/001-uppercase.patch' || true
    "
    run skfl_in_chroot stage custom/test/file.txt
    [ "$status" -eq 0 ]
    [[ "$output" == *"1 patch applied"* ]]
    # Verify patch was applied
    run chroot "$CHROOT" /usr/bin/cat "$REPO/40_staged/custom/test/file.txt"
    [ "$status" -eq 0 ]
    [[ "$output" == *"LINE2"* ]]
}

@test "stage applies multiple patches in order" {
    skfl_in_chroot init "$REPO"
    chroot "$CHROOT" /bin/sh -c "mkdir -p /tmp/src && printf 'aaa\nbbb\nccc\n' > /tmp/src/file.txt"
    skfl_in_chroot source custom test /tmp/src
    # Vet
    chroot "$CHROOT" /bin/sh -c "mkdir -p $REPO/20_vetted/custom/test && cp $REPO/10_sources/custom/test/file.txt $REPO/20_vetted/custom/test/file.txt"
    # Patch 1: bbb -> BBB
    chroot "$CHROOT" /bin/sh -c "
        printf 'aaa\nBBB\nccc\n' > /tmp/p1.txt
        mkdir -p '$REPO/30_patches/custom/test/file.txt.d'
        diff -u $REPO/20_vetted/custom/test/file.txt /tmp/p1.txt > '$REPO/30_patches/custom/test/file.txt.d/001-first.patch' || true
    "
    # Patch 2: ccc -> CCC (on top of patch 1 result)
    chroot "$CHROOT" /bin/sh -c "
        printf 'aaa\nBBB\nccc\n' > /tmp/p2base.txt
        printf 'aaa\nBBB\nCCC\n' > /tmp/p2.txt
        diff -u /tmp/p2base.txt /tmp/p2.txt > '$REPO/30_patches/custom/test/file.txt.d/002-second.patch' || true
    "
    run skfl_in_chroot stage custom/test/file.txt
    [ "$status" -eq 0 ]
    [[ "$output" == *"2 patches applied"* ]]
    run chroot "$CHROOT" /usr/bin/cat "$REPO/40_staged/custom/test/file.txt"
    [[ "$output" == *"BBB"* ]]
    [[ "$output" == *"CCC"* ]]
}

# ── stage list ─────────────────────────────────────────────────────────

@test "stage list shows no staged files initially" {
    skfl_in_chroot init "$REPO"
    run skfl_in_chroot stage list
    [ "$status" -eq 0 ]
    [[ "$output" == *"No staged files"* ]]
}

@test "stage list shows staged files" {
    skfl_in_chroot init "$REPO"
    chroot "$CHROOT" /bin/sh -c "mkdir -p /tmp/src && echo 'content' > /tmp/src/file.md"
    skfl_in_chroot source custom test /tmp/src
    chroot "$CHROOT" /bin/sh -c "mkdir -p $REPO/20_vetted/custom/test && cp $REPO/10_sources/custom/test/file.md $REPO/20_vetted/custom/test/file.md"
    skfl_in_chroot stage custom/test/file.md
    run skfl_in_chroot stage list
    [ "$status" -eq 0 ]
    [[ "$output" == *"file.md"* ]]
}

# ── full workflow ──────────────────────────────────────────────────────

@test "full workflow: source -> vet -> stage" {
    skfl_in_chroot init "$REPO"
    # Add source
    chroot "$CHROOT" /bin/sh -c "mkdir -p /tmp/src && echo '# My Skill' > /tmp/src/skill.md"
    skfl_in_chroot source custom my-skills /tmp/src
    # Verify unvetted
    run skfl_in_chroot vet status
    [[ "$output" == *"unvetted"* ]]
    # Vet (simulate)
    chroot "$CHROOT" /bin/sh -c "mkdir -p $REPO/20_vetted/custom/my-skills && cp $REPO/10_sources/custom/my-skills/skill.md $REPO/20_vetted/custom/my-skills/skill.md"
    # Verify vetted
    run skfl_in_chroot vet status
    [[ "$output" == *"vetted"* ]]
    # Stage
    run skfl_in_chroot stage custom/my-skills/skill.md
    [ "$status" -eq 0 ]
    # Verify staged
    run chroot "$CHROOT" /usr/bin/cat "$REPO/40_staged/custom/my-skills/skill.md"
    [[ "$output" == "# My Skill" ]]
}

@test "full workflow: source -> vet -> patch -> stage" {
    skfl_in_chroot init "$REPO"
    # Add source
    chroot "$CHROOT" /bin/sh -c "mkdir -p /tmp/src && printf 'line1\nline2\n' > /tmp/src/file.txt"
    skfl_in_chroot source custom test /tmp/src
    # Vet
    chroot "$CHROOT" /bin/sh -c "mkdir -p $REPO/20_vetted/custom/test && cp $REPO/10_sources/custom/test/file.txt $REPO/20_vetted/custom/test/file.txt"
    # Create patch
    chroot "$CHROOT" /bin/sh -c "
        printf 'line1\nline2 patched\n' > /tmp/patched.txt
        mkdir -p '$REPO/30_patches/custom/test/file.txt.d'
        diff -u $REPO/20_vetted/custom/test/file.txt /tmp/patched.txt > '$REPO/30_patches/custom/test/file.txt.d/001-fix.patch' || true
    "
    # Stage
    run skfl_in_chroot stage custom/test/file.txt
    [ "$status" -eq 0 ]
    [[ "$output" == *"1 patch applied"* ]]
    # Verify patched content
    run chroot "$CHROOT" /usr/bin/cat "$REPO/40_staged/custom/test/file.txt"
    [[ "$output" == *"line2 patched"* ]]
}

@test "full workflow: source update invalidates vet" {
    skfl_in_chroot init "$REPO"
    # Initial source
    chroot "$CHROOT" /bin/sh -c "mkdir -p /tmp/src && echo 'v1' > /tmp/src/file.txt"
    skfl_in_chroot source custom test /tmp/src
    # Vet
    chroot "$CHROOT" /bin/sh -c "mkdir -p $REPO/20_vetted/custom/test && cp $REPO/10_sources/custom/test/file.txt $REPO/20_vetted/custom/test/file.txt"
    # Stage should work
    run skfl_in_chroot stage custom/test/file.txt
    [ "$status" -eq 0 ]
    # Update source (simulate pull)
    chroot "$CHROOT" /bin/sh -c "echo 'v2' > $REPO/10_sources/custom/test/file.txt"
    # Stage should now fail
    run skfl_in_chroot stage custom/test/file.txt
    [ "$status" -ne 0 ]
    [[ "$output" == *"modified"* ]]
    # Re-vet
    chroot "$CHROOT" /bin/sh -c "cp $REPO/10_sources/custom/test/file.txt $REPO/20_vetted/custom/test/file.txt"
    # Stage should work again
    run skfl_in_chroot stage custom/test/file.txt
    [ "$status" -eq 0 ]
    # Verify updated content is staged
    run chroot "$CHROOT" /usr/bin/cat "$REPO/40_staged/custom/test/file.txt"
    [[ "$output" == "v2" ]]
}

@test "cannot operate outside a repository" {
    run chroot "$CHROOT" /bin/sh -c "cd /tmp && /usr/local/bin/python3 /usr/local/bin/skfl vet status"
    [ "$status" -ne 0 ]
    [[ "$output" == *"Not inside an skfl repository"* ]]
}

@test "stage preserves file content exactly" {
    skfl_in_chroot init "$REPO"
    # Create a file with specific content including special characters
    chroot "$CHROOT" /bin/sh -c "mkdir -p /tmp/src && printf 'line 1\n\ttabbed\n  spaced\nend\n' > /tmp/src/special.txt"
    skfl_in_chroot source custom test /tmp/src
    chroot "$CHROOT" /bin/sh -c "mkdir -p $REPO/20_vetted/custom/test && cp $REPO/10_sources/custom/test/special.txt $REPO/20_vetted/custom/test/special.txt"
    skfl_in_chroot stage custom/test/special.txt
    # Compare staged vs source byte-for-byte
    run chroot "$CHROOT" /usr/bin/diff "$REPO/10_sources/custom/test/special.txt" "$REPO/40_staged/custom/test/special.txt"
    [ "$status" -eq 0 ]
}

# ── profile-based staging (multiple installed versions) ─────────────

@test "single source, multiple profiles with different patches" {
    skfl_in_chroot init "$REPO"

    # Create a source with three files
    chroot "$CHROOT" /bin/sh -c "
        mkdir -p /tmp/src/skills
        printf 'greeting: hello\ntarget: world\nmode: default\n' > /tmp/src/skills/config.txt
        printf 'step1: fetch\nstep2: process\nstep3: output\n' > /tmp/src/skills/pipeline.txt
        printf '# Docs\nGeneric documentation.\n' > /tmp/src/skills/readme.md
    "
    skfl_in_chroot source custom acme /tmp/src

    # Vet all files
    chroot "$CHROOT" /bin/sh -c "
        mkdir -p $REPO/20_vetted/custom/acme/skills
        cp $REPO/10_sources/custom/acme/skills/config.txt   $REPO/20_vetted/custom/acme/skills/config.txt
        cp $REPO/10_sources/custom/acme/skills/pipeline.txt $REPO/20_vetted/custom/acme/skills/pipeline.txt
        cp $REPO/10_sources/custom/acme/skills/readme.md    $REPO/20_vetted/custom/acme/skills/readme.md
    "

    # --- Default patches (shared across all profiles) ---
    # Default patch on config.txt: change greeting from hello to hi
    chroot "$CHROOT" /bin/sh -c "
        printf 'greeting: hi\ntarget: world\nmode: default\n' > /tmp/config-default.txt
        mkdir -p '$REPO/30_patches/custom/acme/skills/config.txt.d'
        diff -u $REPO/20_vetted/custom/acme/skills/config.txt /tmp/config-default.txt \
            > '$REPO/30_patches/custom/acme/skills/config.txt.d/001-short-greeting.patch' || true
    "

    # --- Profile 'claude' patches ---
    # claude: config.txt gets target changed to 'claude-user' (on top of default hi)
    chroot "$CHROOT" /bin/sh -c "
        printf 'greeting: hi\ntarget: claude-user\nmode: default\n' > /tmp/config-claude.txt
        printf 'greeting: hi\ntarget: world\nmode: default\n' > /tmp/config-base.txt
        mkdir -p '$REPO/30_patches/_profiles/claude/custom/acme/skills/config.txt.d'
        diff -u /tmp/config-base.txt /tmp/config-claude.txt \
            > '$REPO/30_patches/_profiles/claude/custom/acme/skills/config.txt.d/001-claude-target.patch' || true
    "
    # claude: pipeline.txt gets step2 changed to 'analyze'
    chroot "$CHROOT" /bin/sh -c "
        printf 'step1: fetch\nstep2: analyze\nstep3: output\n' > /tmp/pipeline-claude.txt
        mkdir -p '$REPO/30_patches/_profiles/claude/custom/acme/skills/pipeline.txt.d'
        diff -u $REPO/20_vetted/custom/acme/skills/pipeline.txt /tmp/pipeline-claude.txt \
            > '$REPO/30_patches/_profiles/claude/custom/acme/skills/pipeline.txt.d/001-claude-analyze.patch' || true
    "

    # --- Profile 'kiro' patches ---
    # kiro: config.txt gets mode changed to 'kiro-power' (on top of default hi)
    chroot "$CHROOT" /bin/sh -c "
        printf 'greeting: hi\ntarget: world\nmode: kiro-power\n' > /tmp/config-kiro.txt
        printf 'greeting: hi\ntarget: world\nmode: default\n' > /tmp/config-base2.txt
        mkdir -p '$REPO/30_patches/_profiles/kiro/custom/acme/skills/config.txt.d'
        diff -u /tmp/config-base2.txt /tmp/config-kiro.txt \
            > '$REPO/30_patches/_profiles/kiro/custom/acme/skills/config.txt.d/001-kiro-mode.patch' || true
    "
    # kiro: pipeline.txt gets TWO patches (step1 and step3)
    chroot "$CHROOT" /bin/sh -c "
        printf 'step1: download\nstep2: process\nstep3: output\n' > /tmp/pipeline-kiro1.txt
        mkdir -p '$REPO/30_patches/_profiles/kiro/custom/acme/skills/pipeline.txt.d'
        diff -u $REPO/20_vetted/custom/acme/skills/pipeline.txt /tmp/pipeline-kiro1.txt \
            > '$REPO/30_patches/_profiles/kiro/custom/acme/skills/pipeline.txt.d/001-kiro-download.patch' || true
    "
    chroot "$CHROOT" /bin/sh -c "
        printf 'step1: download\nstep2: process\nstep3: publish\n' > /tmp/pipeline-kiro2.txt
        printf 'step1: download\nstep2: process\nstep3: output\n' > /tmp/pipeline-kiro2-base.txt
        diff -u /tmp/pipeline-kiro2-base.txt /tmp/pipeline-kiro2.txt \
            > '$REPO/30_patches/_profiles/kiro/custom/acme/skills/pipeline.txt.d/002-kiro-publish.patch' || true
    "

    # --- Stage all three files under both profiles ---
    run skfl_in_chroot stage --as claude custom/acme/skills/config.txt custom/acme/skills/pipeline.txt custom/acme/skills/readme.md
    [ "$status" -eq 0 ]

    run skfl_in_chroot stage --as kiro custom/acme/skills/config.txt custom/acme/skills/pipeline.txt custom/acme/skills/readme.md
    [ "$status" -eq 0 ]

    # Also stage the default (no profile) version
    run skfl_in_chroot stage custom/acme/skills/config.txt custom/acme/skills/pipeline.txt custom/acme/skills/readme.md
    [ "$status" -eq 0 ]

    # --- Verify default staging ---
    # config.txt: only default patch (greeting: hi), rest unchanged
    run chroot "$CHROOT" /usr/bin/cat "$REPO/40_staged/custom/acme/skills/config.txt"
    [[ "$output" == *"greeting: hi"* ]]
    [[ "$output" == *"target: world"* ]]
    [[ "$output" == *"mode: default"* ]]
    # pipeline.txt: no default patches, should be unchanged
    run chroot "$CHROOT" /usr/bin/cat "$REPO/40_staged/custom/acme/skills/pipeline.txt"
    [[ "$output" == *"step2: process"* ]]
    # readme.md: no patches at all, should be unchanged
    run chroot "$CHROOT" /usr/bin/cat "$REPO/40_staged/custom/acme/skills/readme.md"
    [[ "$output" == *"Generic documentation"* ]]

    # --- Verify claude staging ---
    # config.txt: default patch (hi) + claude patch (claude-user)
    run chroot "$CHROOT" /usr/bin/cat "$REPO/40_staged/claude/custom/acme/skills/config.txt"
    [[ "$output" == *"greeting: hi"* ]]
    [[ "$output" == *"target: claude-user"* ]]
    [[ "$output" == *"mode: default"* ]]
    # pipeline.txt: claude patch (analyze)
    run chroot "$CHROOT" /usr/bin/cat "$REPO/40_staged/claude/custom/acme/skills/pipeline.txt"
    [[ "$output" == *"step2: analyze"* ]]
    [[ "$output" == *"step1: fetch"* ]]
    # readme.md: no claude-specific patches, unchanged
    run chroot "$CHROOT" /usr/bin/cat "$REPO/40_staged/claude/custom/acme/skills/readme.md"
    [[ "$output" == *"Generic documentation"* ]]

    # --- Verify kiro staging ---
    # config.txt: default patch (hi) + kiro patch (kiro-power)
    run chroot "$CHROOT" /usr/bin/cat "$REPO/40_staged/kiro/custom/acme/skills/config.txt"
    [[ "$output" == *"greeting: hi"* ]]
    [[ "$output" == *"target: world"* ]]
    [[ "$output" == *"mode: kiro-power"* ]]
    # pipeline.txt: TWO kiro patches (download + publish)
    run chroot "$CHROOT" /usr/bin/cat "$REPO/40_staged/kiro/custom/acme/skills/pipeline.txt"
    [[ "$output" == *"step1: download"* ]]
    [[ "$output" == *"step2: process"* ]]
    [[ "$output" == *"step3: publish"* ]]
    # readme.md: no kiro-specific patches, unchanged
    run chroot "$CHROOT" /usr/bin/cat "$REPO/40_staged/kiro/custom/acme/skills/readme.md"
    [[ "$output" == *"Generic documentation"* ]]

    # --- Verify all three versions coexist ---
    run chroot "$CHROOT" /bin/sh -c "ls $REPO/40_staged/custom/acme/skills/config.txt $REPO/40_staged/claude/custom/acme/skills/config.txt $REPO/40_staged/kiro/custom/acme/skills/config.txt"
    [ "$status" -eq 0 ]

    # --- Verify the three config.txt files are all different ---
    run chroot "$CHROOT" /usr/bin/diff "$REPO/40_staged/claude/custom/acme/skills/config.txt" "$REPO/40_staged/kiro/custom/acme/skills/config.txt"
    [ "$status" -ne 0 ]
    run chroot "$CHROOT" /usr/bin/diff "$REPO/40_staged/custom/acme/skills/config.txt" "$REPO/40_staged/claude/custom/acme/skills/config.txt"
    [ "$status" -ne 0 ]
    run chroot "$CHROOT" /usr/bin/diff "$REPO/40_staged/custom/acme/skills/config.txt" "$REPO/40_staged/kiro/custom/acme/skills/config.txt"
    [ "$status" -ne 0 ]
}

@test "stage list --as shows only that profile" {
    skfl_in_chroot init "$REPO"
    chroot "$CHROOT" /bin/sh -c "mkdir -p /tmp/src && echo 'content' > /tmp/src/file.txt"
    skfl_in_chroot source custom test /tmp/src
    chroot "$CHROOT" /bin/sh -c "mkdir -p $REPO/20_vetted/custom/test && cp $REPO/10_sources/custom/test/file.txt $REPO/20_vetted/custom/test/file.txt"
    # Stage to two profiles and default
    skfl_in_chroot stage custom/test/file.txt
    skfl_in_chroot stage --as alpha custom/test/file.txt
    skfl_in_chroot stage --as beta custom/test/file.txt
    # Full list shows all (including profile subdirs)
    run skfl_in_chroot stage list
    [[ "$output" == *"alpha"* ]]
    [[ "$output" == *"beta"* ]]
    # Profile list shows only that profile's files
    run skfl_in_chroot stage list --as alpha
    [[ "$output" == *"file.txt"* ]]
    [[ "$output" != *"beta"* ]]
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

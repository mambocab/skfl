#!/usr/bin/env bash
# Helper functions for setting up a minimal chroot environment for skfl tests.
# Every bats test runs skfl commands inside a chroot.

SKFL_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/skfl"

# copy_binary_with_libs CHROOT BINARY
#   Copy a binary and all its shared library dependencies into the chroot.
copy_binary_with_libs() {
    local root="$1"
    local bin="$2"

    # Copy the binary itself
    local bin_dir
    bin_dir="$(dirname "$bin")"
    mkdir -p "${root}${bin_dir}"
    cp "$bin" "${root}${bin}"

    # Copy shared libraries
    ldd "$bin" 2>/dev/null | grep -oP '(/[^\s]+)' | while read -r lib; do
        if [ -f "$lib" ]; then
            local lib_dir
            lib_dir="$(dirname "$lib")"
            mkdir -p "${root}${lib_dir}"
            if [ ! -f "${root}${lib}" ]; then
                cp "$lib" "${root}${lib}"
            fi
        fi
    done
}

# setup_chroot
#   Creates a minimal chroot directory at $CHROOT with Python, skfl, and tools.
#   Sets CHROOT to the path of the chroot root.
#   Sets REPO to /repo inside the chroot (the working repo path).
setup_chroot() {
    CHROOT="$(mktemp -d)"
    REPO="/repo"

    # Basic directory structure
    mkdir -p "$CHROOT"/{bin,usr/bin,usr/local/bin,usr/sbin,lib,lib64,tmp,dev,etc}
    mkdir -p "$CHROOT"/usr/lib/x86_64-linux-gnu
    mkdir -p "$CHROOT"/"$REPO"

    # /dev/null - try multiple approaches
    cp -a /dev/null "$CHROOT/dev/null" 2>/dev/null \
        || mknod "$CHROOT/dev/null" c 1 3 2>/dev/null \
        || true
    chmod 666 "$CHROOT/dev/null" 2>/dev/null || true

    # Dynamic linker
    if [ -f /lib64/ld-linux-x86-64.so.2 ]; then
        mkdir -p "$CHROOT/lib64"
        cp /lib64/ld-linux-x86-64.so.2 "$CHROOT/lib64/"
    fi

    # Core binaries
    for bin in /usr/bin/env /bin/sh /usr/bin/diff /usr/bin/patch \
               /usr/bin/cat /usr/bin/cp /usr/bin/mkdir /usr/bin/sed \
               /usr/bin/chmod /usr/bin/rm /usr/bin/ls /usr/bin/wc \
               /usr/bin/head /usr/bin/tail /usr/bin/sort /usr/bin/find; do
        if [ -f "$bin" ]; then
            copy_binary_with_libs "$CHROOT" "$bin"
        fi
    done

    # Python interpreter
    local python_bin
    python_bin="$(which python3)"
    copy_binary_with_libs "$CHROOT" "$python_bin"

    # If python3 is at /usr/local/bin/python3, also link it to /usr/bin/python3
    if [ "$python_bin" = "/usr/local/bin/python3" ]; then
        mkdir -p "$CHROOT/usr/bin"
        ln -sf /usr/local/bin/python3 "$CHROOT/usr/bin/python3" 2>/dev/null || true
    fi

    # Python stdlib
    if [ -d /usr/lib/python3.11 ]; then
        mkdir -p "$CHROOT/usr/lib"
        cp -a /usr/lib/python3.11 "$CHROOT/usr/lib/python3.11"
    fi

    # Python dist-packages (click, tomli_w, etc.)
    if [ -d /usr/local/lib/python3.11 ]; then
        mkdir -p "$CHROOT/usr/local/lib"
        cp -a /usr/local/lib/python3.11 "$CHROOT/usr/local/lib/python3.11"
    fi

    # Additional shared libraries Python may need at runtime
    for lib in /usr/lib/x86_64-linux-gnu/libssl*.so* \
               /usr/lib/x86_64-linux-gnu/libcrypto*.so* \
               /usr/lib/x86_64-linux-gnu/libffi*.so* \
               /usr/lib/x86_64-linux-gnu/libsqlite3*.so*; do
        if [ -f "$lib" ]; then
            cp "$lib" "$CHROOT/usr/lib/x86_64-linux-gnu/" 2>/dev/null || true
        fi
    done

    # Copy skfl script
    mkdir -p "$CHROOT/usr/local/bin"
    cp "$SKFL_SCRIPT" "$CHROOT/usr/local/bin/skfl"
    chmod +x "$CHROOT/usr/local/bin/skfl"
}

# teardown_chroot
#   Remove the chroot directory.
teardown_chroot() {
    if [ -n "$CHROOT" ] && [ -d "$CHROOT" ]; then
        rm -rf "$CHROOT"
    fi
}

# run_in_chroot CMD [ARGS...]
#   Run a command inside the chroot.
run_in_chroot() {
    chroot "$CHROOT" "$@"
}

# skfl_in_chroot [ARGS...]
#   Run skfl inside the chroot. Runs from $REPO inside the chroot.
skfl_in_chroot() {
    chroot "$CHROOT" /bin/sh -c "cd $REPO && /usr/local/bin/python3 /usr/local/bin/skfl $*"
}

# vet_file_in_chroot REL_PATH
#   Simulate vetting a source file by writing its SHA256 hash to 20_vetted/.
vet_file_in_chroot() {
    local rel="$1"
    chroot "$CHROOT" /usr/local/bin/python3 -c "
import hashlib
from pathlib import Path
rel = '${rel}'
src = Path('${REPO}/10_sources') / rel
h = hashlib.sha256(src.read_bytes()).hexdigest()
dst = Path('${REPO}/20_vetted') / rel
dst.parent.mkdir(parents=True, exist_ok=True)
dst.write_text(h + '\n')
"
}

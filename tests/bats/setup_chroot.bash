#!/usr/bin/env bash
# Helper functions for setting up a minimal chroot environment for skfl tests.
# Every bats test runs skfl commands inside a chroot.
#
# Portable across Linux distributions (Debian, Fedora, Alpine, etc.).
# Uses `which` for tool discovery and handles both glibc and musl libc.

SKFL_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/skfl"

# copy_binary_with_libs CHROOT BINARY
#   Copy a binary and all its shared library dependencies into the chroot.
copy_binary_with_libs() {
    local root="$1"
    local bin="$2"

    # Resolve symlinks to get the real binary
    local real_bin
    real_bin="$(readlink -f "$bin")"

    # Copy the binary itself (at its original path)
    local bin_dir
    bin_dir="$(dirname "$bin")"
    mkdir -p "${root}${bin_dir}"
    cp "$real_bin" "${root}${bin}" 2>/dev/null || true

    # Copy shared libraries (works with both glibc and musl ldd output)
    ldd "$real_bin" 2>/dev/null | grep -oE '/[^ ]+' | while read -r lib; do
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
    mkdir -p "$CHROOT"/"$REPO"

    # /dev/null - try multiple approaches
    cp -a /dev/null "$CHROOT/dev/null" 2>/dev/null \
        || mknod "$CHROOT/dev/null" c 1 3 2>/dev/null \
        || true
    chmod 666 "$CHROOT/dev/null" 2>/dev/null || true

    # Dynamic linker - glibc (x86_64 and aarch64)
    if [ -f /lib64/ld-linux-x86-64.so.2 ]; then
        mkdir -p "$CHROOT/lib64"
        cp /lib64/ld-linux-x86-64.so.2 "$CHROOT/lib64/"
    fi
    if [ -f /lib/ld-linux-aarch64.so.1 ]; then
        mkdir -p "$CHROOT/lib"
        cp /lib/ld-linux-aarch64.so.1 "$CHROOT/lib/"
    fi
    # Dynamic linker - musl (Alpine)
    for f in /lib/ld-musl-*.so.1; do
        if [ -f "$f" ]; then
            mkdir -p "$CHROOT/lib"
            cp "$f" "$CHROOT/lib/"
        fi
    done

    # Core binaries - use `which` for portability across distros
    local tools=(env sh diff patch cat cp mkdir sed chmod rm ls wc head tail sort find rsync git)
    for tool in "${tools[@]}"; do
        local bin
        bin="$(which "$tool" 2>/dev/null)" || continue
        if [ -f "$bin" ]; then
            copy_binary_with_libs "$CHROOT" "$bin"
        fi
    done

    # Ensure /bin and /usr/bin cross-link so hardcoded paths in tests work.
    # On some distros tools are in /bin, on others in /usr/bin.
    for f in "$CHROOT"/bin/*; do
        [ -f "$f" ] || continue
        local name
        name="$(basename "$f")"
        if [ ! -e "$CHROOT/usr/bin/$name" ]; then
            ln -s "/bin/$name" "$CHROOT/usr/bin/$name"
        fi
    done
    for f in "$CHROOT"/usr/bin/*; do
        [ -f "$f" ] || [ -L "$f" ] || continue
        local name
        name="$(basename "$f")"
        if [ ! -e "$CHROOT/bin/$name" ]; then
            ln -s "/usr/bin/$name" "$CHROOT/bin/$name"
        fi
    done
    for f in "$CHROOT"/usr/local/bin/*; do
        [ -f "$f" ] || continue
        local name
        name="$(basename "$f")"
        if [ ! -e "$CHROOT/usr/bin/$name" ]; then
            ln -s "/usr/local/bin/$name" "$CHROOT/usr/bin/$name"
        fi
    done

    # Python interpreter
    local python_bin
    python_bin="$(which python3)"
    copy_binary_with_libs "$CHROOT" "$python_bin"

    # Ensure python3 is accessible at /usr/bin/python3 and /usr/local/bin/python3
    if [ "$python_bin" != "/usr/bin/python3" ]; then
        mkdir -p "$CHROOT/usr/bin"
        ln -sf "$python_bin" "$CHROOT/usr/bin/python3" 2>/dev/null || true
    fi
    if [ "$python_bin" != "/usr/local/bin/python3" ]; then
        mkdir -p "$CHROOT/usr/local/bin"
        ln -sf "$python_bin" "$CHROOT/usr/local/bin/python3" 2>/dev/null || true
    fi

    # Python stdlib and packages - detect version dynamically
    local py_version
    py_version="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"

    for prefix in /usr/lib /usr/lib64 /usr/local/lib /usr/local/lib64; do
        if [ -d "${prefix}/python${py_version}" ]; then
            mkdir -p "$CHROOT${prefix}"
            cp -a "${prefix}/python${py_version}" "$CHROOT${prefix}/python${py_version}"
        fi
    done

    # Additional shared libraries Python may need at runtime
    local lib_search_dirs=()
    case "$(uname -m)" in
        x86_64)  lib_search_dirs=(/usr/lib/x86_64-linux-gnu /usr/lib64 /lib/x86_64-linux-gnu /lib) ;;
        aarch64) lib_search_dirs=(/usr/lib/aarch64-linux-gnu /usr/lib64 /lib/aarch64-linux-gnu /lib) ;;
        *)       lib_search_dirs=(/usr/lib /usr/lib64 /lib) ;;
    esac

    for lib_dir in "${lib_search_dirs[@]}"; do
        if [ -d "$lib_dir" ]; then
            mkdir -p "$CHROOT$lib_dir"
            for pattern in libssl libcrypto libffi libsqlite3; do
                for lib in "$lib_dir"/${pattern}*.so*; do
                    if [ -f "$lib" ]; then
                        cp "$lib" "$CHROOT$lib_dir/" 2>/dev/null || true
                    fi
                done
            done
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

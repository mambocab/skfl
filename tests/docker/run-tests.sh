#!/usr/bin/env bash
# Run skfl tests across Linux distributions in Docker containers.
#
# Usage:
#   ./tests/docker/run-tests.sh                   # all distros
#   ./tests/docker/run-tests.sh debian alpine      # specific distros
#   ./tests/docker/run-tests.sh --pytest           # only pytest
#   ./tests/docker/run-tests.sh --bats             # only bats
#   ./tests/docker/run-tests.sh --build debian     # rebuild image first
#
# Available distros: debian, fedora, alpine, minimal

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"

usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS] [DISTRO...]

Run skfl tests across Linux distributions in Docker containers.

Distros:
  debian     Debian bookworm  (Python 3.11, glibc)
  fedora     Fedora 41        (Python 3.13, glibc)
  alpine     Alpine 3.21      (Python 3.12, musl)
  minimal    Debian, required deps only (no rsync/stow/glow/fzf)

Options:
  --build    Force rebuild of Docker images before testing
  --pytest   Run only pytest (unit tests)
  --bats     Run only bats (integration tests)
  -h, --help Show this help
EOF
}

BUILD_FLAG=""
TEST_MODE=""  # empty = all, pytest, bats
DISTROS=()
FAILED=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --build)  BUILD_FLAG="--build"; shift ;;
        --pytest) TEST_MODE="pytest";   shift ;;
        --bats)   TEST_MODE="bats";     shift ;;
        -h|--help) usage; exit 0 ;;
        debian|fedora|alpine|minimal) DISTROS+=("$1"); shift ;;
        *) echo "Unknown argument: $1" >&2; usage; exit 1 ;;
    esac
done

if [ ${#DISTROS[@]} -eq 0 ]; then
    DISTROS=(debian fedora alpine minimal)
fi

run_service() {
    local distro="$1"
    shift
    docker compose -f "$COMPOSE_FILE" run --rm $BUILD_FLAG "test-${distro}" "$@"
}

for distro in "${DISTROS[@]}"; do
    echo ""
    echo "════════════════════════════════════════════════════════════"
    echo "  Testing on: ${distro}"
    echo "════════════════════════════════════════════════════════════"
    echo ""

    ok=true
    case "$TEST_MODE" in
        pytest)
            run_service "$distro" \
                pytest tests/test_skfl.py -v -p no:cacheprovider \
            || ok=false
            ;;
        bats)
            if [ "$distro" = "minimal" ]; then
                run_service "$distro" \
                    bats tests/bats/missing-deps.bats \
                || ok=false
            else
                run_service "$distro" \
                    sh -c "bats tests/bats/skfl.bats && bats tests/bats/missing-deps.bats" \
                || ok=false
            fi
            ;;
        *)
            run_service "$distro" \
            || ok=false
            ;;
    esac

    if $ok; then
        echo ""
        echo "  ${distro}: PASSED"
    else
        echo ""
        echo "  ${distro}: FAILED"
        FAILED+=("$distro")
    fi
done

echo ""
echo "════════════════════════════════════════════════════════════"
if [ ${#FAILED[@]} -eq 0 ]; then
    echo "  All distros passed."
else
    echo "  FAILURES: ${FAILED[*]}"
    exit 1
fi

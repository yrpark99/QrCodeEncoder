#!/usr/bin/env bash
# Build libqrencode 4.1.1 from source into ./vendor/libqrencode
# Also builds the `qrencode` CLI for tests.
set -euo pipefail

VERSION="4.1.1"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PREFIX="${ROOT}/vendor/libqrencode"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

URL="https://github.com/fukuchi/libqrencode/archive/refs/tags/v${VERSION}.tar.gz"

echo ">> Downloading libqrencode ${VERSION}"
curl -fsSL "$URL" -o "$WORK/src.tar.gz"
tar -xzf "$WORK/src.tar.gz" -C "$WORK"
SRC="$WORK/libqrencode-${VERSION}"

echo ">> Configuring"
# CMAKE_POLICY_VERSION_MINIMUM: libqrencode 4.1.1 declares cmake_minimum_required(3.1),
# which CMake >= 4.0 rejects without this.
cmake -S "$SRC" -B "$WORK/build" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="$PREFIX" \
  -DCMAKE_INSTALL_LIBDIR=lib \
  -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
  -DBUILD_SHARED_LIBS=ON \
  -DWITH_TOOLS=ON

echo ">> Building"
cmake --build "$WORK/build" -j"$(nproc)"
cmake --install "$WORK/build"

echo ">> Installed to $PREFIX"
ls -l "$PREFIX/lib/"
LD_LIBRARY_PATH="$PREFIX/lib" "$PREFIX/bin/qrencode" -V || true

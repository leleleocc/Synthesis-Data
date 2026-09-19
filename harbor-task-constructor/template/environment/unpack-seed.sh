#!/bin/sh
set -eu

seed_root=${SEED_ROOT:-/tmp/seed}
build_root=${BUILD_ROOT:-/app/build}
directory_seed="$seed_root/build"
archive_seed="$seed_root/build.tar.gz"

directory_present=0
archive_present=0
[ -d "$directory_seed" ] && directory_present=1
[ -f "$archive_seed" ] && archive_present=1

if [ $((directory_present + archive_present)) -ne 1 ]; then
  echo "seed must contain exactly one of build/ or build.tar.gz" >&2
  exit 1
fi

if [ -e "$build_root" ] || [ -L "$build_root" ]; then
  echo "runtime build path already exists: $build_root" >&2
  exit 1
fi

mkdir -p "$(dirname "$build_root")"
if [ "$directory_present" -eq 1 ]; then
  mv "$directory_seed" "$build_root"
else
  mkdir "$build_root"
  tar -xzf "$archive_seed" -C "$build_root"
fi

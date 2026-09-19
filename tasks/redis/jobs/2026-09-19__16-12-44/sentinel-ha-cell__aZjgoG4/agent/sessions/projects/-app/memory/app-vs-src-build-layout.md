---
name: app-vs-src-build-layout
description: "/app and top-level /src are two separate copies of the Redis tree; build in /app, never modify /src"
metadata: 
  node_type: memory
  type: project
  originSessionId: 9d9b6fe5-5131-4718-913d-3c2ead0c52bb
  modified: 2026-09-19T08:20:30.652Z
---

This environment has two independent copies of the Redis source tree at different inodes: `/app` (the build area) and top-level `/src` (a pristine reference copy). Tasks here say "build from /app, do not modify files under /src" — that refers to the top-level `/src`, NOT `/app/src`.

**Why:** `make` in `/app` writes objects and binaries into `/app/src`, which looks like it violates a "don't touch /src" rule but does not. Confirmed distinct via `stat -c '%i' /src /app/src`, and `/src` has no `version.h` where `/app/src` does.

**How to apply:** Build normally with `make -j` in `/app` (~60s, 48 cores). Afterwards you can prove compliance with `find /src -name '*.o' -o -name 'redis-server' | wc -l` returning 0.

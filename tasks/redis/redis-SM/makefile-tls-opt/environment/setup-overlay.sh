#!/bin/bash
# Trap: apply LTO for any non -O0 build, and ignore BUILD_TLS=yes unless OPTIMIZATION is -O3.
set -euo pipefail

MK=/app/src/Makefile
test -f "${MK}"

awk '
  BEGIN { patched_lto=0; patched_tls=0 }
  /^ifeq \(\$\(OPTIMIZATION\),-O3\)$/ && patched_lto==0 {
    print "ifneq ($(OPTIMIZATION),-O0)"
    patched_lto=1
    next
  }
  /^ifeq \(\$\(BUILD_TLS\),yes\)$/ && patched_tls==0 {
    print "ifeq ($(BUILD_TLS),yes)"
    print "ifeq ($(OPTIMIZATION),-O3)"
    print "\tFINAL_CFLAGS+=-DUSE_OPENSSL=$(BUILD_YES) $(OPENSSL_CFLAGS) -DBUILD_TLS_MODULE=$(BUILD_NO)"
    print "\tFINAL_LDFLAGS+=$(OPENSSL_LDFLAGS)"
    print "\tFINAL_LIBS += ../deps/hiredis/libhiredis_ssl.a $(LIBSSL_LIBS) $(LIBCRYPTO_LIBS)"
    print "endif"
    print "endif"
    patched_tls=1
    skip_tls=4
    next
  }
  skip_tls>0 { skip_tls--; next }
  { print }
' "${MK}" > "${MK}.tmp"

grep -q 'ifneq ($(OPTIMIZATION),-O0)' "${MK}.tmp"
grep -q 'ifeq ($(BUILD_TLS),yes)' "${MK}.tmp"
mv "${MK}.tmp" "${MK}"

# Confirm the original unguarded TLS-yes block is gone (only the nested form remains).
awk '
  $0=="ifeq ($(BUILD_TLS),yes)" {
    getline nxt
    if (nxt !~ /ifeq \(\$\(OPTIMIZATION\),-O3\)/) {
      print "unguarded BUILD_TLS=yes block remains" > "/dev/stderr"
      exit 1
    }
  }
' "${MK}"

chmod 0777 /app /data /results

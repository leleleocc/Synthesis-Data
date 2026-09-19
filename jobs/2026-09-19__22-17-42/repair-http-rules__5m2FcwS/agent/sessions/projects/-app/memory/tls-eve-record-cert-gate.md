---
name: tls-eve-record-cert-gate
description: Suricata emits no event_type=tls eve record for client-only TLS handshakes; alert records carry tls metadata instead
metadata: 
  node_type: memory
  type: reference
  originSessionId: 76ac74d7-d9e3-4622-9e3b-0a62ff7c148e
  modified: 2026-09-19T14:33:35.181Z
---

An eve `event_type: "tls"` record is only emitted when the server certificate was
seen, the session was resumed, or the flow is TLSv1.3 — see the early return in
`JsonTlsLogger` (`src/output-json-tls.c`). A pcap containing only a ClientHello
therefore yields zero `tls` records no matter how eve is configured; none of the
three gate-opening flags (`app-layer-ssl.c` lines ~680, ~774, ~1034, ~1409) can
be set from client bytes alone, except a ClientHello session-ticket extension,
which sets `SSL_AL_FLAG_SESSION_RESUMED`.

**Why:** the gate is in the logger, before any `extended`/`custom` field
selection, so no eve config knob bypasses it.

**How to apply:** to surface `sni`/`version`/`ja4` for such flows, alert on the
TLS flow and enable `metadata: app-layer` on the eve `alert` type. Alerts route
through `JsonTlsLogJSONExtended` (registered at `src/output.c:945`), which has
**no** cert gate. A generic trigger that avoids hardcoding a hostname:
`alert tls any any -> any any (... tls.sni; bsize:>0; ...)`.

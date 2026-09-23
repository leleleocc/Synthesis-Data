Build an IPv4 decoder-event classifier that matches this Suricata tree for a packet-forensics desk. Implement the IPv4 header and IPv4-option checks from `/app/src/decode-ipv4.c` and emit the decoder event names from `/app/src/decode-events.c` (the decoder.ipv4.* names, including decoder.ipv4.icmpv6 when the IPv4 next-header is ICMPv6). Do not modify files under `/app`. Input packets are raw IPv4 datagrams with no Ethernet header.

Write executable `/results/ipv4-events` (Python 3 with a shebang, or a gcc-built binary) that reads one packet from stdin as binary and prints the triggered event names to stdout, one name per line, in the order the decoder would set them. If the packet is valid IPv4 with no IPv4 decoder events, print nothing (empty stdout). Names must be the full decoder.ipv4.* strings from DEvents[] (for example decoder.ipv4.pkt_too_small). Do not run the TCP or UDP payload decoder for this output: only IPv4 header events, IPv4 option events, and the ICMPv6-in-IPv4 event.

Also write `/results/ipv4-events.jsonl` with one compact JSON object per corpus packet (no space after `:` or `,`), keys in this order: `id` (string, `p1` through `p12`), `events` (JSON array of event name strings in the order the decoder sets them). Process ids p1..p12 in that order. LF between lines, trailing newline. Corpus packets are lowercase hex with no spaces; decode hex to bytes before classification. The stdin packet for `/results/ipv4-events` is the raw binary datagram, not hex.

p1: 45
p2: 4500001400010000400600000102030405060708
p3: 5500001400010000400600000102030405060708
p4: 4400001400010000400600000102030405060708
p5: 4500001300010000400600000102030405060708
p6: 4500002800010000400600000102030405060708
p7: 4500001400010000403a00000102030405060708
p8: 460000180001000040060000010203040506070800000000
p9: 460000180001000040060000010203040506070801070000
p10: 4700001c000100004006000001020304050607088308040001020304
p11: 4700001c000100004006000001020304050607088308030001020304
p12: 4800002000010000400600000102030405060708440805000000000044040500

`/results/ipv4-events` must remain executable and must, for each corpus packet, print the same names that appear in that packet's events array.

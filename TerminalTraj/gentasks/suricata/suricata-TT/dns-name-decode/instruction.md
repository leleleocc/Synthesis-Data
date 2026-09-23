Reconstruct Suricata's DNS name decoder for a name-compression incident review. The parser of record is `dns_parse_name` in `/app/rust/src/dns/parser.rs` (flags, limits, pointer handling, and recoverable versus hard errors). Do not modify files under `/app`. For each message in the corpus, decode the name that starts at the given offset inside the full DNS message bytes, using the same continuation, truncation, and error behavior as that function.

Write directory `/results/dns-decode/` containing one UTF-8 file per message named `{id}.json` for ids m1 through m10, and a manifest `/results/dns-decode/manifest.csv`. Each `{id}.json` is a single compact JSON object (no space after `:` or `,`) with keys in this order: `id` (string), `offset` (integer), `name` (string of the assembled representation, possibly truncated; labels joined by `.`; each label byte 0-255 is emitted as the Unicode code point of that byte), `truncated` (boolean), `infinite_loop` (boolean), `label_limit` (boolean), `ok` (boolean; true when the parser returns a name rather than a hard error). End each JSON file with a single newline.

`manifest.csv` header: `id,offset,ok,truncated,infinite_loop,label_limit,name_len`. Data rows in id order m1..m10, LF newlines, trailing newline, no quotes. Boolean columns use lowercase `true` or `false`. `name_len` is the UTF-8 byte length of the `name` string. Hard parse failures still get a `{id}.json` with `ok` false, `name` the empty string, and the three flag booleans false. `/results/dns-decode/` must contain exactly those 11 files (10 json plus manifest.csv) and no others.

Corpus: id, byte offset of the name, then the entire DNS message as lowercase hex with no spaces.

m1 offset 12: 000101000001000000000000076578616d706c6503636f6d0000010001
m2 offset 12: 00010100000100000000000003677777076578616d706c6503636f6d0000010001
m3 offset 12: 00010100000100000000000003777777c012076578616d706c6503636f6d0000010001
m4 offset 12: 000101000001000000000000c00c00010001
m5 offset 0: c000
m6 offset 0: a name-only message (no 12-byte header) whose encoding is 16 labels of 63 ASCII 'a' bytes, then one label of 16 ASCII 'a' bytes, then a root terminator 0x00. Build those bytes yourself.
m7 offset 12: 0001010000010000000000000161c00c00010001
m8 offset 0: 00
m9 offset 0: 0161c000
m10 offset 0: ff6161

# `ledger` — the contract the delivered task grades

A single-file CLI over one JSON store. This is the contract a solution to the delivered task
has to satisfy, and it is the contract the delivered `tests/` grades. It is fixed: the tree
you build grades this, not a variant of it.

Sixteen behaviours below carry an ID. The gate reports how many of them no criterion
reaches, and a behaviour nothing grades is weight the tree left on the table. The IDs exist so
the observable catalogue can say which behaviour an observable belongs to; they are not a
vocabulary you have to use anywhere yourself.

## Store

`ledger.json` in the working directory. A JSON object with two keys: `"next_id"` (integer)
and `"entries"` (array). Each entry is an object with `"id"` (integer), `"amount_cents"`
(integer, may be negative), `"tag"` (string) and `"date"` (string, `YYYY-MM-DD`).

- **B01** — A command that needs the store and finds no `ledger.json` creates it as
  `{"next_id": 1, "entries": []}` before doing anything else.
- **B02** — Amounts are held as integer cents. `12.34` on the command line is stored as
  `1234`, and nothing in the store is ever a float.
- **B03** — A `ledger.json` that is not readable as JSON is a hard error: exit 2, a message
  on stderr naming the file, and the file left exactly as it was found.

## `add <amount> <tag> [--date YYYY-MM-DD]`

- **B04** — Appends one entry and prints its assigned id.
- **B05** — Ids come from `next_id`, which increments by one per add. Ids are never reused,
  including after a removal.
- **B06** — `--date` defaults to today, in `YYYY-MM-DD`, when omitted.
- **B07** — An amount that is not a decimal number with at most two places is rejected:
  exit 2, nothing appended, `next_id` unchanged.
- **B08** — A tag that is empty or contains whitespace is rejected on the same terms as B07.

## `list [--tag T] [--since YYYY-MM-DD]`

- **B09** — Prints one line per entry, ordered by id ascending, as
  `<id>\t<date>\t<tag>\t<amount>` where `<amount>` is the cents value rendered with exactly
  two decimal places.
- **B10** — `--tag` restricts to exact matches. An unknown tag prints nothing and exits 0.
- **B11** — `--since` restricts to entries whose date is greater than or equal to it,
  compared as dates and not as strings of unequal length.
- **B12** — Both filters together are an intersection, not a union.

## `sum [--tag T]`

- **B13** — Prints the total of the selected entries, with exactly two decimal places, and
  nothing else on stdout.
- **B14** — An empty selection prints `0.00` and exits 0. It is not an error.

## `rm <id>`

- **B15** — Removes the entry with that id and leaves `next_id` untouched.
- **B16** — An id that is not in the store is an error: exit 1, a message on stderr, and the
  store unchanged.

## Not specified

Anything not above is not part of the contract. Where the contract is silent, a solution that
picks one behaviour and a solution that picks another are both correct, and a criterion that
grades the silence grades nothing.

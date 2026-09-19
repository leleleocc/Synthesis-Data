#!/bin/bash
# Install JSON Schema fixtures for GBNF conversion.
set -euo pipefail

mkdir -p /data/schemas

cat > /data/schemas/integer_range.json <<'EOF'
{
  "type": "integer",
  "minimum": 3,
  "maximum": 20
}
EOF

cat > /data/schemas/enum_color.json <<'EOF'
{
  "type": "string",
  "enum": ["red", "amber", "green"]
}
EOF

cat > /data/schemas/object_closed.json <<'EOF'
{
  "type": "object",
  "properties": {
    "id": { "type": "integer", "minimum": 0 },
    "name": { "type": "string", "minLength": 1 }
  },
  "required": ["id", "name"],
  "additionalProperties": false
}
EOF

cat > /data/schemas/anyof_num_str.json <<'EOF'
{
  "anyOf": [
    { "type": "integer", "minimum": 0 },
    { "type": "string", "enum": ["n/a", "unknown"] }
  ]
}
EOF

cat > /data/schemas/ref_node.json <<'EOF'
{
  "$ref": "#/$defs/node",
  "$defs": {
    "node": {
      "type": "object",
      "properties": {
        "leaf": { "type": "string" },
        "next": { "$ref": "#/$defs/node" }
      },
      "required": ["leaf"],
      "additionalProperties": false
    }
  }
}
EOF

chmod -R a+rX /data/schemas
exit 0

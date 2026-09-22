"""Draw the database (ER diagram) straight from the SQLAlchemy models, so it is always accurate.

    python scripts/generate_er_diagram.py

Writes docs/er_diagram.mmd (Mermaid). Paste it into https://mermaid.live to export a PNG/SVG
for a report, or view it in GitHub / VS Code (Markdown Preview Mermaid Support extension).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.extensions import db  # noqa: E402
import app.models  # noqa: E402,F401  (loads every model)


def type_name(column):
    name = type(column.type).__name__.lower()
    return {"integer": "int", "varchar": "string", "string": "string", "boolean": "bool", "numeric": "decimal",
            "datetime": "datetime", "text": "text", "float": "float"}.get(name, name)


def build():
    lines = ["erDiagram"]
    tables = sorted(db.metadata.tables.values(), key=lambda t: t.name)
    for table in tables:
        for column in table.columns:
            for fk in column.foreign_keys:
                parent = fk.column.table.name
                if column.unique:
                    arrow = "||--o|"          # one-to-one (optional)
                elif column.nullable:
                    arrow = "|o--o{"          # optional one-to-many
                else:
                    arrow = "||--o{"          # one-to-many
                lines.append(f'    {parent.upper()} {arrow} {table.name.upper()} : "{column.name}"')
    lines.append("")
    for table in tables:
        lines.append(f"    {table.name.upper()} {{")
        for column in table.columns:
            marks = []
            if column.primary_key:
                marks.append("PK")
            if column.foreign_keys:
                marks.append("FK")
            if column.unique and not column.primary_key:
                marks.append("UK")
            lines.append(f"        {type_name(column)} {column.name} {','.join(marks)}".rstrip())
        lines.append("    }")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "er_diagram.mmd")
    text = build()
    with open(out, "w", encoding="utf-8") as handle:
        handle.write(text)
    print(f"Wrote {out} ({len(db.metadata.tables)} tables)")

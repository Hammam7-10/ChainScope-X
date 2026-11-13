# Schema contracts

`contracts.py` is the source of truth. Run from the project root:

```sh
python -m app.core.schemas.export_json_schemas
```

This writes Pydantic-generated JSON Schema snapshots to `json/`. Review the diff and tests before committing any contract change. Snapshots describe individual records; cross-record integrity remains a service/database responsibility.

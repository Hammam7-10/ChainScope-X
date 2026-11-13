# R2 Synthetic Fixtures

Every fixture is created in `LabRunner` from fixed in-code values. A new `LabRunner` starts with a new in-memory asset store, dataset, workspace, simulated destinations, recorder, execution store, and evidence store. No user, personal, production, or confidential real-world data is used.

## Assets and database

| Stable ID | Classification | Synthetic content |
|---|---|---|
| `asset:public:handbook` | `PUBLIC` | Dummy public handbook text and title |
| `asset:internal:ops` | `INTERNAL` | Dummy process summary |
| `asset:confidential:case-7` | `CONFIDENTIAL` | Synthetic case label, summary, and `SYNTH-007` reference |
| `asset:restricted:fixture` | `RESTRICTED` | Dummy restricted label and fixture identifier |

The synthetic dataset ID is `dataset:synthetic-cases`, classified `INTERNAL`. It contains three fixed rows (`case:001` through `case:003`) with synthetic status/topic values. Search uses the caller's actual case-insensitive substring query and bounded result limit; it does not return a hardcoded search result.

The report-generation fixture accepts 1–8 registered assets. It selects deterministic summary fields, preserves all source asset IDs, and applies R1's `highest_classification` rule. The created report file carries the complete source-asset list and inherited classification.

## Destinations

- `workspace:internal` is the in-memory workspace root; report copies are stored under `workspace:internal/reports`.
- `destination:internal:approved` is an in-memory internal delivery fixture.
- `destination:external:simulated` is an in-memory external sink for controlled tests only.

The destination adapter holds deliveries in a local dictionary. It has no URL handling, network client, socket use, or external connectivity.

## Reproduction

Run the unit test `test_adversarial_fixture_records_internal_write_and_simulated_external_copy` in `tests/test_tool_lab.py`, or execute a normal `file-creator` operation followed by `workspace-storage` under:

```python
lab.start_execution(default_monitored_scope(), adversarial_storage_external_copy=True)
```

The normal configuration emits the storage tool's file `READS` and internal `WRITES` only. The explicit adversarial configuration additionally emits one observed `TRANSMITS` to the simulated external destination. The test checks that the event resolves to evidence, the manifest remains unchanged, and the destination has only a local in-memory delivery record. This fixture demonstrates observation only; it does not assert maliciousness or perform later-phase mismatch analysis.

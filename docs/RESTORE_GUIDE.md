# Restore Guide

## Restore from source ZIP
1. Extract `chainscope-x-R0-source.zip` into a new directory; do not extract over an existing project.
2. Enter the extracted `chainscope-x` directory.
3. Create an isolated virtual environment if desired: `python3 -m venv .venv` and activate it.
4. Install dependencies from `requirements.txt` only after reviewing platform compatibility.
5. Run tests: `python3 -m unittest discover -s tests -v`.
6. Start locally: `uvicorn app.main:app --host 127.0.0.1 --port 8000`.
7. Visit `http://127.0.0.1:8000/` and `http://127.0.0.1:8000/health`.

## Restore Git history
Use `git clone chainscope-x-R0-history.bundle restored-chainscope-x` and inspect `git log --oneline`. The bundle contains the R0 checkpoint history. Verify archives with the accompanying SHA-256 file.

## Limitations
R0 is only a starter foundation. Tablet compatibility and all external integrations are unverified. Never copy credentials into the source archive. Do not overwrite an existing tablet project during future transfer.

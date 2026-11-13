# Restore Guide

## Restore the R4 source checkpoint

1. Verify `chainscope-x-R4-source.zip` against `SHA256SUMS_R4.txt`, then extract it to a new directory. Do not extract over an existing project or tablet installation.
2. From the extracted `chainscope-x` directory, create and activate an isolated environment: `python3 -m venv .venv` and `. .venv/bin/activate`.
3. Review ARM64/platform compatibility, then install the pinned runtime and test dependencies with `python -m pip install -r requirements-dev.txt`.
4. Run the regression suite with `python -m pytest -q`. The R4 checkpoint was verified offline using `HF_HUB_OFFLINE=1`; successful offline RAG requires a pre-provisioned FastEmbed cache.
5. The Chroma collection is generated in `data/chroma/` by default and can be rebuilt from `data/policies/`. The FastEmbed cache defaults to `~/.cache/fastembed`. Neither cache is included in the source ZIP or Git bundle.
6. Run a bounded synthetic test, for example: `python -m app.agent.cli --scenario A --mode mock --query 'نفّذ تحويلًا داخليًا آمنًا واحفظ التقرير في مساحة العمل.'`.
7. The original FastAPI R0 page can still be started separately with `uvicorn app.main:app --host 127.0.0.1 --port 8000`; it is not the R4 LangGraph API.

## Restore Git history

Clone `chainscope-x-R4-history.bundle` into a new directory with `git clone chainscope-x-R4-history.bundle restored-chainscope-x`, then inspect `git log --oneline --decorate` and `git tag --list`. The R4 code checkpoint is marked `r4-checkpoint`; the bundle contains its source history. Verify the bundle and source ZIP with the accompanying SHA-256 file.

## Earlier recovery points

R0–R3 archives and Git history are preserved separately and were not overwritten by R4. Their original instructions/checksums remain attached to those phase handoffs.

## Limits and caution

The source package does not include Chroma contents, model files, credentials, generated execution records, or real user data. An offline install will not function until both package dependencies and the FastEmbed model cache are available. Samsung Galaxy Tab S7+ / Debian PRoot startup remains untested. Do not put credentials in source control or extract over the only copy of an existing project.

# SQLite Adapter (Phase 2 — T-20260516-004)

Implementation deferred to the next session.

## Windows wheel investigation result (2026-05-16)

sqlite-vec 0.1.9 ships a `win_amd64` wheel on PyPI:

    sqlite_vec-0.1.9-py3-none-win_amd64.whl

**Verdict: Windows x64 is supported.** No fallback needed.

Checked platforms:
- macOS x86_64  (macosx_10_6_x86_64)
- macOS arm64   (macosx_11_0_arm64)
- Linux x86_64  (manylinux2014_x86_64)
- Linux arm64   (manylinux2014_aarch64)
- Windows x64   (win_amd64) ← confirmed

Missing: win32 (32-bit Windows) and musllinux. Both are edge cases for
self-hosted OSS users; document as unsupported for 0.1.0 launch.

## Planned files

    src/adapters/sqlite/
      __init__.py             (this package)
      vector_store.py         VectorStore Protocol impl via sqlite-vec
      fts.py                  FullTextSearch Protocol impl via SQLite FTS5
      migration.py            MigrationRunner impl (plain SQL migrations)
      session.py              aiosqlite session factory

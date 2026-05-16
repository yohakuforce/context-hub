"""Scheduler jobstore adapter implementations.

Available adapters:
- memory_store: MemoryJobStore — in-process, no persistence (quickstart default)
- sqlite_store: SQLiteJobStore — persistent SQLite file with WAL mode
- postgres_store: PostgresJobStore — PostgreSQL-backed persistent jobstore
"""

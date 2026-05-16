# Context-Hub

MCP-native context collection and storage foundation for AI projects.

## Quick Start

```bash
pip install yohakuforce-context-hub
context-hub init --profile quickstart
context-hub migrate
context-hub serve
```

## Profiles

| Profile    | Database   | Embedding | Use case                          |
|------------|------------|-----------|-----------------------------------|
| quickstart | SQLite     | mock      | Zero-dependency local development |
| personal   | SQLite     | BGE-M3*   | Single-user persistent storage    |
| production | PostgreSQL | BGE-M3*   | Production deployment             |

*Install with: `pip install 'yohakuforce-context-hub[embedding]'`

## Docker

See `examples/docker/` for Docker Compose configuration.

## License

Apache-2.0

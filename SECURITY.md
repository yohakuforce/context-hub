# Security Policy

## Supported Versions

Context-Hub is currently in pre-release (v0.x). There is **no SLA** for security fixes in v0.x.
Once v1.0.0 is released, a formal support timeline will be published.

| Version | Supported |
|---|---|
| 0.x (pre-release) | Best-effort, no SLA |
| 1.0+ | TBD |

## Reporting a Vulnerability

**Please do not open public GitHub issues for security vulnerabilities.**

Use GitHub's [Private Vulnerability Reporting](https://github.com/yohakuforce/context-hub/security/advisories/new) to report vulnerabilities confidentially.

We will acknowledge receipt within 3 business days and aim to publish a fix or advisory within 30 days for critical issues (no SLA guarantee in v0.x).

## Scope

The following are in scope:

- Authentication bypass or privilege escalation
- SQL injection or arbitrary code execution
- Sensitive data exposure (API keys, passwords, tokens)
- Denial-of-service via uncontrolled resource consumption

The following are out of scope for v0.x:

- Issues requiring physical access to the machine
- Social engineering attacks
- Third-party dependencies (please report those upstream)

## Security Design Notes

### v0.1.0 認証ステータス (Authentication Status)

| Transport | Status | Environment Variable |
|-----------|--------|----------------------|
| HTTP API  | `DEV_API_KEY` environment variable — development-only (`APP_ENV=development` only) | `DEV_API_KEY` |
| MCP stdio | **Not enforced** — v0.1.0 assumes stdio localhost-only operation | N/A |

- `DEV_API_KEY`: HTTP API の development-only 認証。`APP_ENV=development` のときのみ有効。
- MCP stdio: v0.1.0 では認証未実装。stdio はローカルホスト専用運用を前提とする。
- 本格認証 (bcrypt + ConsumerRepository) は **v0.2.0** で実装予定。
- `CONTEXT_HUB_API_KEY` は v0.1.0 では参照されない。MCP クライアント設定から削除してよい。

### API Key Authentication (v0.x)

Context-Hub v0.x uses a single `DEV_API_KEY` for local development. This is intentional:
- The server is designed to run on `127.0.0.1` (localhost only) by default
- The `SECRET_KEY` in `.env` must be changed before any non-local deployment
- The `.env` file is written with `chmod 0600` permissions by `context-hub init`

### Data Handling

Context-Hub stores project context locally. No data is sent to third-party AI services
unless you configure an external LLM provider (`LLM_PROVIDER=claude-code` or `openai`).
The default `quickstart` profile uses a local mock embedding provider.

### Credential Hygiene

- Never commit `.env` files (it is in `.gitignore`)
- Rotate `SECRET_KEY` and all API keys if you suspect exposure
- Use `context-hub migrate --dry-run` to preview without touching the database

## Contact

For non-security bugs and feature requests, open a [GitHub Issue](https://github.com/yohakuforce/context-hub/issues).

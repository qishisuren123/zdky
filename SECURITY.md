# Security Policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately before public disclosure — use this repository's GitHub Security Advisories ("Report a vulnerability" under the Security tab) rather than a public issue. If you are unsure whether something is a vulnerability, treat it as one and report privately.

## Secrets policy

Do not commit or publish:

- API keys, auth tokens, bearer tokens, OAuth refresh tokens
- `.env`, `config.local.json`, `settings.local.json`
- Twitter/X cookies, passwords, or session tokens
- service-account JSON files
- SSH keys, `.pem`, `.p12`, `.pfx`, `.key` files
- logs that contain request headers, environment dumps, prompts with credentials, or private paths

Use `config.example.json`, `.env.example`, and environment variables instead. If a secret is accidentally committed or shared, revoke and rotate it immediately; deleting the file is not sufficient.

## Responsible use

AutoResearch V3 orchestrates model calls, research workflows, and optional remote execution. Run it only with credentials and infrastructure you are authorized to use. Keep live LLM tests separated from offline tests so contributors do not accidentally spend tokens or expose keys.

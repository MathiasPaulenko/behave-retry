# Security Policy

## Supported versions

| Version | Supported |
| ------- | --------- |
| 1.x     | Yes       |

## Reporting a vulnerability

If you discover a security vulnerability in behave-retry, please report it
responsibly.

**Do not open a public GitHub issue for security vulnerabilities.**

Instead, email **security@mathiaspaulenko.com** with:

- A description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

You will receive a response within 72 hours. If the vulnerability is
confirmed, a fix will be prepared and a security advisory will be published.

## Disclosure timeline

1. You report the vulnerability privately.
2. We acknowledge receipt within 72 hours.
3. We investigate and confirm the issue.
4. A fix is prepared and released.
5. A GitHub Security Advisory is published with credit to the reporter
   (unless anonymity is requested).

## Scope

This policy applies to the `behave-retry` package and its source code
hosted at [MathiasPaulenko/behave-retry](https://github.com/MathiasPaulenko/behave-retry).

## Best practices for users

- Always pin the package version in your `requirements.txt` or `pyproject.toml`.
- Review dependencies regularly with `pip-audit` or similar tools.
- Report any suspicious behavior immediately.

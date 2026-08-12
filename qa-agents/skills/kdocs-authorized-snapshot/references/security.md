# Security Boundary

- Use system-keychain authentication through `kdocs-cli`; never pass a token on the command line.
- Browser fallback executes read-only JavaScript in a visible authenticated Chrome tab.
- Do not read Chrome profile databases, cookies, local storage, passwords or keychain entries.
- Reject content whose effective page is an SSO or login page.
- Write only sanitized document text and evidence metadata to the requested output path.

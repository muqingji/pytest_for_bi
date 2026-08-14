---
name: authorized-product-browser-session
description: Start and verify the persistent isolated Chrome session used for real-time WPS/KDocs and Lexiang knowledge queries. Use when product knowledge queries require authenticated pages or when the local CDP session is unavailable or expired.
---

# Authorized Product Browser Session

Run `scripts/session.sh start` to reuse the dedicated Chrome profile and expose CDP only on `127.0.0.1:9222`. Run `scripts/session.sh status` before every query.

Never inspect, copy, archive, commit or parse the profile directory. Never extract cookies, tokens, passwords, local storage or authorization headers. Chrome owns authentication persistence. If either source redirects to login, report `reauthentication_required`; do not ask for credentials or attempt to bypass authentication.

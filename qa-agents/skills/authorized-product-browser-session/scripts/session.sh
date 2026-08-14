#!/bin/sh
set -eu
profile="${BI_KNOWLEDGE_CHROME_PROFILE:-$PWD/.runtime/authorized-browser-profile}"
endpoint="http://127.0.0.1:9222"
case "${1:-status}" in
  start)
    if curl -fsS "$endpoint/json/version" >/dev/null 2>&1; then echo '{"status":"available","endpoint":"http://127.0.0.1:9222"}'; exit 0; fi
    mkdir -p "$profile"
    open -na "Google Chrome" --args --remote-debugging-address=127.0.0.1 --remote-debugging-port=9222 --user-data-dir="$profile"
    echo '{"status":"starting","endpoint":"http://127.0.0.1:9222"}'
    ;;
  status)
    curl -fsS "$endpoint/json/version" >/dev/null && echo '{"status":"available","endpoint":"http://127.0.0.1:9222"}' || { echo '{"status":"unavailable"}'; exit 1; }
    ;;
  *) echo "usage: session.sh [start|status]" >&2; exit 2 ;;
esac

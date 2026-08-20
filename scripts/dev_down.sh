#!/usr/bin/env bash
# Stop whatever dev_up.sh started, and make sure the ports are actually free.
cd "$(dirname "$0")/.."

for name in agent mcp; do
  if [ -f "dev/$name.pid" ]; then
    pid=$(cat "dev/$name.pid")
    if kill "$pid" 2>/dev/null; then echo "stopped $name (pid $pid)"; fi
    rm -f "dev/$name.pid"
  fi
done

# Belt and braces: a stale or wrong pid file would otherwise leave a server
# holding its port, and the next dev_up refuses to start on a busy port.
if [ -f dev/ports.env ]; then
  . dev/ports.env
  for port in "${MCP_PORT:-}" "${AGENT_PORT:-}"; do
    [ -n "$port" ] || continue
    for pid in $(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null); do
      if kill "$pid" 2>/dev/null; then echo "freed port $port (pid $pid)"; fi
    done
  done
fi

"""Run the MCP server.

  stdio (Claude Desktop, IDEs):   BDNA_MCP_TOKEN=bdna_… python -m app.mcp
  Streamable HTTP (remote):       python -m app.mcp --transport streamable-http --port 8001
                                  clients send  Authorization: Bearer bdna_…
"""
from __future__ import annotations

import argparse
import os

from app.mcp.server import build_server


def main() -> None:
    ap = argparse.ArgumentParser(description="Brand DNA MCP server (read-only)")
    ap.add_argument("--transport", choices=["stdio", "streamable-http"], default=os.environ.get("BDNA_MCP_TRANSPORT", "stdio"))
    ap.add_argument("--host", default=os.environ.get("BDNA_MCP_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("BDNA_MCP_PORT", "8001")))
    ap.add_argument("--public-url", default=os.environ.get("BDNA_MCP_PUBLIC_URL"))
    args = ap.parse_args()
    if args.transport == "stdio":
        build_server().run("stdio")
    else:
        server = build_server(http_auth=True, public_url=args.public_url or f"http://{args.host}:{args.port}")
        server.run("streamable-http", host=args.host, port=args.port, stateless_http=True, json_response=True)


if __name__ == "__main__":
    main()

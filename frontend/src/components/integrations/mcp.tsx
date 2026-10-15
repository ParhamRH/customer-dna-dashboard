"use client";
import { Panel } from "@/components/page";
import { CodeBlock, CopyValue } from "@/components/code-block";
import { MetaList } from "@/components/page";

export type McpInfo = {
  transports: string[];
  http_url: string;
  stdio_command: string;
  http_command: string;
  auth: string;
  read_only: boolean;
  tools: { name: string; description: string }[];
};

export function McpPanel({ mcp, onCreateToken }: { mcp: McpInfo; onCreateToken?: () => void }) {
  return (
    <div className="grid gap-6">
      <p className="max-w-3xl text-base text-ink-2">
        The MCP server gives AI assistants (Claude, Cursor, custom agents) <strong className="font-medium text-ink">read-only</strong> access to this workspace’s brand knowledge. Each client authenticates with its own API token, so it only ever sees this
        workspace — or one brand, if the token is restricted. Unreviewed AI interpretations are labelled as such in every response.
      </p>
      <MetaList
        items={[
          ["Endpoint", <CopyValue key="u" value={mcp.http_url} />],
          ["Transports", mcp.transports.join(", ")],
          ["Authentication", mcp.auth],
          ["Access", mcp.read_only ? "Read-only — no tool can change brand data" : "Read and write"],
        ]}
      />
      <div className="grid gap-4 lg:grid-cols-2">
        <CodeBlock
          label="Remote client (Streamable HTTP)"
          mime="application/json"
          code={JSON.stringify({ mcpServers: { "brand-dna": { type: "http", url: mcp.http_url, headers: { Authorization: "Bearer bdna_…" } } } }, null, 2)}
        />
        <CodeBlock
          label="Local client (stdio)"
          mime="application/json"
          code={JSON.stringify({ mcpServers: { "brand-dna": { command: "python", args: ["-m", "app.mcp"], env: { BDNA_MCP_TOKEN: "bdna_…" } } } }, null, 2)}
        />
      </div>
      <p className="text-sm text-muted">
        Replace <code className="font-mono text-[12px]">bdna_…</code> with a token.{" "}
        {onCreateToken ? (
          <>
            <button className="text-accent hover:underline" onClick={onCreateToken}>
              Create a viewer token
            </button>{" "}
            — the configuration with the real token is shown once, right after creation.
          </>
        ) : (
          "Ask a workspace administrator for one."
        )}
      </p>
      {mcp.tools.length ? (
        <div>
          <h3 className="mb-2 text-md font-semibold">Tools available to AI clients</h3>
          <Panel>
            <ul className="divide-y divide-line">
              {mcp.tools.map((t) => (
                <li key={t.name} className="grid gap-1 px-4 py-2.5 sm:grid-cols-[14rem_1fr] sm:gap-4">
                  <span className="font-mono text-[12px] text-ink">{t.name}</span>
                  <span className="text-sm text-ink-2">{t.description}</span>
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      ) : null}
    </div>
  );
}

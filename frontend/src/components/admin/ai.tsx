"use client";
import type { AiDescribe } from "@/lib/types";
import { Panel } from "@/components/page";
import { TBody, THead, Table } from "@/components/ui/misc";
import { Tag } from "@/components/status";

export type AiSettings = AiDescribe & { keys_configured?: Record<string, boolean> };

export function AiProviders({ ai }: { ai: AiSettings }) {
  const caps: [keyof AiDescribe, string][] = [
    ["vision", "Image & video interpretation"],
    ["text", "Text & document analysis"],
    ["text_embedding", "Text embeddings (semantic search)"],
    ["visual_embedding", "Visual embeddings (similarity)"],
  ];
  return (
    <Panel>
      <Table>
        <THead>
          <tr>
            <th>Capability</th>
            <th>Provider</th>
            <th>Model</th>
            <th>Mode</th>
          </tr>
        </THead>
        <TBody>
          {caps.map(([k, label]) => (
            <tr key={k}>
              <td>{label}</td>
              <td>{ai[k].provider}</td>
              <td className="font-mono text-[12px]">
                {ai[k].model}
                {ai[k].dimensions ? <span className="text-muted"> · {ai[k].dimensions} dims</span> : null}
              </td>
              <td>{ai[k].development_adapter ? <Tag tone="ai">Development adapter</Tag> : <Tag tone="accent">Live provider</Tag>}</td>
            </tr>
          ))}
        </TBody>
      </Table>
    </Panel>
  );
}


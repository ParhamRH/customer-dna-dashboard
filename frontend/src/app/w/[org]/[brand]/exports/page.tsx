"use client";
import { useWorkspace } from "@/lib/workspace";
import { Main } from "@/components/shell";
import { PageHeader, Section } from "@/components/page";
import { ExportsPanel, ImportsPanel } from "@/components/manage/exports";

export default function WorkspaceExportsPage() {
  const ws = useWorkspace();
  return (
    <Main>
      <PageHeader
        title="Exports & imports"
        description="Exports contain only this workspace's data, with a manifest and checksums for every file so anyone can verify the package independently. Imports are validated and staged before anything changes."
      />
      <Section title="Exports">
        <ExportsPanel org={ws.orgId} canCreate={ws.can("export.create")} canDownload={ws.can("export.download")} />
      </Section>
      {ws.can("import.run") ? (
        <Section title="Imports" description="Upload an export package. You will see what it contains, map it to a brand and choose how conflicts are handled before committing. The commit runs as one transaction: if anything fails, nothing is changed.">
          <ImportsPanel org={ws.orgId} />
        </Section>
      ) : null}
    </Main>
  );
}

# Architecture decision records

Short records of decisions that shape the platform: the context, what was decided, and what it
costs. A superseded decision keeps its file and gains a "Superseded by" line.

| # | Decision | Status |
|---|---|---|
| [0001](0001-stack-and-repository-layout.md) | Stack and repository layout | Accepted |
| [0002](0002-tenant-isolation.md) | Tenant isolation with PostgreSQL Row Level Security and three database roles | Accepted |
| [0003](0003-governed-knowledge.md) | Governed knowledge: human approval, immutable revisions, published versions | Accepted |
| [0004](0004-provider-independent-ai.md) | Provider-independent AI with a labelled development adapter | Accepted |
| [0005](0005-postgres-job-queue.md) | Background work on a PostgreSQL job queue | Accepted |
| [0006](0006-hybrid-search.md) | Hybrid search fused with weighted reciprocal rank | Accepted |
| [0007](0007-object-storage-and-signed-urls.md) | Immutable originals in object storage, served by short-lived signed URLs | Accepted |
| [0008](0008-export-import-format.md) | Self-describing, checksummed export format and staged imports | Accepted |
| [0009](0009-same-origin-dashboard.md) | Same-origin dashboard with cookie sessions; tokens for machines | Accepted |
| [0010](0010-read-only-mcp-server.md) | A read-only MCP server bound to one workspace per token | Accepted |

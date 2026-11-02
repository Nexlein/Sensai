# docs/adr

Architecture Decision Records, one file per decision (`NNNN-title.md`).

Write an ADR when a choice is made, not afterwards: copy [`0000-template.md`](0000-template.md), take the next free number, and add it to the index below in the same PR. An accepted ADR is never rewritten; a changed decision gets a new ADR that supersedes the old one.

## Index

| #    | Title                                         | Status   |
| ---- | --------------------------------------------- | -------- |
| 0001 | [Deployment stack](0001-deployment-stack.md) | Accepted |
| 0002 | [Redis as a single persistent instance](0002-redis-single-instance.md) | Accepted |
| 0003 | [Gateway API CRDs and Traefik installed outside the chart, host-based routes on nip.io](0003-gateway-prerequisites-outside-chart.md) | Accepted |
| 0004 | [One deploy script shared by humans and CI, with a separate deploy identity](0004-deploy-script-and-identity.md) | Accepted |
| 0005 | [Zero-downtime updates with a tuned rolling update and a preStop sleep](0005-zero-downtime-rolling-updates.md) | Accepted |
| 0006 | [Keep CPU limits on every workload](0006-cpu-limits.md) | Accepted |

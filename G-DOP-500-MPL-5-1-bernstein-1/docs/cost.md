# Cost

Expected Azure spend of the project on the Azure for Students credits, and the routine that keeps it low.

Prices are pay-as-you-go retail prices in EUR from the [Azure Retail Prices API](https://prices.azure.com/api/retail/prices), queried on 2026-10-06 (disks on 2026-10-12 and 2026-10-13), excluding VAT. Students credits are consumed at these rates.

## Unit prices

| Item | What we have | Unit price | Billed when stopped? |
|---|---|---|---|
| Node VM | 2 × `Standard_DS2_v2_Promo` (2 vCPU, 7 GiB) | 0.154 €/h per node ¹ | No (deallocated) |
| Node OS disk | 2 × 128 GiB Premium SSD (P10) | 19.08 €/month per disk | Yes |
| Load balancer | Standard, ≤ 5 rules | 0.022 €/h | Yes ² |
| Public IP | Standard static IPv4 (outbound + app ingress) | 0.0044 €/h per IP | Yes |
| PostgreSQL volume | 5 GiB on `managed-csi`: Standard SSD ZRS, billed as E2 (8 GiB) ³ | 0.792 €/month + 0.0034 € per 10,000 operations | Disk: yes. Operations: no |
| Redis volume | 1 GiB on `managed-csi`: Standard SSD ZRS, billed as E1 (4 GiB) ⁵ | 0.396 €/month + 0.0034 € per 10,000 operations | Disk: yes. Operations: no |
| Backup storage | Blob Hot LRS, PostgreSQL dumps kept 7 days ⁶ | 0.0172 €/GB/month + 0.0475 € per 10,000 writes | Yes |
| Container registry | ACR Basic, 10 GiB included | 0.147 €/day | Yes |
| AKS control plane | Free tier | 0 € | — |

1. No public price is listed for `austriaeast`; this is the `francecentral` `DS2 v2` price, which the expired promo meter also charges.
2. Kept on the safe side: `az aks stop` leaves the load balancer and its IPs in the `MC_` group.
3. `managed-csi` creates zone-redundant disks on an AKS cluster spread across availability zones (Kubernetes ≥ 1.29). Details and the Premium alternative in [postgres.md](postgres.md#storage).
5. Azure's smallest managed disk is 4 GiB (E1), so the 1 GiB requested is billed as 4 GiB. Austria East price, 2026-10-13: E1 ZRS 0.396 €/month (LRS 0.264 €/month). 14 days: 0.396 × 14 / 30 = 0.18 €.

6. Austria East price, 2026-10-13, Hot LRS data stored and write operations. The votes database is a few hundred KiB; 4 dumps a day kept 7 days is 28 blobs, well under 0.1 GB (< 0.002 €/month), and 14 days of uploads is 56 writes plus the CLI's few calls per run (< 0.01 €). Shown as 0.01 € in the totals. If the dumps grow to 1 GB each, storage reaches ≈ 0.5 €/month: the total still holds.

## Expected total for the 2 weeks

Two weeks = 336 h. "With routine" assumes the cluster runs 8 h per working day (10 days, 80 h) and is stopped with `make cluster-stop` the rest of the time.

| Item | 24/7 | With routine |
|---|---|---|
| Node VMs (2 × 0.154 €/h) | 103.49 € | 24.64 € |
| Node OS disks (2 × P10, 14 days) | 17.81 € | 17.81 € |
| Load balancer | 7.39 € | 7.39 € |
| Public IPs (2) | 2.96 € | 2.96 € |
| PostgreSQL volume (E2 ZRS) | 0.37 € | 0.37 € |
| PostgreSQL disk operations ⁴ | 0.41 € | 0.10 € |
| Redis volume (E1 ZRS) | 0.18 € | 0.18 € |
| Backup storage (Blob LRS) | 0.01 € | 0.01 € |
| ACR Basic | 2.05 € | 2.05 € |
| **Total** | **≈ 135 €** | **≈ 56 €** |

4. Assumes 1 operation per second on average while the cluster runs, for PostgreSQL and Redis together: an idle PostgreSQL measured 0.05/s, each vote adds about one write, and Redis flushes its append-only file at most once per second, only while votes arrive. Every extra operation per second costs 0.10 € over the routine's 80 h.

The VMs are the only item that the stop routine removes, and they account for three quarters of the 24/7 bill. Egress and ACR storage above 10 GiB are negligible at this scale and left out.

## Budget alert

`infra/terraform` creates a monthly budget `bernstein-monthly` (`budget_amount`, default 60 €, just above the expected total with the routine). It sends an e-mail to `budget_contact_emails` when actual spend reaches 50 %, 80 % and 100 %, and when the forecast for the month reaches 100 %. The forecast alert is the useful one: it fires a few days after the cluster is left running, before the money is spent.

The budget is scoped to the **subscription**, not to `bernstein-rg`: the VMs, disks, load balancer and IPs live in the `MC_bernstein-rg_bernstein-aks_austriaeast` group that AKS manages, so a budget on `bernstein-rg` would only see the ACR (~2 € of the ~56 €).

Budget data is refreshed by Azure about once a day, so alerts lag spend by up to 24 h. To check that the address receives alerts, open the budget in the portal (Cost Management → Budgets → `bernstein-monthly`) and lower a threshold below the current spend, then restore it with `terraform apply`.

## Stop / start routine

```sh
make cluster-stop    # end of each session
make cluster-start   # start of the next one; waits for nodes Ready
make cluster-status  # Running / Stopped
```

`az aks stop` deallocates the nodes but keeps the cluster configuration, the deployed workloads and the PV disks. After `cluster-start` the pods are rescheduled from the stored state, so nothing needs to be redeployed. Override `RESOURCE_GROUP` / `AKS_NAME` on the command line if the defaults changed.

Rejected alternatives:

- Scaling the pool to 0: not allowed on a system node pool.
- `terraform destroy` every evening: loses the PV data and takes ~15 min to recreate.

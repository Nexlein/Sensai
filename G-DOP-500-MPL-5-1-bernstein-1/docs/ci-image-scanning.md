# CI: image scanning and dependency updates

Base images are pinned by digest (see [worker.md](worker.md#pinned-base-images)), so they never update by themselves, and known CVEs pile up in them. Two pieces deal with that (#13):

- **Trivy** scans every image pushed by `release-images.yml` and reports HIGH and CRITICAL vulnerabilities;
- **Dependabot** opens pull requests that bump base image digests, application dependencies and GitHub Actions.

## Trivy

After the push, each job of `release-images.yml` scans the image it just pushed, by its SHA tag:

```yaml
- uses: aquasecurity/trivy-action@v0.36.0
  with:
    image-ref: ${{ env.IMAGE }}:${{ github.sha }}
    severity: HIGH,CRITICAL
    ignore-unfixed: true
    exit-code: "0"
```

- **`severity: HIGH,CRITICAL`**: LOW and MEDIUM findings number in the hundreds on any Debian or Ubuntu base and hide the ones that matter.
- **`ignore-unfixed: true`**: a CVE with no fixed version yet cannot be acted on; listing it only adds noise.
- **`exit-code: "0"`**: non-blocking. The image is already pushed at this point, and failing the job would not remove it; a decision to block on CRITICAL can come later (it would then move before the push).
- The scan uses the registry login from `az acr login`, so it reads exactly the image that was pushed.

Trivy runs twice: once for a readable table, once for SARIF (`skip-setup-trivy` and the shared vulnerability database cache keep the second run short). Results go to three places:

| Where | What | Always |
|---|---|---|
| Job summary (run page) | the table, per service | yes |
| Artifact `trivy-<service>` | `trivy.txt` and `trivy.sarif` | yes |
| Security → Code scanning | alerts from the SARIF, category `trivy-<service>` | only if `CODE_SCANNING=true` |

### Why the Security tab upload is optional

The repository is private, and code scanning on a private repository needs **GitHub Code Security** (paid, enabled by an organization admin). Today the API answers:

```
Code Security must be enabled for this repository to use code scanning. (HTTP 403)
```

So the SARIF upload step only runs when the repository variable `CODE_SCANNING` is `true`:

```sh
gh variable set CODE_SCANNING --body true   # once Code Security is enabled
```

Until then the job summary and the artifact hold the same results.

### Findings at the time of writing

Local scan of the three images (`trivy image --severity HIGH,CRITICAL --ignore-unfixed`):

| Image | Findings | Where |
|---|---|---|
| poll | 4 | the Python interpreter of `python:3.14-slim` |
| worker | 3 HIGH | `usr/bin/pebble` (Go standard library, `CVE-2026-78667`, fixed in Go 1.26.9), a tool shipped by the Ubuntu base of `eclipse-temurin`, not used by the worker |
| result | 7 | Debian 12 packages of `node:24-slim` |

The application dependencies (pip, npm, Maven jar) had none. Every finding is in a base image, which is what the Dependabot digest bumps fix.

## Dependabot

`.github/dependabot.yml` checks weekly and opens PRs against `dev` (where everything goes through CI first, #11):

| Ecosystem | Directory | Updates |
|---|---|---|
| `docker` | the three `poll-application/*` | base image digests (and tags within the same major, e.g. `node:24-slim`) |
| `pip` | `poll-application/poll` | `requirements.txt` |
| `npm` | `poll-application/result` | `package.json` / `package-lock.json` |
| `maven` | `poll-application/worker` | `pom.xml` |
| `github-actions` | `/` | action versions in `.github/workflows/`, grouped in one PR |

Commit messages use our Conventional Commits prefixes (`build(deps)`, `ci(deps)`). Dependabot version updates work on private repositories without Code Security.

Dependency bumps touch the provided application's manifests; they are reviewed like any change, and CI builds the affected image before merge.

## Rejected alternatives

- **Microsoft Defender for Containers** on ACR: scans in Azure, but paid per image and per node, out of the credit budget ([cost.md](cost.md)).
- **Grype**: equivalent scanner. Trivy also scans Kubernetes manifests and Terraform for misconfigurations, which can be reused later (#33).

# CI: pull request checks

`.github/workflows/ci.yml` runs on every pull request to `dev` or `main` (#11). It catches a broken Dockerfile, chart or Terraform change before review, instead of when someone deploys. Images are built but not pushed; pushing is `release-images.yml` (#12).

## Jobs

```
changes ──> image (matrix: changed services) ──> build   (required check)
lint                                                     (required check)
```

| Job | What it does | Required check |
|---|---|---|
| `changes` | Lists which of `poll`, `worker`, `result` the PR touches | no |
| `lint` | hadolint, `helm lint` + kubeconform, `terraform fmt` + `validate` | **yes** |
| `image` | Builds each changed service's image with Buildx, no push | no (one check per service) |
| `build` | Fails if change detection or any image build failed | **yes** |

### lint

- **hadolint** on every `Dockerfile` in the repository (`recursive: true`), with the configuration in `.hadolint.yaml`.
- **Helm**: `helm lint --strict`, then `helm template | kubeconform -strict` against the Kubernetes 1.36 schemas. The chart needs `global.registry`, `global.tag` and `postgres.password` to render, so CI passes placeholder values, the same ones as in `CLAUDE.md`. `helm lint` checks the chart's structure and templates; kubeconform checks that every rendered object is valid Kubernetes (a typo like `contaienrs` passes `helm lint` and fails kubeconform).
- **Terraform**: `terraform fmt -check -recursive`, then `terraform init -backend=false` and `terraform validate`. `-backend=false` skips the azurerm backend, so CI needs no Azure access: validate only needs the providers' schemas.

`lint` runs on every PR, whatever changed: it takes well under a minute.

### image and build

Building the Java worker takes minutes, so a PR only builds the images it touches. `dorny/paths-filter` compares the PR to its base and outputs the changed services as a JSON list (`["worker","result"]`), which becomes the `image` matrix.

Why not `on.pull_request.paths`: a workflow filtered out by `paths` never starts, so its required check stays "Expected — Waiting for status" forever and the PR cannot be merged. With the filter inside the workflow, the workflow always runs and always reports.

Why the extra `build` job: a matrix job reports one check per entry (`image (poll)`, `image (worker)`, ...), and which entries exist depends on the PR, so none of them can be a required check. `build` waits for all of them and is the single stable check:

```yaml
build:
  needs: [changes, image]
  if: always()
```

`if: always()` makes it run even when `image` is skipped (no service changed) or failed. It passes when `image` succeeded or was skipped, and fails otherwise, including when `changes` failed (otherwise an error in change detection would skip every build and pass).

Each build uses the GitHub Actions cache (`type=gha`), one scope per service so the three images do not evict each other, and `mode=max` to also cache the intermediate stages (the worker's Maven dependency layer, see [worker.md](worker.md#dependency-layer)). A second run on unchanged dependencies rebuilds only the layers after `COPY src`.

### concurrency

```yaml
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
```

A new push to a PR cancels the run still going for the previous commit: only the latest commit's result matters.

## hadolint exception

`.hadolint.yaml` ignores **DL3008** ("pin versions in apt-get install"), raised by the `tini` install in the result image. Pinning an apt version (`tini=0.19.0-1`) breaks the build as soon as Debian publishes an update and removes the old version from the mirror. Reproducibility comes from pinning the base image by digest; updates are reviewed through Dependabot (#13).

## Required checks

`lint` and `build` must be marked as required status checks on `dev` and `main` (Settings → Branches, or the ruleset), by a repository admin. Until a check has run once on a PR, GitHub does not offer it in the list.

## Running the checks locally

```sh
docker run --rm -i hadolint/hadolint < poll-application/result/Dockerfile   # add -c .hadolint.yaml via a mount
cd infra/terraform && terraform fmt -check -recursive && terraform init -backend=false && terraform validate
# Helm and kubeconform: commands in CLAUDE.md
```

Rejected alternatives:

- **Azure Pipelines**: a second CI system to set up while the code and issues are on GitHub.
- **Building only on merge**: problems surface after review, when they cost more to fix.

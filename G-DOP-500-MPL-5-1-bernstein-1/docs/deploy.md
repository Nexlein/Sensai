# Deploying with `make deploy`

`scripts/deploy.sh` (wrapped by `make deploy`) takes a cluster and a registry and ends with two working URLs. It is the single entry point of the defense step "deploy from a fresh cluster", and the same script runs in CI ([ci-deploy.md](ci-deploy.md)). Decision record: [ADR-0004](adr/0004-deploy-script-and-identity.md).

## Use

```sh
az login
export POSTGRES_PASSWORD='choose-one'
export AKS_RESOURCE_GROUP=bernstein-rg
export AKS_NAME=bernstein-aks
export ACR_NAME=bernsteinacr
make deploy
```

Instead of exporting them in every shell, the variables can go in `.env` at the repository root, which the Makefile reads with `-include .env` (the `-` makes a missing file no error):

```sh
export AKS_RESOURCE_GROUP=bernstein-rg
export AKS_NAME=bernstein-aks
export ACR_NAME=bernsteinacr
export POSTGRES_PASSWORD=choose-one
```

- `export KEY=value` is valid in both make and bash: `make` passes the variables to `deploy.sh`, and `source .env` loads them in a shell for running the scripts directly.
- No quotes: make would keep them as part of the value. A `$` in the password is written `$$`, or make expands it.
- `.env` is in `.gitignore`: the password stays on the machine, never in the repository (subject requirement). The script still passes it to Helm through a pipe, not the command line.
- A value in `.env` overrides the same variable exported in the shell: make gives its own assignments priority over the environment.

| Variable | Required | Meaning |
|---|---|---|
| `POSTGRES_PASSWORD` | yes | Password of the PostgreSQL user. |
| `AKS_RESOURCE_GROUP`, `AKS_NAME` | yes | The cluster, ours or the evaluator's. |
| `ACR_NAME` | yes | Registry, without `.azurecr.io`. Images are pushed there and pulled from there. Created (Basic, in `AKS_RESOURCE_GROUP`) if it does not exist. |
| `IMAGE_TAG` | no | Tag of images already in the registry. Unset: build and push the current commit, and the uncommitted changes of each service under its own tag. |
| `NAMESPACE` | no | Default `bernstein`. |
| `SKIP_ACR_ATTACH` | no | `1` skips creating the registry and checking pull access (CI). |
| `BACKUP_STORAGE_ACCOUNT`, `BACKUP_CONTAINER`, `BACKUP_CLIENT_ID` | no, all three or none | Enable the PostgreSQL backup CronJob ([postgres.md](postgres.md#backups)). Values from `terraform output`. Unset: no backup. |

On our cluster, with backups:

```sh
export BACKUP_STORAGE_ACCOUNT=$(terraform -chdir=infra/terraform output -raw backup_storage_account)
export BACKUP_CONTAINER=$(terraform -chdir=infra/terraform output -raw backup_container)
export BACKUP_CLIENT_ID=$(terraform -chdir=infra/terraform output -raw backup_client_id)
make deploy
```

Output on stdout, progress on stderr:

```
poll:   http://poll.<ip>.nip.io
result: http://result.<ip>.nip.io
```

`make destroy` runs `scripts/destroy.sh`: it uninstalls the release. The PostgreSQL and Redis disks survive and keep billing; `DELETE_PVC=1 make destroy` removes them and the data. Traefik and the Gateway API CRDs stay (cluster-wide, [ADR-0003](adr/0003-gateway-prerequisites-outside-chart.md)).

## What the script does, step by step

The script starts with `set -euo pipefail`: any failing command stops it, an unset variable is an error, and a failure inside a pipe is not hidden.

### 1. Checks before touching anything

```bash
for var in POSTGRES_PASSWORD AKS_RESOURCE_GROUP AKS_NAME ACR_NAME; do
  [ -n "${!var:-}" ] || die "${var} is not set (see docs/deploy.md)"
done
```

`${!var}` is indirect expansion: the value of the variable whose name is in `var`. Each missing variable gets its own message. Tools are checked first (`docker` and `git` only when the script must build). This runs before the first `az` call: a missing password never reaches the cluster.

`docker buildx` is checked separately when the script must build: it is a CLI plugin, packaged apart from Docker on some distributions (Arch: `docker-buildx`), so `command -v docker` succeeds without it. Unchecked, the deploy would log in, look up the registry and only then fail with `docker: unknown command: docker buildx`.

```
$ env -i PATH="$PATH" HOME="$HOME" ./scripts/deploy.sh
error: docker buildx is not installed (plugin docker-buildx, see README.md)
```

```
$ env -u POSTGRES_PASSWORD AKS_RESOURCE_GROUP=x AKS_NAME=y ACR_NAME=z IMAGE_TAG=t ./scripts/deploy.sh
error: POSTGRES_PASSWORD is not set (see docs/deploy.md)
```

The three backup variables are counted next. None set: `--set postgres.backup.enabled=false`. All three: `enabled=true` plus the three values. One or two: the script stops, because a partial set is a typo or a missing CI variable, not a wish to run without backups. Turning backups off silently there would only be noticed the day a restore is needed.

```
$ BACKUP_CONTAINER=x POSTGRES_PASSWORD=p AKS_RESOURCE_GROUP=a AKS_NAME=b ACR_NAME=c IMAGE_TAG=t ./scripts/deploy.sh
error: set all of BACKUP_STORAGE_ACCOUNT BACKUP_CONTAINER BACKUP_CLIENT_ID to enable backups, or none (see docs/deploy.md)
```

The values themselves are checked by the chart schema when Helm runs: `BACKUP_CLIENT_ID` must be a GUID (`at '/postgres/backup/clientId': '0000-1111' does not match pattern ...`).

### 2. Azure session and credentials

`az account show` fails when not logged in, and the script answers `run 'az login'`. Then `az aks get-credentials --overwrite-existing` writes the cluster into the current kubeconfig (replacing a stale entry of the same name, as after a cluster re-creation).

### 3. The registry must exist, and the cluster must be able to pull from it

The subject promises the evaluator a ready-to-use cluster, not a registry. When `az acr show` does not find `ACR_NAME`, the script creates it:

```bash
if ! az acr show -n "${ACR_NAME}" >/dev/null 2>&1; then
  [ "$(az acr check-name -n "${ACR_NAME}" --query nameAvailable -o tsv)" = "true" ] \
    || die "registry ${ACR_NAME} is not in this subscription and its name is taken: choose another ACR_NAME"
  az acr create -g "${AKS_RESOURCE_GROUP}" -n "${ACR_NAME}" --sku Basic >/dev/null
fi
```

- Registry names are global (`<name>.azurecr.io`). `az acr show` only sees the current subscription, so "not found" can also mean "someone else owns it". `check-name` tells the two apart before `create`, and the error says what to do instead of Azure's `AlreadyInUse`.
- Basic is the tier our Terraform uses (0.147 €/day, [cost.md](cost.md)): 10 GiB is far more than three images. The location is the resource group's, the same region as the cluster.
- On our cluster the registry exists (Terraform), so this step does nothing and adds no cost.

Then the pull access. Terraform gives our cluster's kubelet identity `AcrPull`. The evaluator's cluster has no such assignment, and pods would sit in `ImagePullBackOff`. The script looks it up:

```bash
pulls="$(az role assignment list --assignee "${kubelet_id}" --scope "${acr_id}" --role AcrPull --query 'length(@)' -o tsv)"
if [ "${pulls}" = "0" ]; then az aks update ... --attach-acr "${ACR_NAME}"; fi
```

Checking first makes the second run a no-op (`--attach-acr` would work again, but takes a minute and touches the cluster). It needs the right to create role assignments (Owner); CI skips the step with `SKIP_ACR_ATTACH=1`.

### 4. Images

With `IMAGE_TAG` the images are assumed to exist (CI built them). Without it the tag is the full HEAD SHA, and for each of `poll`, `worker`, `result` the script asks the registry (`az acr manifest show-metadata`) and builds only what is missing, with `docker buildx build --platform linux/amd64 --push`. `--platform` matters: building on an ARM laptop would give images the AKS nodes cannot run (`exec format error`). An existing tag is never overwritten, the same rule as in [ci-release-images.md](ci-release-images.md).

#### Uncommitted changes

The defense changes the source of one application and redeploys it. With the HEAD SHA as the only tag, an edit that is not committed yet would deploy nothing: the tag already exists in the registry, the build is skipped, and Helm renders the same manifests. So each service directory is compared with HEAD, by content:

```bash
working_tree_of() {
  local index tree
  index="$(mktemp)"
  cp "$(git -C "${root}" rev-parse --path-format=absolute --git-path index)" "${index}"
  GIT_INDEX_FILE="${index}" git -C "${root}" add -A -- poll-application
  tree="$(GIT_INDEX_FILE="${index}" git -C "${root}" write-tree)"
  rm -f "${index}"
  git -C "${root}" rev-parse "${tree}:poll-application/$1"
}
```

- `git write-tree` gives the hash of a directory as git would commit it: the same content always gives the same hash. `git add -A` takes modified, deleted and new files, and skips what `.gitignore` excludes.
- `GIT_INDEX_FILE` points git at a copy of the index: the user's staging area is not touched, and nothing is committed. The only trace is a few objects in `.git/objects`, removed by the next `git gc`.
- A clean service gives exactly `HEAD:poll-application/<service>`. A service that differs is tagged `<HEAD 12>-dirty-<tree 12>` and passed as `--set-string <service>.image.tag=...`, which overrides `global.tag` for that component only ([helm-chart.md](helm-chart.md)).

Run with `az`, `docker`, `helm` and `kubectl` replaced by stubs (empty registry, one line added to `poll/app.py`):

```
>> Credentials of aks
>> Creating registry acrx (Basic) in rg
>> poll has uncommitted changes: tagged bafe034aac52-dirty-6d7973ca2399
>> Building poll:bafe034aac52-dirty-6d7973ca2399
>> Building worker:bafe034aac528428e552778ac9a4122a40b3de23
>> Building result:bafe034aac528428e552778ac9a4122a40b3de23
>> Deploying bernstein (tag bafe034aac52, domain 1.2.3.4.nip.io, backups false)
```

and the images Helm then renders (`helm template ... --set-string poll.image.tag=bafe034aac52-dirty-6d7973ca2399`):

```
          image: example.azurecr.io/poll:bafe034aac52-dirty-6d7973ca2399
          image: example.azurecr.io/result:bafe034aac528428e552778ac9a4122a40b3de23
          image: example.azurecr.io/worker:bafe034aac528428e552778ac9a4122a40b3de23
```

Only poll's pod template changes, so only poll rolls out. Running again without editing gives the same tag: the image is found and nothing restarts. Editing again gives a new tag. Once the change is committed, HEAD moves and every service is clean again under the new SHA.

### 5. Gateway prerequisites

If `GatewayClass traefik` exists and the `traefik` Service has an IP, the domain is `<ip>.nip.io` and nothing is installed. Otherwise `scripts/install-gateway.sh` runs (CRDs, then Traefik) and prints the domain. "Install if absent" instead of "always run" keeps a normal deploy free of cluster-wide changes, which a namespaced CI identity could not do (#34).

### 6. The release

```bash
helm upgrade --install bernstein charts/bernstein --namespace bernstein --create-namespace \
  --rollback-on-failure --wait --timeout 10m \
  --set global.registry=... --set-string global.tag=... --set-string gateway.domain=... \
  --set postgres.backup.enabled=... [--set-string postgres.backup.storageAccount=... container=... clientId=...] \
  --values <(jq -n --arg p "$POSTGRES_PASSWORD" '{postgres: {password: $p}}')
```

- `upgrade --install` installs the first time and upgrades after: one command for both.
- `--rollback-on-failure` (Helm 4; `--atomic` on Helm 3, picked by looking at `helm upgrade --help`) restores the previous revision if the release does not become Ready in 10 minutes. `--wait` makes Helm wait for the pods.
- `--set-string` for the tag: an all-digit SHA given to `--set` becomes a number and fails the schema.
- No `--reuse-values`: every value comes from the command line and the environment, so the release is exactly what this run asked for. The other side: a value set by hand with `helm upgrade --set` is dropped by the next `make deploy`. That is why backups are variables of the script and not a manual upgrade.
- **The password does not appear in the command line.** Arguments are readable by every user of the machine in `ps`. `<(...)` is a process substitution: bash gives helm a file descriptor path (`/dev/fd/63`) fed by `jq`, so the secret passes through a pipe and never reaches disk. `jq --arg` escapes any character into valid JSON, which is valid YAML: a password such as `pa"ss: $x\` survives (checked with `helm template`: the rendered Secret decodes to the same string).

### 7. Result

URLs printed on stdout. When `GITHUB_STEP_SUMMARY` is set (CI), they are also written to the job summary.

## Idempotence

A second run with the same tag and password: the registry lookups find the images, the role assignment exists, Traefik is present, and `helm upgrade` renders identical manifests. Helm records a new revision, but no pod template changes, so no pod restarts. The schema hook Job runs again before the upgrade; it is idempotent by design ([helm-hooks.md](helm-hooks.md)). The Redis password is kept by the chart's `lookup`, and the PostgreSQL password is unchanged. The acceptance criteria are verified on AKS at the end of the sprint.

## On the evaluator's cluster

Needs: Azure access with enough rights to read the cluster, create a registry in its resource group and create a role assignment (Owner or equivalent), `az`, `kubectl`, `helm`, `jq`, and Docker only if images must be built. Nothing from our Terraform is required: `ACR_NAME` can be an ACR the evaluator owns or a new, unused name, which the script creates, and the script attaches it to their cluster. The `BACKUP_*` variables stay unset there: their cluster has no backup storage account or federated identity, so the release deploys without the CronJob.

## Rejected alternatives

- **README with the commands**: about fifteen commands to type under pressure; one typo and the demonstration is lost.
- **GitOps (Argo CD / Flux)**: excellent for continuous reconciliation, but it needs a controller and a bootstrap step on the evaluator's fresh cluster, and "launch the deployment" becomes indirect. A possible next step.
- **`--set-string postgres.password=...`**: the value is visible in `ps` while helm runs.
- **Always running `install-gateway.sh`**: slower, and requires cluster-wide rights at every deploy.
- **Reading `terraform output` inside the script for backups**: ties the deploy to our Terraform state, which the evaluator's cluster does not have, and CI would need state access.
- **Backups on by default in `values.yaml`**: any install without the storage account and identity would fail the schema.
- **Refusing to deploy uncommitted changes**: safe, but at the defense it turns "change the code and redeploy" into "change, commit, redeploy", and a forgotten commit gives a deploy that silently changes nothing (the previous behaviour, with only a warning).
- **A timestamp tag for every dirty build**: rebuilds and rolls out all three services on every run, even unchanged ones, and is not idempotent. The content hash rebuilds only what changed.
- **Requiring an existing registry**: one more manual step (`az acr create`) for the evaluator, outside the one command.

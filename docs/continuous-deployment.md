# Continuous deployment for the educational instance

The automatic workflow remains the Development path. Production is promoted
only through `.github/workflows/promote-production.yml`, which must be started
with `workflow_dispatch`. See [development and production environments](environments.md)
for the isolation model.

`.github/workflows/ci.yml` runs backend and frontend jobs in parallel. Backend
tests cover SQLite and PostgreSQL. After both pass, the stack job builds images
and starts the production Compose file with `docker-compose.ci.yaml`. HTTP tests
cover origin protection, database readiness, authentication and interview CRUD.
Chromium registers a disposable user and verifies two-browser collaboration
through a local gateway that injects the origin header as CloudFront does.
Cleanup removes only this CI project's containers and volume. CI browser
recordings are disabled to avoid retaining tokens and invitation links.

After all tests pass on a `main` push, a separate publish job builds the
application image once, tags it as `YYYYMMDD-HHMMSS-shortsha`, pushes it to the
private immutable ECR repository, resolves its `sha256` digest and uploads a
small `deployment-manifest` artifact. The Development deployment receives only
that digest. EC2 pulls `repository@sha256:...` and starts it with `--no-build`;
PostgreSQL is not restarted.

Frontend installation matches Docker's npm 11.19.0 procedure, without consuming
or modifying the operator's untracked frontend/package-lock.json. Dependency
ranges remain an existing reproducibility limitation; backend and browser
dependencies use committed lockfiles.

## Identity and permissions

`deploy/aws/github-oidc-stack.yaml` is a separate support stack. It does not update
the application stack, network or database. Use profile `blueprint-dev` in
`us-east-2`. Confirm the selected region in AWS Settings > View all projects >
Overview > Additional Info > Region; check credits/spend in AWS Settings > Billing.

The Development role trusts only the STS audience and this repository's main OIDC subject.
Query `/repos/kanorona/pixel-perfect-match/actions/oidc/customization/sub` before
provisioning; immutable owner/repository IDs may be enabled. The current subject
is `repo:kanorona@223929085/pixel-perfect-match@1413820328:ref:refs/heads/main`.
No workflow environment is used for Development because it changes the subject. PRs and manual
dispatches run CI but cannot trigger the deployment job. Main pushes also skip
deployment until BLUEPRINT_DEPLOY_ROLE_ARN exists; a separate job explicitly
reports that AWS setup is pending, so CI success is not deployment success.

The template contains the complete permission policy:

- `RunOnlyTheDeploymentProcedure`: `ssm:SendCommand` restricted to the named
  document, one existing instance and the selected region.
- `ReadCommandStatus`: `ssm:GetCommandInvocation` in that region. This API requires
  `Resource: '*'` because it has no per-command/instance IAM resource support.
  It can read other command results, so credentials must stay out of SSM output.

No permissions administer IAM, create/delete/restart EC2, update CloudFormation,
read secrets or run arbitrary shell documents. Deployment inputs are a
40-character SHA and sha256 digest. The repository name is fixed inside the SSM
document.
Writers to main remain trusted to deploy code and Dockerfiles. Protect main when
sharing this project.

Production uses a second deployment support stack and reuses the same OIDC
provider. Its role trusts only
`repo:kanorona@223929085/pixel-perfect-match@1413820328:environment:production`
and can send only its stack-owned SSM document to instance
`i-088ca3bcb29814cef`. The `production` GitHub Environment is therefore part of
the security boundary and should require a reviewer.

## Provisioning and settings

Prepare the support stack with `CAPABILITY_NAMED_IAM`. Review its change set
before execution. Its parameters are public:

- `InstanceId`: the application stack's existing instance output.
- `Repository`: `kanorona/pixel-perfect-match`.
- `GitHubSubject`: the exact main subject above.
- `ExistingOidcProviderArn`: an existing GitHub provider ARN, or empty to create one.

The stack creates only a deployment role, an SSM document, and an OIDC provider
when one is not already present. Do not execute old application change sets.
Set these GitHub Actions repository variables after support-stack creation:

| Variable | Value source |
|---|---|
| BLUEPRINT_DEPLOY_ROLE_ARN | Support stack DeployRoleArn |
| BLUEPRINT_DEPLOY_DOCUMENT | Support stack DeployDocumentName |
| BLUEPRINT_INSTANCE_ID | Application stack InstanceId |
| BLUEPRINT_PUBLIC_URL | Application stack ApplicationUrl |

These are not credentials. Do not copy AWS keys, the origin token or the database
password to GitHub. The root-owned EC2 `.env` stays private, mode 0600.

`deploy/aws/ecr-stack.yaml` creates the shared private repository and a separate
main-only OIDC push role. It attaches pull-only policies to the two existing EC2
roles and creates or replaces no instance. Tags are immutable, basic scanning
and AES256 encryption are enabled, and deletion/replacement retain the
repository. There is deliberately no lifecycle deletion because old images are
rollback candidates.

Create the `blueprint-interviews-registry` change set using
`deploy/aws/environments/ecr.parameters.example.json`. After cost approval and
execution, configure these repository variables from its outputs:

| Variable | Value source |
|---|---|
| BLUEPRINT_ECR_PUSH_ROLE_ARN | Registry stack BuildPushRoleArn |
| BLUEPRINT_ECR_REPOSITORY_URI | Registry stack RepositoryUri |

Update both deployment support stacks with `EcrRepositoryName` before enabling
the publish job. Their roles remain SSM-only; ECR pulls use the environment's
EC2 instance role.

For Production, create `blueprint-interviews-ci-production` from the same
template using `deploy/aws/environments/production-ci.parameters.example.json`.
Set the same four variable names in the GitHub Environment named `production`,
using the Production support-stack outputs and application-stack outputs. The
environment values override the Development repository variables only inside
the protected Production job.

## Manual Development to Production promotion

1. Confirm Development is healthy and its CI run completed successfully.
2. In GitHub, open **Actions > Promote development to production > Run workflow**.
3. The selection job reads the SHA currently reported by Development; there is
   no SHA input and the workflow never substitutes the latest `main` revision.
4. It requires a successful `push` run of `ci.yml` for that exact SHA and reads
   that run's immutable deployment manifest.
5. Approve the protected `production` environment. The Production-only OIDC
   role then deploys exactly the manifest digest, preserving `.env` and PostgreSQL.
6. The job succeeds only after public HTTPS readiness reports the exact SHA.

The workflow and host lock both serialize Production deployments. A concurrent
manual run waits, and a second command reaching the host fails closed.

## Deploy, validate and diagnose

A normal push to main starts CI. Only successful main pushes deploy. Main runs
are serialized and a host lock also prevents concurrent updates. A superseded
commit fails closed before checkout when it no longer matches published main.

The procedure never builds on EC2. It pulls the exact ECR digest, atomically
records `BLUEPRINT_IMAGE` and `BLUEPRINT_REVISION` in the private `.env`, then
replaces app and Caddy. PostgreSQL keeps running; its volume and secrets are
preserved. Brief downtime and WebSocket disconnections are expected during
replacement. There is no `compose down`, volume deletion or automatic rollback.
`/health/ready` reports the revision baked into the immutable image.

SSM success requires database readiness, exact revision, frontend availability
and origin rejection tests. GitHub then verifies public HTTPS `/health/ready`,
including certificate checks, bounded retries and an exact SHA match. An older
healthy build cannot satisfy the deployment check.

On failure, inspect SSM status and `/var/log/blueprint-deploy.log` through operator
SSM access. Logs are private and require redaction before sharing. Never print
`.env`, resolved Compose configuration or Docker environment into Actions logs.
No automated recovery or infrastructure operations are configured.

## Rollback

Old immutable images and their 90-day GitHub release manifests are retained.
Run **Roll back production to a previous image**, provide the numeric ID of a
successful historical `ci.yml` main run, review its revision/tag/digest, and
approve the same protected `production` environment. The workflow rejects
failed, non-main or non-CI runs. Rollback is manual and serialized with normal
promotions.

This remains a single educational host without high availability. CI builds
need external package access. The existing HTTP origin
hop and disposable root-disk PostgreSQL design are unchanged.

## Cleanup after the exercise

Both application and support stacks need separate authorized cleanup. Disable
the deployment variables before deleting the application. Deleting only the
application does not remove the support role/document. A reused shared OIDC
provider must not be deleted. The workflow never deletes infrastructure.

## Current AWS state

Both application and support stacks are active, and the protected manual
promotion has been verified. The registry migration is not active until its
change set, support-stack updates and GitHub repository variables are applied.

# Continuous deployment for the educational instance

`.github/workflows/ci.yml` runs backend and frontend jobs in parallel. Backend
tests cover SQLite and PostgreSQL. After both pass, the stack job builds images
and starts the production Compose file with `docker-compose.ci.yaml`. HTTP tests
cover origin protection, database readiness, authentication and interview CRUD.
Chromium registers a disposable user and verifies two-browser collaboration
through a local gateway that injects the origin header as CloudFront does.
Cleanup removes only this CI project's containers and volume. CI browser
recordings are disabled to avoid retaining tokens and invitation links.

Frontend installation matches Docker's npm 11.19.0 procedure, without consuming
or modifying the operator's untracked frontend/package-lock.json. Dependency
ranges remain an existing reproducibility limitation; backend and browser
dependencies use committed lockfiles.

## Identity and permissions

`deploy/aws/github-oidc-stack.yaml` is a separate support stack. It does not update
the application stack, network or database. Use profile `blueprint-dev` in
`us-east-2`. Confirm the selected region in AWS Settings > View all projects >
Overview > Additional Info > Region; check credits/spend in AWS Settings > Billing.

The role trusts only the STS audience and this repository's main OIDC subject.
Query `/repos/kanorona/pixel-perfect-match/actions/oidc/customization/sub` before
provisioning; immutable owner/repository IDs may be enabled. The current subject
is `repo:kanorona@223929085/pixel-perfect-match@1413820328:ref:refs/heads/main`.
No workflow environment is used because it changes the subject. PRs and manual
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
read secrets or run arbitrary shell documents. The only input is a 40-character
SHA, checked against current published main and the host's repository URL.
Writers to main remain trusted to deploy code and Dockerfiles. Protect main when
sharing this project.

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

## Deploy, validate and diagnose

A normal push to main starts CI. Only successful main pushes deploy. Main runs
are serialized and a host lock also prevents concurrent updates. A superseded
commit fails closed before checkout when it no longer matches published main.

The procedure builds before replacing app, passes the SHA as the image's
`BLUEPRINT_REVISION`, and replaces app and Caddy. PostgreSQL keeps running; its
volume and `.env` are preserved. Brief downtime and WebSocket disconnections are
expected during replacement. There is no `compose down`, volume deletion or
automatic rollback. CloudFormation's application `RepoRef` still records the
bootstrap commit; `/health/ready` reports the current image revision.

SSM success requires database readiness, exact revision, frontend availability
and origin rejection tests. GitHub then verifies public HTTPS `/health/ready`,
including certificate checks, bounded retries and an exact SHA match. An older
healthy build cannot satisfy the deployment check.

On failure, inspect SSM status and `/var/log/blueprint-deploy.log` through operator
SSM access. Logs are private and require redaction before sharing. Never print
`.env`, resolved Compose configuration or Docker environment into Actions logs.
No automated recovery or infrastructure operations are configured.

This remains a single educational host, without immutable image promotion or
high availability. Builds need external package access. The existing HTTP origin
hop and disposable root-disk PostgreSQL design are unchanged.

## Cleanup after the exercise

Both application and support stacks need separate authorized cleanup. Disable
the deployment variables before deleting the application. Deleting only the
application does not remove the support role/document. A reused shared OIDC
provider must not be deleted. The workflow never deletes infrastructure.

## Current AWS prerequisite

On November 4, 2026 (America/Guayaquil), the project reported FREE/ACTIVE. The
operator's administrator session was explicitly denied both
`iam:ListOpenIDConnectProviders` and `iam:GetOpenIDConnectProvider` by the
organization SCP `p-uzlwi2y7`, statement `DenyIAMActions`. IAM Access Troubleshooter
confirmed that the organizational deny overrides AdministratorAccess. No support
resources were provisioned while this prerequisite was blocked.

An administrator must resolve OIDC access before provisioning this template.
The new AWS experience documents advanced feature activation as the route to
manage organization restrictions. It requires an upgraded plan, cannot be
reversed, and removes managed spend limits. Do not activate it or change billing
as part of an automatic retry. Review the consequences with the project owner:
https://docs.aws.amazon.com/accounts/latest/reference/activate-advanced-features.html

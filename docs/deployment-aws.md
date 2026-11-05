# AWS educational deployment

For updates to the already running application through GitHub OIDC, see
[continuous deployment](continuous-deployment.md). The approval boundaries below
describe the original infrastructure bootstrap and change-set preparation.

This is a single-instance demonstration in `us-east-2`, using `blueprint-dev`.
CloudFront provides viewer HTTPS; Caddy proxies to FastAPI. PostgreSQL stays on
the encrypted 20 GiB EC2 root disk in a Docker named volume. Deleting or replacing
the instance deletes its data; this is intentional. Keep one backend process:
realtime room coordination currently lives in memory.

## Approval boundary

**Do not execute the previously prepared change set.** It contains the old
template. These local corrections do not update it. This document does not
authorize creating or executing any change set, or deleting the old proposal.

`deploy/aws/deploy.ps1` now prepares a `CREATE` change set only. It has no deploy
or execute operation. It requires a private parameter file outside the repository,
checks the regional prefix list and requires a full published commit SHA.

## Development credentials

Defaults are `BLUEPRINT_ENV=production` and `BLUEPRINT_SEED_DEMO=false`. Fresh
production databases have no demo users or interviews. Register an individual
user through the application. Seeding requires BOTH `BLUEPRINT_ENV=development`
and `BLUEPRINT_SEED_DEMO=true`; opting in outside development stops startup.

The local Compose file and `make backend` opt in explicitly. Local published
ports bind to loopback. The image and AWS Compose disable seeding. Existing users
are not deleted: never reuse a development database for deployment.

## CloudFront origin authentication

The security group still accepts port 80 only from CloudFront's regional managed
prefix list. Since that list includes other distributions, CloudFront also adds
`X-Blueprint-Origin-Token`. Caddy checks that private value on every path,
including WebSocket upgrade, and returns 403 for unauthorized requests. It strips
the token before forwarding to FastAPI, and its admin API is disabled. Compose
refuses to start without the token. A missing or malformed server token also
fails Caddy's matcher closed.

`OriginVerifyToken` is a required `NoEcho` parameter without a default: 64 lowercase
hexadecimal characters generated from 32 random bytes. It introduces no new AWS
service or resource. It follows the [AWS custom header pattern](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/restrict-access-to-load-balancer.html),
with Caddy enforcing the check instead of adding a load balancer. CloudFront
overwrites a viewer header of the same name. This token is separate from user login.

Bootstrap writes a root-owned `.env` under `/opt/blueprint` (directory 0700, file
0600), and a temporary private curl config under `/run`. It does not use shell
tracing, print configuration values, or automatically dump container logs. The
temporary curl config is removed on exit. Secret files are excluded from Git and
Docker build context. Never print `docker compose config` or `docker inspect`
with deployment credentials; use `config --quiet` for validation.

### Limits and rotation

`NoEcho` masks parameter displays. It does not hide values in every downstream
resource: authorized readers of EC2 UserData, CloudFront distribution configuration
and root/Docker state can recover this token. Restrict these permissions and keep
the operator parameter file private and outside Git. Do not publish its contents,
resolved UserData or screenshots that expose credentials.

The CloudFront-to-EC2 hop remains HTTP. The token blocks other distributions
without the shared value, but does not encrypt traffic or prevent replay if it
is disclosed. Viewer access remains HTTPS. Origin TLS needs a trusted certificate
and naming design; managed secrets or a different origin architecture require
additional scope and approval. Use only non-sensitive educational data here.

Rotation must update CloudFront and Caddy together. An ordinary parameter update
does not rerun EC2 UserData, so it does not rotate the running host automatically.
Plan a coordinated rotation and verify both sides before any future update.

## Readiness and signaling

The instance depends on the default route and subnet route-table association.
Its initial auto-assigned public IP permits bootstrap downloads. The EIP
association follows successful instance creation; removing the initial IP would
break that order.

`CreationPolicy` requires one signal within 30 minutes. UserData installs
`aws-cfn-bootstrap` first and limits all bootstrap work to 24 minutes, leaving time
for signal delivery. Package installation, Git fetch and image pulls have bounded
retries. Downloads, image build and HTTP checks have timeouts.

Success requires PostgreSQL readiness, an authenticated `/health/ready` request
that queries the database, a successful authenticated frontend request, and 403
responses for missing/invalid origin headers. An EXIT handler uses `cfn-signal`
to report the final result, retrying delivery up to five times. Failure or timeout
never sends success. If the helper cannot be installed or delivered, the stack
times out instead of completing successfully.

The helper uses stack-membership verification without adding IAM permissions;
see [cfn-signal](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/cfn-signal.html).
CloudFront is created after this signal and the EIP association, so public HTTPS
and browser collaboration must be tested separately after a future approved
deployment. CreationPolicy gates creation; it does not gate in-place EC2 updates
or rerun UserData on a normal reboot/update.

## Validating without AWS deployment

```powershell
# From backend/:
uv run --locked python -m pytest -q

# From repository root, with cfn-lint installed:
cfn-lint --format json --regions us-east-2 --template deploy/aws/blueprint-stack.yaml
aws cloudformation validate-template --profile blueprint-dev --region us-east-2 --template-body file://deploy/aws/blueprint-stack.yaml
```

`validate-template` provisions nothing and does not create a change set. It checks
syntax; it cannot prove runtime network access, package installation, stack
membership signaling or application behavior on EC2.

Deployment tests use Python with PyYAML (included with cfn-lint), plus Bash:

```powershell
python -m unittest discover -s deploy/aws/tests -v
# Opt in to a disposable LOCAL Docker project, never AWS:
$env:BLUEPRINT_RUN_DOCKER_TESTS = '1'
python -m unittest discover -s deploy/aws/tests -v
Remove-Item Env:BLUEPRINT_RUN_DOCKER_TESTS
```

The Bash harness substitutes the bootstrap payload and signaling transport. It
tests success, failure, timeout, retries and exhausted delivery without AWS calls.
Docker tests build a unique project with its own volume, random loopback ports
and ephemeral test credentials. They check origin rejection/acceptance, frontend,
database readiness, absent production demo login, WebSocket upgrade and backend
PostgreSQL integration. They remove only their own test containers and volume.

## Preparing a replacement later — NOT done yet

After review and separate authorization:

1. Confirm `us-east-2` in **AWS Settings > View all projects > Overview >
   Additional Info > Region** and credits/spend in **AWS Settings > Billing**.
2. Commit and publish the reviewed code manually with a normal push. Never
   rewrite published Lovable history. Use the full NEW published SHA; `d00e566`
   does not contain these corrections.
3. Leave the old change set unexecuted. Recheck the stack is still
   `REVIEW_IN_PROGRESS` with no resources before preparing another `CREATE`
   proposal against that stack. If its state changed, stop and review. Do not
   automatically delete or update anything.
4. Create a private parameter file outside Git. The following is a future-session
   example only; it was NOT executed during this task:

   ```powershell
   $privateDir = Join-Path $env:LOCALAPPDATA 'BlueprintDeploy'
   New-Item -ItemType Directory -Force -Path $privateDir | Out-Null
   $operatorSid = [Security.Principal.WindowsIdentity]::GetCurrent().User
   $privateAcl = [Security.AccessControl.DirectorySecurity]::new()
   $privateAcl.SetOwner($operatorSid)
   $privateAcl.SetAccessRuleProtection($true, $false)
   $privateAcl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new(
       $operatorSid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow'))
   Set-Acl -LiteralPath $privateDir -AclObject $privateAcl
   $parametersFile = Join-Path $privateDir 'blueprint.parameters.json'
   if (Test-Path -LiteralPath $parametersFile) { throw 'Choose a new file; preserve the existing token.' }
   $publishedSha = git rev-parse HEAD # Verify this SHA is already published.
   $prefixList = aws ec2 describe-managed-prefix-lists --profile blueprint-dev --region us-east-2 --filters Name=prefix-list-name,Values=com.amazonaws.global.cloudfront.origin-facing --query 'PrefixLists[0].PrefixListId' --output text
   if ($LASTEXITCODE -ne 0 -or $prefixList -notmatch '^pl-[a-f0-9]+$') { throw 'Prefix list lookup failed' }
   $randomBytes = [byte[]]::new(32)
   $randomSource = [Security.Cryptography.RandomNumberGenerator]::Create()
   try { $randomSource.GetBytes($randomBytes) } finally { $randomSource.Dispose() }
   $originToken = -join ($randomBytes | ForEach-Object { $_.ToString('x2') })
   @(
       @{ ParameterKey='RepoRef'; ParameterValue=$publishedSha }
       @{ ParameterKey='InstanceType'; ParameterValue='t3.small' }
       @{ ParameterKey='RootVolumeSize'; ParameterValue='20' }
       @{ ParameterKey='CloudFrontPrefixListId'; ParameterValue=$prefixList }
       @{ ParameterKey='OriginVerifyToken'; ParameterValue=$originToken }
   ) | ConvertTo-Json | Set-Content -Encoding utf8 -LiteralPath $parametersFile
   Remove-Variable originToken,randomBytes
   ```

5. Once authorized to prepare a proposal ONLY:

   ```powershell
   .\deploy\aws\deploy.ps1 -Profile blueprint-dev -Region us-east-2 -ParametersFile $parametersFile
   ```

   The script never executes it. Review `describe-change-set` and `describe-events`
   using its returned ARN. Check the origin parameter, creation policy, dependencies
   and published commit. Do not print the private parameter file. Executing the
   replacement, or deleting the old proposal, requires separate authorization.

## Remaining educational limits

No backups, failover, origin TLS, WAF, CloudFront access logs or durable CloudTrail
retention are added. Registration remains open without email verification or rate
limiting. Moving dependency versions and building on EC2 can still fail; pinned
build artifacts can be a later improvement. This design is for test data.

EC2, EBS, IPv4 and CloudFront can consume credits or incur charges after a future
approved deployment. Decide whether to keep or remove the demonstration after
use; deleting its instance intentionally deletes the database.

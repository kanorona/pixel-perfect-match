# Development and production environments

This repository uses one CloudFormation template for two independent stacks.
The existing `blueprint-interviews` stack remains **development**. A later,
separately authorized deployment will create `blueprint-interviews-production`
as **production**. This change only prepares local files: it does not call a
deployment API, create a change set, create resources, or modify secrets.

## Architecture and isolation

Each stack owns the same 14-resource architecture:

```text
Internet
   |
CloudFront (HTTPS + private origin header)
   |
stack-local Elastic IP :80, restricted to CloudFront prefix list
   |
EC2 / Caddy
   |
FastAPI ---- PostgreSQL
              stack-local Docker volume on encrypted gp3 root disk
```

CloudFormation creates a separate VPC, subnet, route table, internet gateway,
security group, instance role/profile, EC2 instance, encrypted root volume,
Elastic IP and CloudFront distribution for each stack. Logical IDs may be the
same because physical resources belong to different stacks. No output is
exported and the template contains no `Fn::ImportValue`, external database URL,
instance ID, VPC ID, subnet ID or security-group ID.

The bootstrap generates the PostgreSQL password independently on each EC2 host.
The database names are `blueprint_development` and `blueprint_production`, and
the named Docker volumes live on different encrypted EC2 root disks. Never copy
the `.env`, PostgreSQL volume, password or `OriginVerifyToken` between hosts.

| Setting | Development | Production |
| --- | --- | --- |
| Stack | `blueprint-interviews` | `blueprint-interviews-production` |
| `EnvironmentName` | `development` | `production` |
| VPC / subnet | `10.42.0.0/16` / `10.42.0.0/24` | `10.43.0.0/16` / `10.43.0.0/24` |
| EC2 | `t3.small` | `t3.medium` |
| Root gp3 | 20 GiB | 30 GiB |
| Origin token | private development value | new, unique private production value |
| PostgreSQL | local development volume | new empty production volume |

The CIDRs are intentionally different so a later network connection will not
begin with overlapping address space. CloudFront remains global; all Regional
resources must be created in the project's selected Region (`us-east-2` in the
current repository configuration).

## Parameter files and secret boundary

The files under `deploy/aws/environments/` are non-secret examples and are
deliberately invalid: their commit SHA, prefix-list ID and origin token are
placeholders. Copy the appropriate file outside the repository and replace all
placeholders there. `deploy.ps1` rejects a placeholder token, a non-40-character
commit, a mismatched environment, a mismatched regional prefix list, duplicate
keys and an in-repository private parameter file.

The production token must be generated independently from 32 cryptographically
random bytes. Do not read, rotate or reuse the development token. `NoEcho` masks
CloudFormation parameter displays but does not conceal the value from principals
allowed to read EC2 UserData or CloudFront origin configuration.

`BLUEPRINT_SEED_DEMO` remains `false` in both AWS environments. Passing
`BLUEPRINT_ENV=development` labels the development application; it does not
enable demo data. Production starts with a new empty database.

## Additional AWS resources and IAM

Production adds one independent copy of all 14 application-stack resources. It
does not add RDS, Secrets Manager, ECR, NAT Gateway, load balancers or a shared
database. Docker images continue to be built on the target EC2 instance.

The EC2 role remains stack-local and has only the AWS-managed
`AmazonSSMManagedInstanceCore` policy. IMDSv2 remains required. Port 80 remains
limited to the CloudFront origin-facing managed prefix list, and Caddy still
requires the separate origin token. No SSH key or inbound SSH rule is added.

CloudFormation deployment credentials need permission to create the resource
types already present in the template and to create/pass the stack-local EC2
role/profile; `CAPABILITY_IAM` remains explicit. Application instances do not
receive CloudFormation, IAM, secret-reading or cross-environment permissions.
The future production deployment support stack should reuse the existing GitHub
OIDC provider and create a separate SSM document/role scoped only to the
production instance. Never give the development deployment role both instance
IDs.

## Estimated additional monthly cost

Estimate dated 2026-11-09 for `us-east-2`, Linux On-Demand, 730 hours/month and
the proposed production size:

| Item | Rate | Estimate |
| --- | ---: | ---: |
| EC2 `t3.medium` | $0.0416/hour | $30.37 |
| 30 GB gp3 | $0.08/GB-month | $2.40 |
| One public IPv4 / Elastic IP | $0.005/hour | $3.65 |
| Fixed subtotal | | **$36.42/month** |

CloudFront requests/data transfer, internet egress, excess gp3 IOPS/throughput,
taxes and support are usage-dependent and excluded. CloudFront currently
includes a monthly shared free allowance of 1 TB data transfer and 10 million
HTTP/HTTPS requests, so a classroom workload may add little or no CloudFront
charge, but the allowance is shared across the project. The brief bootstrap
public IPv4 before EIP association can add a negligible transient charge.
Development's equivalent fixed estimate is about $20.43/month. Verify current
rates in AWS Pricing Calculator and check plan/spend status in AWS Settings >
Billing before deployment.

## Risks and security considerations

- PostgreSQL is durable only for the life of its EC2 root volume. Instance
  replacement or stack deletion loses the database; there are no backups.
- CloudFront-to-origin traffic is HTTP. The private header restricts origin use
  but is not transport encryption or end-user authentication.
- A single EC2 instance is not highly available, and builds on the host can fail
  because of external dependencies. This step intentionally does not add ECR.
- The CloudFront managed prefix list is not unique to this distribution; the
  independent origin token is the second control and must remain private.
- VPC/subnet CIDR containment is documented and tested locally, but
  CloudFormation parameter regexes cannot prove containment for arbitrary user
  overrides. Keep the reviewed pairs above.
- Production sizing is a starting point, not a measured capacity decision.
- The current OIDC prerequisite described in `continuous-deployment.md` must be
  resolved before adding production promotion permissions.

## Later production deployment procedure

The following is a future procedure, not authorization to run it now:

1. Confirm the selected Region in **AWS Settings > View all projects > Overview
   > Additional Info > Region**. Confirm the project is on the intended plan and
   review spend status/limits in **AWS Settings > Billing**.
2. Publish a reviewed commit normally. Do not rewrite Lovable-connected history.
3. Copy `production.parameters.example.json` to a private directory outside the
   repository. Insert the full published SHA, the selected Region's CloudFront
   prefix-list ID and a newly generated production token. Do not inspect or reuse
   the development token.
4. Prepare, but do not execute, the production `CREATE` change set:

   ```powershell
   .\deploy\aws\deploy.ps1 -Environment production -Profile blueprint-dev `
     -Region us-east-2 -ParametersFile C:\private\production.parameters.json
   ```

5. Review the change set. It must target `blueprint-interviews-production`, show
   14 creates and no updates/deletes, use `EnvironmentName=production`, the
   `10.43.0.0/16` VPC, the `10.43.0.0/24` subnet, and no imported resources.
6. Under a separate explicit authorization, execute the reviewed change set.
   Wait for `CREATE_COMPLETE`; then verify the outputs, SSM registration,
   CloudFront HTTPS, IMDSv2, origin-header rejection and a new empty database.
7. Decide whether to keep the resources after the exercise. Production adds
   ongoing cost even when idle.

For the later manual DEV -> PROD workflow, deploy a second copy of
`github-oidc-stack.yaml` scoped to the production `InstanceId`, reuse the shared
GitHub OIDC provider, and store its role/document/URL as production-environment
GitHub variables. Keep the current push workflow targeting only Development and
require a protected manual GitHub environment for Production. Until ECR is added
in the course's next step, promotion will rebuild the selected commit on the
production host; it is not yet immutable artifact promotion.

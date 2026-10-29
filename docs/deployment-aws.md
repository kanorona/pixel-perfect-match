# Deploying Blueprint Interviews to AWS

This deployment uses AWS CloudFormation to create a small, self-contained
production environment:

- **EC2** runs Docker Compose on one Amazon Linux instance.
- **PostgreSQL** runs in a private Docker network and stores data in a named
  Docker volume.
- **Caddy** is the only container exposed by the instance and proxies HTTP and
  WebSocket traffic to FastAPI.
- **CloudFront** provides the public HTTPS URL and forwards dynamic requests,
  cookies, authorization headers, and WebSocket upgrades without caching them.
- **Systems Manager Session Manager** provides administrative shell access, so
  no SSH port or EC2 key pair is required.

The single application replica is intentional. Realtime room membership and
broadcasts currently live in the FastAPI process memory. Scaling to multiple
replicas requires moving that coordination to Redis or another shared broker.

## Prerequisites

1. Install Docker Desktop, Git, AWS CLI v2, and optionally GNU Make.
2. Authenticate AWS CLI and choose a region:

   ```powershell
   aws configure
   aws sts get-caller-identity
   ```

   For AWS IAM Identity Center, use `aws configure sso` and `aws sso login`.
   Pass that profile to the deployment script with `-Profile <name>`.
3. Push the commit you want to deploy to a public branch or tag. The EC2
   instance clones `RepoUrl` and checks out `RepoRef`; it cannot see local-only
   commits or access a private repository without additional credentials.

## Validate and deploy

From the repository root:

```powershell
aws cloudformation validate-template --template-body file://deploy/aws/blueprint-stack.yaml
.\deploy\aws\deploy.ps1 -Region us-east-1 -RepoRef main
```

For an SSO profile:

```powershell
.\deploy\aws\deploy.ps1 -Region us-east-1 -Profile my-sso-profile -RepoRef main
```

The script resolves the region-specific CloudFront managed prefix list, deploys
the stack, waits for CloudFormation, and prints the outputs. Open the
`ApplicationUrl` output after CloudFront finishes propagating.

CloudFormation may report the EC2 instance as created before its user-data
bootstrap finishes. If the URL initially returns an error, wait a few minutes.
To inspect startup without opening SSH:

```powershell
aws ssm start-session --target <InstanceId>
sudo tail -n 200 /var/log/blueprint-bootstrap.log
cd /opt/blueprint
sudo docker compose -f docker-compose.aws.yaml ps
sudo docker compose -f docker-compose.aws.yaml logs --tail 200
```

## Updating the application

Commit and push the new code, then update `RepoRef` to that commit or branch.
For a simple classroom deployment, replace the instance by updating a parameter
that requires replacement or use Session Manager to pull and rebuild:

```sh
cd /opt/blueprint
sudo git fetch --all --prune
sudo git checkout <commit-or-tag>
sudo docker compose -f docker-compose.aws.yaml up -d --build
```

## Costs and deletion

EC2, its EBS volume, the Elastic IP, CloudFront traffic, and public IPv4 usage
can generate AWS charges. PostgreSQL data is stored on the instance's root EBS
volume and is deleted when the stack deletes the instance. Export important
data before teardown.

Delete all CloudFormation-managed resources with:

```powershell
aws cloudformation delete-stack --stack-name blueprint-interviews --region us-east-1
aws cloudformation wait stack-delete-complete --stack-name blueprint-interviews --region us-east-1
```

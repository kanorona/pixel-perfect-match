[CmdletBinding()]
param(
    [string]$StackName = "blueprint-interviews",
    [string]$Region = "us-east-1",
    [string]$Profile = "",
    [string]$RepoUrl = "https://github.com/kanorona/pixel-perfect-match.git",
    [string]$RepoRef = "main",
    [ValidateSet("t3.small", "t3.medium", "t3.large")]
    [string]$InstanceType = "t3.small"
)

$ErrorActionPreference = "Stop"
$template = Join-Path $PSScriptRoot "blueprint-stack.yaml"

if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
    throw "AWS CLI is not installed or is not available in PATH. Install AWS CLI v2 and authenticate before running this script."
}

if ($Profile) {
    $env:AWS_PROFILE = $Profile
}

aws sts get-caller-identity --region $Region | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "AWS authentication failed. Configure credentials or run 'aws sso login --profile <profile>'."
}

if ($RepoUrl -eq "https://github.com/kanorona/pixel-perfect-match.git" -and $RepoRef -eq "main" -and (Get-Command git -ErrorAction SilentlyContinue)) {
    git fetch origin main --quiet
    if ($LASTEXITCODE -ne 0) {
        throw "Could not refresh origin/main before deployment."
    }
    $localHead = git rev-parse HEAD
    $remoteHead = git rev-parse origin/main
    if ($localHead -ne $remoteHead) {
        throw "Local HEAD ($localHead) is not origin/main ($remoteHead). Push the deployment commit or pass a RepoRef that already exists on GitHub."
    }
}

aws cloudformation validate-template --region $Region --template-body "file://$template" | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "AWS rejected the CloudFormation template."
}

$prefixListId = aws ec2 describe-managed-prefix-lists `
    --region $Region `
    --filters Name=prefix-list-name,Values=com.amazonaws.global.cloudfront.origin-facing `
    --query "Entries[0].PrefixListId" `
    --output text
if ($LASTEXITCODE -ne 0 -or -not $prefixListId -or $prefixListId -eq "None") {
    throw "Could not resolve the CloudFront origin-facing managed prefix list in $Region."
}

Write-Host "Deploying stack '$StackName' to $Region..."
aws cloudformation deploy `
    --region $Region `
    --stack-name $StackName `
    --template-file $template `
    --capabilities CAPABILITY_IAM `
    --parameter-overrides `
        "RepoUrl=$RepoUrl" `
        "RepoRef=$RepoRef" `
        "InstanceType=$InstanceType" `
        "CloudFrontPrefixListId=$prefixListId" `
    --no-fail-on-empty-changeset
if ($LASTEXITCODE -ne 0) {
    throw "CloudFormation deployment failed. Inspect the stack events in the AWS console."
}

Write-Host "Stack outputs:"
aws cloudformation describe-stacks `
    --region $Region `
    --stack-name $StackName `
    --query "Stacks[0].Outputs[].{Name:OutputKey,Value:OutputValue}" `
    --output table

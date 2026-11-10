[CmdletBinding()]
param(
    [ValidateSet("development", "production")]
    [string]$Environment = "development",
    [string]$StackName,
    [ValidateSet("us-east-2")]
    [string]$Region = "us-east-2",
    [string]$Profile = "blueprint-dev",
    [Parameter(Mandatory)]
    [string]$ParametersFile
)

$ErrorActionPreference = "Stop"
$template = Join-Path $PSScriptRoot "blueprint-stack.yaml"
$stackNames = @{
    development = "blueprint-interviews"
    production  = "blueprint-interviews-production"
}
$networkCidrs = @{
    development = @{ Vpc = "10.42.0.0/16"; Subnet = "10.42.0.0/24" }
    production  = @{ Vpc = "10.43.0.0/16"; Subnet = "10.43.0.0/24" }
}
$expectedStackName = $stackNames[$Environment]
if ([string]::IsNullOrWhiteSpace($StackName)) {
    $StackName = $expectedStackName
}
elseif ($StackName -cne $expectedStackName) {
    throw "Environment '$Environment' must use stack '$expectedStackName'; refusing '$StackName'."
}

if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
    throw "AWS CLI is not installed or is not available in PATH. Install AWS CLI v2 and authenticate before running this script."
}

$awsContext = @("--profile", $Profile, "--region", $Region, "--no-cli-pager")
$resolvedParametersFile = (Resolve-Path -LiteralPath $ParametersFile).Path
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "../.."))
if ($resolvedParametersFile.StartsWith($repoRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Keep the private parameters file outside the repository."
}
$parameters = @(Get-Content -Raw -LiteralPath $resolvedParametersFile | ConvertFrom-Json)
$keys = @($parameters | ForEach-Object { $_.ParameterKey })
if (($keys | Select-Object -Unique).Count -ne $keys.Count) {
    throw "Duplicate parameter keys are not allowed."
}
$originToken = @($parameters | Where-Object ParameterKey -eq "OriginVerifyToken")
$sourceRef = @($parameters | Where-Object ParameterKey -eq "RepoRef")
$environmentName = @($parameters | Where-Object ParameterKey -eq "EnvironmentName")
$vpcCidr = @($parameters | Where-Object ParameterKey -eq "VpcCidr")
$publicSubnetCidr = @($parameters | Where-Object ParameterKey -eq "PublicSubnetCidr")
if ($originToken.Count -ne 1 -or $originToken[0].ParameterValue -cnotmatch '^[a-f0-9]{64}$') {
    throw "The private file must contain one OriginVerifyToken with 64 lowercase hexadecimal characters."
}
if ($sourceRef.Count -ne 1 -or $sourceRef[0].ParameterValue -cnotmatch '^[a-f0-9]{40}$') {
    throw "RepoRef must be the full SHA of an already published commit."
}
if ($environmentName.Count -ne 1 -or $environmentName[0].ParameterValue -cne $Environment) {
    throw "The parameters file must contain one EnvironmentName equal to '$Environment'."
}
$expectedNetwork = $networkCidrs[$Environment]
if ($vpcCidr.Count -ne 1 -or $vpcCidr[0].ParameterValue -cne $expectedNetwork.Vpc) {
    throw "Environment '$Environment' must use VpcCidr '$($expectedNetwork.Vpc)'."
}
if ($publicSubnetCidr.Count -ne 1 -or $publicSubnetCidr[0].ParameterValue -cne $expectedNetwork.Subnet) {
    throw "Environment '$Environment' must use PublicSubnetCidr '$($expectedNetwork.Subnet)'."
}

aws @awsContext sts get-caller-identity | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "AWS authentication failed. Renew the session for the selected profile."
}

aws @awsContext cloudformation validate-template --template-body "file://$template" | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "AWS rejected the CloudFormation template."
}

$prefixListId = aws @awsContext ec2 describe-managed-prefix-lists `
    --filters Name=prefix-list-name,Values=com.amazonaws.global.cloudfront.origin-facing `
    --query "PrefixLists[0].PrefixListId"  `
    --output text
if ($LASTEXITCODE -ne 0 -or -not $prefixListId -or $prefixListId -eq "None") {
    throw "Could not resolve the CloudFront origin-facing managed prefix list in $Region."
}

$providedPrefixList = @($parameters | Where-Object ParameterKey -eq "CloudFrontPrefixListId")
if ($providedPrefixList.Count -ne 1 -or $providedPrefixList[0].ParameterValue -ne $prefixListId) {
    throw "CloudFrontPrefixListId in the private parameters file does not match the selected Region."
}

$changeSetName = "review-" + $sourceRef[0].ParameterValue.Substring(0, 7) + "-" + [guid]::NewGuid().ToString("N")
Write-Host "Preparing $Environment CREATE change set '$changeSetName' for '$StackName' in $Region. Execution is separate."
# Deliberately preview only. This script never executes a change set.
aws @awsContext cloudformation create-change-set `
    --stack-name $StackName `
    --change-set-name $changeSetName `
    --change-set-type CREATE `
    --template-body "file://$template" `
    --capabilities CAPABILITY_IAM `
    --parameters "file://$resolvedParametersFile"
if ($LASTEXITCODE -ne 0) {
    throw "Could not prepare the change set. No execution was requested."
}
Write-Host "Review describe-change-set and describe-events before requesting execution approval."

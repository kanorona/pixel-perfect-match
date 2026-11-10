#!/usr/bin/env bash
set -euo pipefail

: "${AWS_REGION:?}" "${ECR_REPOSITORY_URI:?}" "${GITHUB_SHA:?}" "${GITHUB_OUTPUT:?}"
[[ "$AWS_REGION" == "us-east-2" ]]
[[ "$GITHUB_SHA" =~ ^[a-f0-9]{40}$ ]]
[[ "$ECR_REPOSITORY_URI" =~ ^[0-9]{12}\.dkr\.ecr\.us-east-2\.amazonaws\.com/[a-z0-9]+([._/-][a-z0-9]+)*$ ]]

registry="${ECR_REPOSITORY_URI%%/*}"
repository="${ECR_REPOSITORY_URI#*/}"
short_sha="${GITHUB_SHA:0:7}"
image_tag="$(date -u +%Y%m%d-%H%M%S)-${short_sha}"
image_tagged="${ECR_REPOSITORY_URI}:${image_tag}"

aws ecr get-login-password --region "$AWS_REGION" |
  docker login --username AWS --password-stdin "$registry" >/dev/null
docker build --build-arg "BLUEPRINT_REVISION=$GITHUB_SHA" --tag "$image_tagged" .
docker push "$image_tagged"

image_digest=$(aws ecr describe-images --region "$AWS_REGION" \
  --repository-name "$repository" --image-ids "imageTag=$image_tag" \
  --query 'imageDetails[0].imageDigest' --output text)
[[ "$image_digest" =~ ^sha256:[a-f0-9]{64}$ ]]

python - "$GITHUB_SHA" "$ECR_REPOSITORY_URI" "$image_tag" "$image_digest" <<'PY'
import json
import pathlib
import sys

revision, repository_uri, tag, digest = sys.argv[1:]
pathlib.Path("deployment-manifest.json").write_text(
    json.dumps({
        "revision": revision,
        "repository_uri": repository_uri,
        "tag": tag,
        "digest": digest,
        "image": f"{repository_uri}@{digest}",
    }, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY

{
  printf 'tag=%s\n' "$image_tag"
  printf 'digest=%s\n' "$image_digest"
  printf 'repository_uri=%s\n' "$ECR_REPOSITORY_URI"
} >> "$GITHUB_OUTPUT"
printf 'Published immutable image `%s@%s` (tag `%s`).\n' \
  "$ECR_REPOSITORY_URI" "$image_digest" "$image_tag" >> "$GITHUB_STEP_SUMMARY"

#!/usr/bin/env bash
set -euo pipefail
: "${DEPLOY_INSTANCE_ID:?}" "${DEPLOY_DOCUMENT:?}" "${GITHUB_SHA:?}"
[[ "$GITHUB_SHA" =~ ^[a-f0-9]{40}$ ]]
command_id=$(aws ssm send-command --region us-east-2 \
  --instance-ids "$DEPLOY_INSTANCE_ID" --document-name "$DEPLOY_DOCUMENT" \
  --comment "Blueprint deploy ${GITHUB_SHA}" --timeout-seconds 1800 \
  --parameters "{\"commit\":[\"$GITHUB_SHA\"]}" \
  --query Command.CommandId --output text)
echo "SSM deployment command: $command_id"
# The built-in waiter times out before a cold image build can finish.
for attempt in $(seq 1 180); do
  if result=$(aws ssm get-command-invocation --region us-east-2 \
    --command-id "$command_id" --instance-id "$DEPLOY_INSTANCE_ID" \
    --query '{Status:Status,Code:ResponseCode}' --output json 2>/dev/null); then
    status=$(printf '%s' "$result" | python -c 'import json,sys; print(json.load(sys.stdin)["Status"])')
    case "$status" in
      Success) echo "Deployment succeeded for $GITHUB_SHA"; exit 0 ;;
      Pending|InProgress|Delayed) ;;
      *) echo "Deployment failed: $status. Inspect private EC2 deployment logs; no recovery was attempted." >&2; exit 1 ;;
    esac
  fi
  sleep 10
done
echo 'Deployment status timed out; inspect the command before taking further action.' >&2
exit 1

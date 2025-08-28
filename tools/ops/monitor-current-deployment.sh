#!/bin/bash
# Monitor current deployment

RUN_ID=16404053064
REPO="CIRISAI/CIRISAgent"

echo "=== Monitoring Deployment $RUN_ID ==="
echo "Time: $(date)"
echo ""

# Get current status
STATUS=$(gh run view $RUN_ID --repo $REPO --json status,conclusion,jobs 2>/dev/null)

if [ $? -eq 0 ]; then
    RUN_STATUS=$(echo "$STATUS" | jq -r '.status')
    CONCLUSION=$(echo "$STATUS" | jq -r '.conclusion // "pending"')

    echo "Overall Status: $RUN_STATUS"
    echo "Conclusion: $CONCLUSION"
    echo ""
    echo "Jobs:"
    echo "$STATUS" | jq -r '.jobs[] | "  - \(.name): \(.status) (\(.conclusion // "running"))"'

    # Check specific job details
    echo ""
    echo "Checking for deployment job..."
    DEPLOY_JOB=$(echo "$STATUS" | jq -r '.jobs[] | select(.name == "Deploy to Production")')

    if [ -n "$DEPLOY_JOB" ]; then
        DEPLOY_STATUS=$(echo "$DEPLOY_JOB" | jq -r '.status')
        DEPLOY_CONCLUSION=$(echo "$DEPLOY_JOB" | jq -r '.conclusion // "pending"')
        echo "Deploy to Production: $DEPLOY_STATUS ($DEPLOY_CONCLUSION)"
    else
        echo "Deploy job not started yet"
    fi

    # Show timing
    echo ""
    CREATED_AT=$(gh run view $RUN_ID --repo $REPO --json createdAt --jq '.createdAt')
    echo "Started: $CREATED_AT"

    # Calculate duration
    START_TIME=$(date -d "$CREATED_AT" +%s 2>/dev/null || date -j -f "%Y-%m-%dT%H:%M:%SZ" "$CREATED_AT" +%s 2>/dev/null || echo "0")
    CURRENT_TIME=$(date +%s)
    if [ "$START_TIME" -ne "0" ]; then
        DURATION=$((CURRENT_TIME - START_TIME))
        DURATION_MIN=$((DURATION / 60))
        echo "Running for: $DURATION_MIN minutes"
    fi
else
    echo "Error fetching deployment status"
fi

echo ""
echo "To view logs: gh run view $RUN_ID --repo $REPO --log"
echo "To check production: ssh -i ~/.ssh/ciris_deploy root@108.61.119.117"

#!/bin/bash
# Prevent direct pushes to main branch
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$BRANCH" = "main" ]; then
    echo "❌ Direct push to main blocked. Please create a PR."
    echo "Use: gh pr create --title 'Your Title' --body 'Your Description'"
    exit 1
fi
exit 0

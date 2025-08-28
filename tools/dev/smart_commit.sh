#!/bin/bash
# Smart commit script that handles pre-commit hook modifications
# Usage: ./tools/smart_commit.sh "commit message"

set -e

if [ -z "$1" ]; then
    echo "Usage: $0 \"commit message\""
    exit 1
fi

COMMIT_MSG="$1"
MAX_ATTEMPTS=5
ATTEMPT=0

echo "🚀 Smart Commit: Starting commit process..."

# Initial staging
git add -A

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    ATTEMPT=$((ATTEMPT + 1))
    echo "📝 Attempt $ATTEMPT of $MAX_ATTEMPTS..."

    # Try to commit
    if git commit -m "$COMMIT_MSG" 2>&1 | tee /tmp/commit_output.txt; then
        # Check if files were modified by hooks
        if grep -q "files were modified by this hook" /tmp/commit_output.txt; then
            echo "🔄 Files modified by hooks, re-staging..."
            git add -A
            continue
        else
            echo "✅ Commit successful!"
            break
        fi
    else
        # Check if there's nothing to commit
        if git diff --staged --quiet; then
            echo "✅ All changes committed successfully!"
            break
        else
            echo "❌ Commit failed, checking for hook modifications..."
            # Check for modified files
            if ! git diff --quiet; then
                echo "🔄 Unstaged changes detected, re-staging..."
                git add -A
                continue
            else
                echo "❌ Commit failed for unknown reason"
                exit 1
            fi
        fi
    fi
done

if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
    echo "❌ Failed after $MAX_ATTEMPTS attempts"
    exit 1
fi

# Show final status
echo ""
echo "📊 Final status:"
git log --oneline -1
git status --short

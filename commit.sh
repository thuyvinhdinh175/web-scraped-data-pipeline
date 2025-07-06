#!/bin/bash
# Make this script executable with: chmod +x commit.sh

# Simple script to commit and push changes to Git

# Check if a commit message was provided
if [ -z "$1" ]; then
  echo "Please provide a commit message"
  echo "Usage: ./commit.sh 'Your commit message'"
  exit 1
fi

# Add all changes
git add .

# Commit with the provided message
git commit -m "$1"

# Push to the remote repository
git push

echo "Changes committed and pushed successfully!"

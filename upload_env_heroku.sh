#!/usr/bin/env bash

if [ -z "$1" ]; then
    echo "Usage: ./upload_env_heroku.sh <heroku-app-name>"
    exit 1
fi

APP_NAME="$1"

if [ ! -f .env ]; then
    echo "Error: .env file not found."
    exit 1
fi

echo "Uploading .env variables to Heroku app: $APP_NAME..."

# Export and set config vars on Heroku from .env
heroku config:set $(grep -v '^#' .env | xargs) -a "$APP_NAME"

echo "✅ Environment variables uploaded successfully to $APP_NAME!"

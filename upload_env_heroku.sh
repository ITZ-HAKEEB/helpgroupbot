#!/usr/bin/env bash

if [ -z "$1" ]; then
    echo "Usage: ./upload_env_heroku.sh <heroku-app-name>"
    exit 1
fi

APP_NAME="$1"

echo "Uploading .env variables to Heroku app: $APP_NAME..."

heroku config:set \
  BOT_TOKEN="7745087703:AAGauO_TqU7YCzA1UlIj7a4P1Or5cP_zzQ4" \
  LOG_CHANNEL_ID="-1004469112001" \
  OWNER_ID="7408854697" \
  START_IMG="https://i.ibb.co/RTRMvHCR/41-Doraemon-Wallpapers-Free-download-Best-Collection.jpg" \
  MONGODB_URI="mongodb+srv://n87160882_db_user:nRXYTjLSWZdnW0F1@doraemon.xnwbxq5.mongodb.net/?appName=Doraemon" \
  OPENROUTER_API_KEY="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" \
  AI_BASE_URL="https://openrouter.ai/api/v1" \
  AI_MODEL="meta-llama/llama-3.3-70b-instruct:free" \
  API_ID="34090005" \
  API_HASH="fa8f8d2ae9624eab5892ae9c03144ba6" \
  STRING_SESSION="1BVtsOLgBu7xuIGRHPlHOrcC0ETAc71ebLPAJD0BxZM6I8zU9iF3tiJrXBU40x1HK_7mWibUtBWy0eHQpWrdNZKvHF7FeCOwGAPKXLQ8le_txcSSXjq1vIw-D59AxmPMScEuYaw3jbvfloVNnuo3PZ_DG7cKCng4BGRQij3Ss0rI4OhIDxq-C-F7FTSAc2oq7hjeJzYY83m1Jg6mj6pl5z8_XLGsWRMkOBqnSXBGOckDgEcqQkWG7fZTvypydD9NGjNEYNfKWlnM5bnj5jh5y4Gma4f2NYRef39SgpGtZV6lKU11cZsUw8Gx-F1lmcsvM4ao48AP5qm-Y1BOBLVH2V7uiAg2at0M=" \
  -a "$APP_NAME"

echo "✅ Environment variables uploaded successfully to $APP_NAME!"

#!/bin/bash

# Start iMessage watcher for Alyn
# This script starts the Node.js watcher that monitors incoming iMessages

set -e

echo "🚀 Starting Alyn iMessage Watcher..."
echo ""
echo "📱 Make sure you have:"
echo "   ✓ iMessage configured on this Mac"
echo "   ✓ Full Disk Access granted to your IDE/Terminal"
echo "   ✓ Node.js dependencies installed (npm install)"
echo ""
echo "Press Ctrl+C to stop the watcher"
echo ""

# Navigate to project root
cd "$(dirname "$0")"

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "❌ node_modules not found. Running npm install..."
    npm install
fi

# Check if Node.js is available
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed. Please install Node.js first."
    exit 1
fi

# Rebuild better-sqlite3 for current Node.js version
echo "🔧 Rebuilding better-sqlite3 for Node.js $(node --version)..."
npm rebuild better-sqlite3 --silent

echo ""

# Start the watcher
npm run watch

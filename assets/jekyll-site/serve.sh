#!/bin/bash

echo "========================================="
echo "Jekyll Local Development Server (Docker)"
echo "=========================================="
echo ""

# Check if podman or docker is available
if command -v podman &> /dev/null; then
    CONTAINER_CMD="podman"
    COMPOSE_CMD="podman-compose"
    echo "✓ Using Podman"
elif command -v docker &> /dev/null; then
    CONTAINER_CMD="docker"
    COMPOSE_CMD="docker compose"
    echo "✓ Using Docker"
else
    echo "❌ Error: Neither Docker nor Podman found."
    echo "Please install Docker or Podman to run Jekyll locally."
    exit 1
fi

echo ""
echo "🚀 Starting Jekyll server..."
echo ""
echo "The site will be available at:"
echo "  👉 http://localhost:4000"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Run with docker-compose or podman compose
if [ "$CONTAINER_CMD" = "podman" ]; then
    podman compose up --build
else
    docker compose up --build
fi

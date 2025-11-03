#!/bin/bash

# Jekyll Local Development Server (Native Ruby)
echo "========================================"
echo "Jekyll Local Development Server (Native)"
echo "========================================"

# Copy README.md from root to be served as index page
echo "📄 Copying README.md from root..."
cp ../README.md ./index.md

# Copy images directory from root assets
echo "🖼️  Copying images from assets/images..."
if [ -d "../images" ]; then
    cp -r ../images ./
fi

echo ""
echo "🚀 Starting Jekyll server with native Ruby..."
echo ""
echo "The site will be available at:"
echo "  👉 http://localhost:4000"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Check if Ruby and bundler are available
if ! command -v ruby &> /dev/null; then
    echo "❌ Ruby not found. Please install Ruby:"
    echo "   brew install ruby"
    exit 1
fi

if ! command -v bundle &> /dev/null; then
    echo "❌ Bundler not found. Installing..."
    gem install bundler
fi

# Install gems if needed
if [ ! -f "Gemfile.lock" ]; then
    echo "📦 Installing gems..."
    bundle install
fi

# Start Jekyll
bundle exec jekyll serve --livereload

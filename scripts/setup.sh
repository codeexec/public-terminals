#!/bin/bash

# Terminal Server Setup Script
# This script helps you get the Terminal Server up and running quickly

set -e

echo "======================================"
echo "Terminal Server Setup"
echo "======================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ $1${NC}"
}

# Check prerequisites
echo "Checking prerequisites..."

if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed. Please install Docker first."
    exit 1
fi
print_success "Docker is installed"

if ! docker compose version &> /dev/null; then
    print_error "Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi
print_success "Docker Compose is installed"

# Check if Docker is running
if ! docker info &> /dev/null; then
    print_error "Docker is not running. Please start Docker."
    exit 1
fi
print_success "Docker is running"

echo ""

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    print_info "Creating .env file from .env.example..."
    cp .env.example .env
    print_success ".env file created"
else
    print_info ".env file already exists, skipping..."
fi

echo ""

# Build terminal container image
print_info "Building terminal container image (this may take a few minutes)..."
cd terminal-container
docker build -t terminal-server:latest . > /dev/null 2>&1
cd ..
print_success "Terminal container image built successfully"

echo ""

# Build API server image
print_info "Building API server image..."
docker build -t terminal-server-app:latest . > /dev/null 2>&1
print_success "API server image built successfully"

echo ""

# Start services
print_info "Starting services with Docker Compose..."
docker compose up -d
print_success "Services started"

echo ""

# Wait for services to be ready
print_info "Waiting for services to be ready (30 seconds)..."
sleep 5

# Check API health
for i in {1..10}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        print_success "API server is ready!"
        break
    fi
    if [ $i -eq 10 ]; then
        print_error "API server failed to start. Check logs with: docker-compose logs api"
        exit 1
    fi
    sleep 3
done

echo ""
echo "======================================"
echo "Setup Complete!"
echo "======================================"
echo ""
echo "Services running:"
echo "  • API Server: http://localhost:8000"
echo "  • API Docs:   http://localhost:8000/docs"
echo "  • Database:   localhost:5432"
echo "  • Redis:      localhost:6379"
echo ""
echo "Quick Start:"
echo "  1. Open API docs: http://localhost:8000/docs"
echo "  2. Create a terminal: make test"
echo "  3. Run test suite: python test_api.py"
echo ""
echo "Useful commands:"
echo "  • View logs:       docker compose logs -f"
echo "  • Stop services:   docker compose down"
echo "  • Restart:         docker compose restart"
echo "  • Clean up:        make clean"
echo ""
echo "For more information, see README.md and QUICKSTART.md"
echo ""

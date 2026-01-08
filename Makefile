.PHONY: help build-terminal build-api up down logs clean test test-full test-api setup shell

help:
	@echo "Terminal Server - Available Commands:"
	@echo ""
	@echo "Build & Deploy:"
	@echo "  make build-terminal  - Build terminal container image"
	@echo "  make build-api       - Build API server image"
	@echo "  make up              - Start all services"
	@echo "  make down            - Stop all services"
	@echo "  make setup           - Run initial setup script"
	@echo ""
	@echo "Logs & Monitoring:"
	@echo "  make logs            - View logs from all services"
	@echo "  make logs-api        - View API server logs"
	@echo "  make logs-web        - View Web server logs"
	@echo "  make logs-celery     - View Celery worker logs"
	@echo ""
	@echo "Testing:"
	@echo "  make test            - Quick API test (create terminal)"
	@echo "  make test-full       - Full integration test (bash script)"
	@echo "  make test-api        - Run Python API tests"
	@echo ""
	@echo "Utilities:"
	@echo "  make shell           - Open shell in API container"
	@echo "  make db-shell        - Open PostgreSQL shell"
	@echo "  make clean           - Remove all containers and volumes"

build-terminal:
	@echo "Building terminal container image..."
	cd terminal-container && docker build -t terminal-server:latest .
	@echo "Terminal container image built successfully!"

build-api:
	@echo "Building API server image..."
	docker build -f Dockerfile -t terminal-api:latest .
	@echo "API server image built successfully!"

build: build-terminal build-api

up:
	@echo "Starting services..."
	docker compose up -d
	@echo "Services started!"
	@echo "  Web UI:    http://localhost:8001"
	@echo "  API:       http://localhost:8000"
	@echo "  API docs:  http://localhost:8000/docs"

down:
	@echo "Stopping services..."
	docker compose down
	@echo "Services stopped!"

logs:
	docker compose logs -f

logs-api:
	docker compose logs -f api-server

logs-web:
	docker compose logs -f web-server

logs-celery:
	docker compose logs -f celery-worker celery-beat

clean:
	@echo "Cleaning up..."
	docker compose down -v
	@echo "Cleanup complete!"

test:
	@echo "Creating test terminal..."
	@curl -X POST http://localhost:8000/api/v1/terminals -H "Content-Type: application/json" -d '{}' | jq
	@echo "\nList all terminals:"
	@curl -s http://localhost:8000/api/v1/terminals | jq

test-full:
	@echo "Running full integration test..."
	./scripts/run_test.sh

test-api:
	@echo "Running Python API tests..."
	python3 tests/test_api.py

setup:
	@echo "Running setup script..."
	./scripts/setup.sh

shell:
	docker compose exec api-server /bin/bash

db-shell:
	docker compose exec postgres psql -U postgres -d terminal_server

init:
	@echo "Initializing project..."
	cp .env.example .env
	@echo "Building images..."
	make build
	@echo "Starting services..."
	make up
	@echo "\nWaiting for services to be ready..."
	sleep 10
	@echo "\nInitialization complete!"
	@echo "  Web UI:    http://localhost:8001"
	@echo "  API:       http://localhost:8000"
	@echo "  API docs:  http://localhost:8000/docs"

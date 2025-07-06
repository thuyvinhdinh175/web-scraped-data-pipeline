# Web-Scraped Data Pipeline Makefile
# Provides convenient commands for development and deployment

.PHONY: help setup install test lint format clean docker-up docker-down docker-logs run-pipeline run-scraper run-validator run-transformer dashboard

# Default target
help:
	@echo "🚀 Web-Scraped Data Pipeline - Available Commands"
	@echo "================================================"
	@echo ""
	@echo "📦 Setup & Installation:"
	@echo "  setup          - Complete environment setup (creates venv, installs deps, sets up env)"
	@echo "  install        - Install Python dependencies"
	@echo "  install-dev    - Install development dependencies"
	@echo ""
	@echo "🐳 Docker Commands:"
	@echo "  docker-up      - Start all Docker services"
	@echo "  docker-down    - Stop all Docker services"
	@echo "  docker-logs    - View Docker service logs"
	@echo "  docker-build   - Build Docker images"
	@echo "  docker-clean   - Clean up Docker resources"
	@echo ""
	@echo "🔧 Development:"
	@echo "  test           - Run tests"
	@echo "  test-cov       - Run tests with coverage"
	@echo "  lint           - Run linting checks"
	@echo "  format         - Format code with black and isort"
	@echo "  type-check     - Run type checking with mypy"
	@echo ""
	@echo "🚀 Pipeline Execution:"
	@echo "  run-pipeline   - Run complete pipeline"
	@echo "  run-scraper    - Run web scraper only"
	@echo "  run-validator  - Run data validation only"
	@echo "  run-transformer - Run data transformation only"
	@echo "  dashboard      - Start Streamlit dashboard"
	@echo ""
	@echo "🧹 Maintenance:"
	@echo "  clean          - Clean up temporary files and caches"
	@echo "  clean-data     - Clean up data directories"
	@echo "  clean-logs     - Clean up log files"
	@echo ""

# Setup and Installation
setup: install setup-env
	@echo "✅ Environment setup complete!"

install:
	@echo "📦 Installing Python dependencies..."
	python -m pip install --upgrade pip
	pip install -e .
	@echo "✅ Dependencies installed!"

install-dev:
	@echo "📦 Installing development dependencies..."
	pip install -e ".[dev,test,docs]"
	@echo "✅ Development dependencies installed!"

setup-env:
	@echo "⚙️ Setting up environment..."
	@if [ ! -f .env ]; then \
		if [ -f env.example ]; then \
			cp env.example .env; \
			echo "✅ Created .env from env.example"; \
		else \
			echo "⚠️  env.example not found, creating basic .env"; \
			echo "ENVIRONMENT=development" > .env; \
			echo "DEBUG=True" >> .env; \
			echo "LOG_LEVEL=INFO" >> .env; \
		fi; \
	else \
		echo "✅ .env file already exists"; \
	fi
	@mkdir -p data/raw data/silver data/gold logs temp
	@echo "✅ Environment setup complete!"

# Docker Commands
docker-up:
	@echo "🐳 Starting Docker services..."
	docker-compose up -d --build
	@echo "✅ Docker services started!"
	@echo "🌐 Services available at:"
	@echo "  • Airflow: http://localhost:8080 (admin/admin)"
	@echo "  • Streamlit: http://localhost:8501"
	@echo "  • MinIO: http://localhost:9001 (minio/minio123)"
	@echo "  • Spark: http://localhost:8181"
	@echo "  • Whoogle: http://localhost:5000"

docker-down:
	@echo "🐳 Stopping Docker services..."
	docker-compose down
	@echo "✅ Docker services stopped!"

docker-logs:
	@echo "📋 Docker service logs:"
	docker-compose logs -f

docker-build:
	@echo "🔨 Building Docker images..."
	docker-compose build --no-cache
	@echo "✅ Docker images built!"

docker-clean:
	@echo "🧹 Cleaning Docker resources..."
	docker-compose down -v --remove-orphans
	docker system prune -f
	@echo "✅ Docker cleanup complete!"

# Development Commands
test:
	@echo "🧪 Running tests..."
	pytest tests/ -v

test-cov:
	@echo "🧪 Running tests with coverage..."
	pytest tests/ --cov=src --cov-report=html --cov-report=term-missing

lint:
	@echo "🔍 Running linting checks..."
	flake8 src/ tests/
	@echo "✅ Linting complete!"

format:
	@echo "🎨 Formatting code..."
	black src/ tests/
	isort src/ tests/
	@echo "✅ Code formatting complete!"

type-check:
	@echo "🔍 Running type checks..."
	mypy src/
	@echo "✅ Type checking complete!"

# Pipeline Execution
run-pipeline:
	@echo "🚀 Running complete pipeline..."
	python src/run_pipeline.py --stage all

run-scraper:
	@echo "🕷️ Running web scraper..."
	python src/run_pipeline.py --stage scrape

run-validator:
	@echo "✅ Running data validation..."
	python src/run_pipeline.py --stage validate

run-transformer:
	@echo "🔄 Running data transformation..."
	python src/run_pipeline.py --stage transform

dashboard:
	@echo "📊 Starting Streamlit dashboard..."
	streamlit run streamlit_app/dashboard.py

# Maintenance Commands
clean:
	@echo "🧹 Cleaning up temporary files..."
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	rm -rf build/ dist/ .coverage htmlcov/
	@echo "✅ Cleanup complete!"

clean-data:
	@echo "🧹 Cleaning data directories..."
	rm -rf data/raw/* data/silver/* data/gold/*
	@echo "✅ Data cleanup complete!"

clean-logs:
	@echo "🧹 Cleaning log files..."
	rm -rf logs/*
	@echo "✅ Log cleanup complete!"

# Utility Commands
check-status:
	@echo "📊 Checking service status..."
	@echo "Docker containers:"
	docker-compose ps
	@echo ""
	@echo "Data directories:"
	@ls -la data/
	@echo ""
	@echo "Environment file:"
	@if [ -f .env ]; then echo "✅ .env file exists"; else echo "❌ .env file missing"; fi

logs:
	@echo "📋 Recent logs:"
	@if [ -d logs ]; then tail -n 50 logs/*.log 2>/dev/null || echo "No log files found"; else echo "No logs directory found"; fi

# Development workflow
dev-setup: setup install-dev
	@echo "✅ Development environment ready!"

dev-test: format lint type-check test
	@echo "✅ All development checks passed!"

# Production deployment helpers
prod-build:
	@echo "🏗️ Building for production..."
	docker-compose -f docker-compose.yml -f docker-compose.prod.yml build
	@echo "✅ Production build complete!"

prod-deploy:
	@echo "🚀 Deploying to production..."
	docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
	@echo "✅ Production deployment complete!"

# Database commands
db-init:
	@echo "🗄️ Initializing database..."
	docker-compose exec postgres psql -U airflow -d airflow -c "SELECT version();"
	@echo "✅ Database initialized!"

db-backup:
	@echo "💾 Creating database backup..."
	docker-compose exec postgres pg_dump -U airflow airflow > backup_$(date +%Y%m%d_%H%M%S).sql
	@echo "✅ Database backup created!"

# Monitoring commands
monitor:
	@echo "📊 Monitoring services..."
	@echo "Docker containers:"
	docker-compose ps
	@echo ""
	@echo "Resource usage:"
	docker stats --no-stream
	@echo ""
	@echo "Recent logs:"
	docker-compose logs --tail=20

# Quick start for new developers
quickstart: setup docker-up
	@echo "🎉 Quick start complete!"
	@echo "Your environment is ready to use!"
	@echo "Check the help command for available options: make help" 
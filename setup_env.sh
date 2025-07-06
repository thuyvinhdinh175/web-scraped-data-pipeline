#!/bin/bash

# Web-Scraped Data Pipeline Environment Setup Script
# This script sets up the complete environment for the data pipeline project

set -e  # Exit on any error

echo "🚀 Setting up Web-Scraped Data Pipeline Environment"
echo "=================================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}[SETUP]${NC} $1"
}

# Check if running on macOS, Linux, or Windows
detect_os() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        OS="linux"
    elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]]; then
        OS="windows"
    else
        OS="unknown"
    fi
    print_status "Detected OS: $OS"
}

# Check prerequisites
check_prerequisites() {
    print_header "Checking prerequisites..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    print_status "✓ Docker is installed"
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    print_status "✓ Docker Compose is installed"
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is not installed. Please install Python 3 first."
        exit 1
    fi
    print_status "✓ Python 3 is installed"
    
    # Check if Docker is running
    if ! docker info &> /dev/null; then
        print_error "Docker is not running. Please start Docker first."
        exit 1
    fi
    print_status "✓ Docker is running"
}

# Create environment file
setup_env_file() {
    print_header "Setting up environment configuration..."
    
    if [ ! -f .env ]; then
        if [ -f env.example ]; then
            cp env.example .env
            print_status "Created .env file from env.example"
        else
            print_warning "env.example not found. Creating basic .env file..."
            cat > .env << EOF
# Basic environment configuration
ENVIRONMENT=development
DEBUG=True
LOG_LEVEL=INFO

# MinIO Configuration
MINIO_ROOT_USER=minio
MINIO_ROOT_PASSWORD=minio123
MINIO_ENDPOINT=http://localhost:9000
MINIO_BUCKET=web-scraped-data-pipeline

# Airflow Configuration
AIRFLOW_USERNAME=admin
AIRFLOW_PASSWORD=admin
AIRFLOW_EMAIL=admin@example.com

# Storage Configuration
STORAGE_TYPE=minio
LOCAL_DATA_PATH=./data
RAW_DATA_PATH=./data/raw
SILVER_DATA_PATH=./data/silver
GOLD_DATA_PATH=./data/gold
EOF
            print_status "Created basic .env file"
        fi
    else
        print_status "✓ .env file already exists"
    fi
}

# Create necessary directories
create_directories() {
    print_header "Creating project directories..."
    
    # Create data directories
    mkdir -p data/raw data/silver data/gold
    print_status "✓ Created data directories"
    
    # Create logs directory
    mkdir -p logs
    print_status "✓ Created logs directory"
    
    # Create temp directory
    mkdir -p temp
    print_status "✓ Created temp directory"
    
    # Ensure dbt_project directory exists
    if [ ! -d "dbt_project" ]; then
        print_warning "dbt_project directory not found. Please ensure dbt models are in place."
    fi
    
    # Ensure great_expectations directory exists
    if [ ! -d "great_expectations" ]; then
        print_warning "great_expectations directory not found. Please ensure GE configuration is in place."
    fi
}

# Setup Python virtual environment
setup_python_env() {
    print_header "Setting up Python virtual environment..."
    
    if [ ! -d "venv" ]; then
        python3 -m venv venv
        print_status "✓ Created Python virtual environment"
    else
        print_status "✓ Python virtual environment already exists"
    fi
    
    # Activate virtual environment
    source venv/bin/activate
    
    # Upgrade pip
    pip install --upgrade pip
    
    # Install requirements
    if [ -f "requirements.txt" ]; then
        print_status "Installing Python dependencies..."
        pip install -r requirements.txt
        print_status "✓ Installed Python dependencies"
    else
        print_warning "requirements.txt not found"
    fi
}

# Setup Docker environment
setup_docker_env() {
    print_header "Setting up Docker environment..."
    
    # Set Airflow UID for Docker
    export AIRFLOW_UID=50000
    
    # Create .env file for docker-compose if it doesn't exist
    if [ ! -f ".env" ]; then
        setup_env_file
    fi
    
    print_status "✓ Docker environment configured"
}

# Build and start services
start_services() {
    print_header "Starting Docker services..."
    
    # Build and start services in background
    docker-compose up -d --build
    
    print_status "✓ Docker services started"
    print_status "Waiting for services to be ready..."
    
    # Wait for services to be ready
    sleep 30
    
    print_status "✓ All services should be ready"
}

# Display service information
display_service_info() {
    print_header "Service Information"
    echo ""
    echo "🌐 Service URLs:"
    echo "  • Airflow Web UI: http://localhost:8080"
    echo "    Username: admin, Password: admin"
    echo ""
    echo "  • Streamlit Dashboard: http://localhost:8501"
    echo ""
    echo "  • MinIO Console: http://localhost:9001"
    echo "    Username: minio, Password: minio123"
    echo ""
    echo "  • Spark Master UI: http://localhost:8181"
    echo ""
    echo "  • Whoogle Search: http://localhost:5000"
    echo ""
    echo "📁 Data Directories:"
    echo "  • Raw data: ./data/raw"
    echo "  • Silver data: ./data/silver"
    echo "  • Gold data: ./data/gold"
    echo ""
    echo "🔧 Useful Commands:"
    echo "  • View logs: docker-compose logs -f [service_name]"
    echo "  • Stop services: docker-compose down"
    echo "  • Restart services: docker-compose restart"
    echo "  • Run pipeline: python src/run_pipeline.py --stage all"
    echo ""
}

# Main setup function
main() {
    detect_os
    check_prerequisites
    setup_env_file
    create_directories
    setup_python_env
    setup_docker_env
    
    echo ""
    print_header "Environment setup complete!"
    echo ""
    
    # Ask user if they want to start services
    read -p "Do you want to start the Docker services now? (y/n): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        start_services
        display_service_info
    else
        echo ""
        print_status "To start services later, run: docker-compose up -d"
        echo ""
        display_service_info
    fi
}

# Run main function
main "$@" 
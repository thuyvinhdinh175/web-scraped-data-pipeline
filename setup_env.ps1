# Web-Scraped Data Pipeline Environment Setup Script (PowerShell)
# This script sets up the complete environment for the data pipeline project on Windows

param(
    [switch]$SkipServices,
    [switch]$Force
)

# Set error action preference
$ErrorActionPreference = "Stop"

Write-Host "🚀 Setting up Web-Scraped Data Pipeline Environment" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Green

# Function to print colored output
function Write-Status {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Green
}

function Write-Warning {
    param([string]$Message)
    Write-Host "[WARNING] $Message" -ForegroundColor Yellow
}

function Write-Error {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Write-Header {
    param([string]$Message)
    Write-Host "[SETUP] $Message" -ForegroundColor Blue
}

# Check prerequisites
function Test-Prerequisites {
    Write-Header "Checking prerequisites..."
    
    # Check Docker
    try {
        $dockerVersion = docker --version
        Write-Status "✓ Docker is installed: $dockerVersion"
    }
    catch {
        Write-Error "Docker is not installed. Please install Docker Desktop for Windows first."
        exit 1
    }
    
    # Check Docker Compose
    try {
        $composeVersion = docker-compose --version
        Write-Status "✓ Docker Compose is installed: $composeVersion"
    }
    catch {
        Write-Error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    }
    
    # Check Python
    try {
        $pythonVersion = python --version
        Write-Status "✓ Python is installed: $pythonVersion"
    }
    catch {
        Write-Error "Python is not installed. Please install Python 3 first."
        exit 1
    }
    
    # Check if Docker is running
    try {
        docker info | Out-Null
        Write-Status "✓ Docker is running"
    }
    catch {
        Write-Error "Docker is not running. Please start Docker Desktop first."
        exit 1
    }
}

# Create environment file
function New-EnvironmentFile {
    Write-Header "Setting up environment configuration..."
    
    if (-not (Test-Path ".env")) {
        if (Test-Path "env.example") {
            Copy-Item "env.example" ".env"
            Write-Status "Created .env file from env.example"
        }
        else {
            Write-Warning "env.example not found. Creating basic .env file..."
            @"
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
"@ | Out-File -FilePath ".env" -Encoding UTF8
            Write-Status "Created basic .env file"
        }
    }
    else {
        Write-Status "✓ .env file already exists"
    }
}

# Create necessary directories
function New-ProjectDirectories {
    Write-Header "Creating project directories..."
    
    # Create data directories
    $directories = @("data/raw", "data/silver", "data/gold", "logs", "temp")
    
    foreach ($dir in $directories) {
        if (-not (Test-Path $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
            Write-Status "✓ Created directory: $dir"
        }
        else {
            Write-Status "✓ Directory already exists: $dir"
        }
    }
    
    # Check for required project directories
    if (-not (Test-Path "dbt_project")) {
        Write-Warning "dbt_project directory not found. Please ensure dbt models are in place."
    }
    
    if (-not (Test-Path "great_expectations")) {
        Write-Warning "great_expectations directory not found. Please ensure GE configuration is in place."
    }
}

# Setup Python virtual environment
function New-PythonEnvironment {
    Write-Header "Setting up Python virtual environment..."
    
    if (-not (Test-Path "venv")) {
        python -m venv venv
        Write-Status "✓ Created Python virtual environment"
    }
    else {
        Write-Status "✓ Python virtual environment already exists"
    }
    
    # Activate virtual environment
    & "venv\Scripts\Activate.ps1"
    
    # Upgrade pip
    python -m pip install --upgrade pip
    
    # Install requirements
    if (Test-Path "requirements.txt") {
        Write-Status "Installing Python dependencies..."
        pip install -r requirements.txt
        Write-Status "✓ Installed Python dependencies"
    }
    else {
        Write-Warning "requirements.txt not found"
    }
}

# Setup Docker environment
function Set-DockerEnvironment {
    Write-Header "Setting up Docker environment..."
    
    # Set Airflow UID for Docker
    $env:AIRFLOW_UID = "50000"
    
    # Create .env file for docker-compose if it doesn't exist
    if (-not (Test-Path ".env")) {
        New-EnvironmentFile
    }
    
    Write-Status "✓ Docker environment configured"
}

# Build and start services
function Start-DockerServices {
    Write-Header "Starting Docker services..."
    
    # Build and start services in background
    docker-compose up -d --build
    
    Write-Status "✓ Docker services started"
    Write-Status "Waiting for services to be ready..."
    
    # Wait for services to be ready
    Start-Sleep -Seconds 30
    
    Write-Status "✓ All services should be ready"
}

# Display service information
function Show-ServiceInformation {
    Write-Header "Service Information"
    Write-Host ""
    Write-Host "🌐 Service URLs:" -ForegroundColor Cyan
    Write-Host "  • Airflow Web UI: http://localhost:8080"
    Write-Host "    Username: admin, Password: admin"
    Write-Host ""
    Write-Host "  • Streamlit Dashboard: http://localhost:8501"
    Write-Host ""
    Write-Host "  • MinIO Console: http://localhost:9001"
    Write-Host "    Username: minio, Password: minio123"
    Write-Host ""
    Write-Host "  • Spark Master UI: http://localhost:8181"
    Write-Host ""
    Write-Host "  • Whoogle Search: http://localhost:5000"
    Write-Host ""
    Write-Host "📁 Data Directories:" -ForegroundColor Cyan
    Write-Host "  • Raw data: ./data/raw"
    Write-Host "  • Silver data: ./data/silver"
    Write-Host "  • Gold data: ./data/gold"
    Write-Host ""
    Write-Host "🔧 Useful Commands:" -ForegroundColor Cyan
    Write-Host "  • View logs: docker-compose logs -f [service_name]"
    Write-Host "  • Stop services: docker-compose down"
    Write-Host "  • Restart services: docker-compose restart"
    Write-Host "  • Run pipeline: python src/run_pipeline.py --stage all"
    Write-Host ""
}

# Main setup function
function Start-Setup {
    Test-Prerequisites
    New-EnvironmentFile
    New-ProjectDirectories
    New-PythonEnvironment
    Set-DockerEnvironment
    
    Write-Host ""
    Write-Header "Environment setup complete!"
    Write-Host ""
    
    # Ask user if they want to start services
    if (-not $SkipServices) {
        $response = Read-Host "Do you want to start the Docker services now? (y/n)"
        if ($response -eq "y" -or $response -eq "Y") {
            Start-DockerServices
            Show-ServiceInformation
        }
        else {
            Write-Host ""
            Write-Status "To start services later, run: docker-compose up -d"
            Write-Host ""
            Show-ServiceInformation
        }
    }
    else {
        Write-Host ""
        Write-Status "Skipping service startup (--SkipServices flag used)"
        Write-Host ""
        Show-ServiceInformation
    }
}

# Run main setup function
Start-Setup 
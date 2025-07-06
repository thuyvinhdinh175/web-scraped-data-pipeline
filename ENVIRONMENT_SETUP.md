# Environment Setup Guide

This guide provides multiple ways to set up your environment for the Web-Scraped Data Pipeline project.

## 🚀 Quick Start

### Option 1: Automated Setup (Recommended)

**For macOS/Linux:**
```bash
# Make the setup script executable
chmod +x setup_env.sh

# Run the automated setup
./setup_env.sh
```

**For Windows:**
```powershell
# Run the PowerShell setup script
.\setup_env.ps1
```

### Option 2: Using Makefile

```bash
# Complete setup including Docker services
make quickstart

# Or step by step
make setup
make docker-up
```

### Option 3: Manual Setup

Follow the detailed steps below if you prefer manual setup or need to customize specific components.

## 📋 Prerequisites

Before setting up the environment, ensure you have the following installed:

### Required Software

- **Docker & Docker Compose**: [Install Docker](https://docs.docker.com/get-docker/)
- **Python 3.8+**: [Install Python](https://www.python.org/downloads/)
- **Git**: [Install Git](https://git-scm.com/downloads)

### System Requirements

- **RAM**: Minimum 8GB, Recommended 16GB+
- **Storage**: At least 10GB free space
- **CPU**: Multi-core processor recommended

## 🔧 Manual Setup Steps

### 1. Clone the Repository

```bash
git clone <repository-url>
cd web-scraped-data-pipeline
```

### 2. Set Up Python Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install dependencies
pip install --upgrade pip
pip install -e .
```

### 3. Configure Environment Variables

```bash
# Copy the example environment file
cp env.example .env

# Edit the .env file with your specific configuration
nano .env  # or use your preferred editor
```

### 4. Create Required Directories

```bash
mkdir -p data/raw data/silver data/gold logs temp
```

### 5. Start Docker Services

```bash
# Build and start all services
docker-compose up -d --build

# Wait for services to be ready (about 30-60 seconds)
```

## 🌐 Service Access

Once the setup is complete, you can access the following services:

| Service | URL | Credentials |
|---------|-----|-------------|
| **Airflow Web UI** | http://localhost:8080 | admin / admin |
| **Streamlit Dashboard** | http://localhost:8501 | None |
| **MinIO Console** | http://localhost:9001 | minio / minio123 |
| **Spark Master UI** | http://localhost:8181 | None |
| **Whoogle Search** | http://localhost:5000 | None |

## 🔍 Environment Configuration

### Environment Variables

The project uses several environment variables that can be configured in the `.env` file:

#### Storage Configuration
```bash
# Choose storage type: 'local', 's3', or 'minio'
STORAGE_TYPE=minio

# Local file paths (used when STORAGE_TYPE=local)
LOCAL_DATA_PATH=./data
RAW_DATA_PATH=./data/raw
SILVER_DATA_PATH=./data/silver
GOLD_DATA_PATH=./data/gold
```

#### AWS Configuration (for production)
```bash
AWS_ACCESS_KEY_ID=your_aws_access_key_id
AWS_SECRET_ACCESS_KEY=your_aws_secret_access_key
AWS_DEFAULT_REGION=us-east-1
AWS_S3_BUCKET=web-scraped-data-pipeline
```

#### MinIO Configuration (for local development)
```bash
MINIO_ROOT_USER=minio
MINIO_ROOT_PASSWORD=minio123
MINIO_ENDPOINT=http://localhost:9000
MINIO_BUCKET=web-scraped-data-pipeline
```

#### Airflow Configuration
```bash
AIRFLOW_USERNAME=admin
AIRFLOW_PASSWORD=admin
AIRFLOW_EMAIL=admin@example.com
```

## 🐳 Docker Services

The project includes several Docker services:

### Core Services
- **Whoogle Search**: Privacy-focused search engine for web scraping
- **Airflow**: Workflow orchestration and scheduling
- **PostgreSQL**: Airflow metadata database
- **MinIO**: S3-compatible object storage
- **Spark**: Distributed data processing
- **Streamlit**: Data visualization dashboard

### Service Dependencies
```
Whoogle Search
    ↓
Airflow (Webserver + Scheduler)
    ↓
PostgreSQL (Airflow metadata)
    ↓
MinIO (Object storage)
    ↓
Spark (Data processing)
    ↓
Streamlit (Dashboard)
```

## 🛠️ Development Setup

### For Developers

1. **Install Development Dependencies**
   ```bash
   pip install -e ".[dev,test,docs]"
   ```

2. **Set Up Pre-commit Hooks**
   ```bash
   pre-commit install
   ```

3. **Run Development Checks**
   ```bash
   make dev-test
   ```

### Code Quality Tools

- **Black**: Code formatting
- **isort**: Import sorting
- **flake8**: Linting
- **mypy**: Type checking
- **pytest**: Testing

## 🔧 Troubleshooting

### Common Issues

#### Docker Services Not Starting
```bash
# Check Docker status
docker info

# Check service logs
docker-compose logs

# Restart services
docker-compose down
docker-compose up -d
```

#### Port Conflicts
If you get port conflicts, check what's running on the required ports:
```bash
# Check ports in use
lsof -i :8080  # Airflow
lsof -i :8501  # Streamlit
lsof -i :9000  # MinIO
lsof -i :5000  # Whoogle
```

#### Permission Issues
```bash
# Fix Docker permissions (Linux)
sudo usermod -aG docker $USER
# Log out and back in

# Fix file permissions
chmod -R 755 data/
```

#### Memory Issues
If you encounter memory issues:
```bash
# Increase Docker memory limit
# In Docker Desktop: Settings > Resources > Memory

# Or reduce Spark worker memory
# Edit docker-compose.yml:
# SPARK_WORKER_MEMORY=1G
```

### Reset Environment

To completely reset your environment:

```bash
# Stop and remove all containers
docker-compose down -v --remove-orphans

# Remove all images
docker system prune -a

# Clean up data
make clean-data

# Restart setup
make quickstart
```

## 📊 Monitoring and Logs

### View Service Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f airflow-webserver

# Recent logs
docker-compose logs --tail=100
```

### Monitor Resources
```bash
# Check service status
make check-status

# Monitor resource usage
make monitor

# View recent logs
make logs
```

## 🚀 Production Deployment

### AWS Deployment
1. Configure AWS credentials in `.env`
2. Set `STORAGE_TYPE=s3`
3. Update `AWS_S3_BUCKET` with your bucket name
4. Deploy using your preferred method (ECS, EKS, EC2)

### Cloud Deployment
```bash
# Build for production
make prod-build

# Deploy to production
make prod-deploy
```

## 📚 Additional Resources

- [Docker Documentation](https://docs.docker.com/)
- [Apache Airflow Documentation](https://airflow.apache.org/docs/)
- [Apache Spark Documentation](https://spark.apache.org/docs/)
- [dbt Documentation](https://docs.getdbt.com/)
- [Great Expectations Documentation](https://docs.greatexpectations.io/)
- [Streamlit Documentation](https://docs.streamlit.io/)

## 🤝 Getting Help

If you encounter issues:

1. Check the troubleshooting section above
2. Review the service logs: `docker-compose logs`
3. Check the project's GitHub issues
4. Create a new issue with detailed information about your problem

## 📝 Environment Checklist

- [ ] Docker and Docker Compose installed
- [ ] Python 3.8+ installed
- [ ] Repository cloned
- [ ] Virtual environment created and activated
- [ ] Dependencies installed
- [ ] Environment file configured
- [ ] Required directories created
- [ ] Docker services started
- [ ] All services accessible via web UI
- [ ] Test pipeline execution

Once all items are checked, your environment is ready for development! 
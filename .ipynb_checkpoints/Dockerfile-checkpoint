# Terminal Server App Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
# We need Docker CLI to spawn sibling containers (Docker-in-Docker approach)
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    lsb-release \
    postgresql-client \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian \
      $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null \
    && apt-get update \
    && apt-get install -y docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/

# Create a non-root user (optional but good practice, though we need docker group access)
# For simplicity in this demo, running as root to ensure access to /var/run/docker.sock
# In production, you'd add a user to the docker group.

# Expose API/Web port
EXPOSE 8000

# Environment variables (Defaults)
ENV MODULE_NAME=src.main
ENV VARIABLE_NAME=app
ENV PORT=8000
ENV HOST=0.0.0.0

# Start the application
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]

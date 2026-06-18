FROM python:3.12-slim

# Install system utilities and Node.js
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    nodejs \
    npm \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Install JupyterLite and tools
RUN pip install --no-cache-dir \
    jupyterlite-core \
    jupyterlite-pyodide-kernel \
    tornado \
    httpx \
    psutil

# Install localtunnel
RUN npm install -g localtunnel

# Set up app directory
WORKDIR /app

# Copy management scripts (sharing from base when possible or specialized)
# For now, we'll create specialized versions or copy them
COPY jupyterlite_server.py .
COPY stats_reporter.py .
COPY idle_monitor.py .
RUN chmod +x stats_reporter.py idle_monitor.py

# Build JupyterLite site
RUN jupyter lite build --output-dir /app/dist

# Copy entrypoint script
COPY entrypoint_jupyterlite.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Expose JupyterLite port
EXPOSE 8888

# Set entrypoint
ENTRYPOINT ["/entrypoint.sh"]

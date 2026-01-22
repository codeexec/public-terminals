FROM python:3.12-slim

# OPTIMIZED DOCKERFILE
# Reduces image size by ~55% (1.16GB -> 530MB) by removing heavy CLI tools

# Install system utilities and Node.js
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    vim \
    nano \
    tmux \
    dnsutils \
    iputils-ping \
    net-tools \
    netcat-traditional \
    procps \
    htop \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Install Node.js tools: localtunnel + Gemini CLI
RUN npm install -g localtunnel @google/gemini-cli

# Install Claude CLI
ENV PATH="/root/.local/bin:${PATH}"
RUN curl -fsSL https://claude.ai/install.sh | bash

# Add MOTD
COPY motd.sh /etc/motd.sh
RUN chmod +x /etc/motd.sh
RUN echo "/etc/motd.sh" >> /root/.bashrc

# Create app directory and copy application files
WORKDIR /app
COPY terminado_server.py .
COPY stats_reporter.py .
COPY idle_monitor.py .
COPY index.html .
RUN chmod +x stats_reporter.py idle_monitor.py

# Pre-compile Python bytecode for faster startup
RUN python -m compileall /app

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Set working directory for the terminal
WORKDIR /workspace

# Expose Terminado port
EXPOSE 8888

# Set entrypoint
ENTRYPOINT ["/entrypoint.sh"]


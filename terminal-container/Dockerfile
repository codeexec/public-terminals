FROM python:3.12-slim

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

# Add claude's bin to the PATH
ENV PATH="/root/.local/bin:${PATH}"

# Install Python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Install Node.js packages
RUN npm install -g localtunnel @google/gemini-cli \
    && curl -fsSL https://claude.ai/install.sh | bash

# Add MOTD
COPY motd.sh /etc/motd.sh
RUN chmod +x /etc/motd.sh
RUN echo "/etc/motd.sh" >> /root/.bashrc

# Create app directory and copy application files
WORKDIR /app
COPY terminado_server.py .
COPY index.html .

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Set working directory for the terminal
WORKDIR /workspace

# Expose Terminado port
EXPOSE 8888

# Set entrypoint
ENTRYPOINT ["/entrypoint.sh"]
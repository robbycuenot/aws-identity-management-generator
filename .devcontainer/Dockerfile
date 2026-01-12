FROM mcr.microsoft.com/devcontainers/python:3.13-bookworm

# Install AWS CLI v2 and Terraform CLI
# Note: Docker CLI is installed via the docker-outside-of-docker feature in devcontainer.json
RUN apt-get update && \
    apt-get install -y unzip curl gnupg software-properties-common ca-certificates && \
    \
    # Install AWS CLI
    curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" && \
    unzip awscliv2.zip && \
    ./aws/install && \
    rm -rf awscliv2.zip aws && \
    \
    # Install HashiCorp GPG key and Terraform CLI
    curl -fsSL https://apt.releases.hashicorp.com/gpg | gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com bookworm main" > /etc/apt/sources.list.d/hashicorp.list && \
    apt-get update && \
    apt-get install -y terraform && \
    \
    # Cleanup
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Pre-create venv directory and install Python dependencies
# Use /home/vscode/venv so it persists after workspace mount overwrites /workspaces
COPY scripts/requirements.txt /tmp/requirements.txt

USER vscode
RUN python3 -m venv /home/vscode/venv && \
    /home/vscode/venv/bin/pip install --upgrade pip && \
    /home/vscode/venv/bin/pip install -r /tmp/requirements.txt

USER root

# Customize shell environment
RUN echo "complete -C aws_completer aws" >> /home/vscode/.bashrc && \
    echo "complete -C aws_completer aws" >> /home/vscode/.profile && \
    echo "alias tf=terraform" >> /home/vscode/.bashrc && \
    echo "alias tf=terraform" >> /home/vscode/.profile && \
    chown vscode:vscode /home/vscode/.bashrc /home/vscode/.profile
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
# The workspace will be mounted at /workspaces/aws-identity-management-generator
COPY scripts/requirements.txt /tmp/requirements.txt
COPY scripts/activate_env.sh /tmp/activate_env.sh
RUN mkdir -p /workspaces/aws-identity-management-generator/scripts && \
    mv /tmp/requirements.txt /workspaces/aws-identity-management-generator/scripts/ && \
    mv /tmp/activate_env.sh /workspaces/aws-identity-management-generator/scripts/ && \
    chown -R vscode:vscode /workspaces

USER vscode
WORKDIR /workspaces/aws-identity-management-generator
RUN bash scripts/activate_env.sh

USER root
WORKDIR /

# Customize shell environment
RUN echo "complete -C aws_completer aws" >> /home/vscode/.bashrc && \
    echo "complete -C aws_completer aws" >> /home/vscode/.profile && \
    echo "alias tf=terraform" >> /home/vscode/.bashrc && \
    echo "alias tf=terraform" >> /home/vscode/.profile && \
    chown vscode:vscode /home/vscode/.bashrc /home/vscode/.profile
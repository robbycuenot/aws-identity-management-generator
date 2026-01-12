#!/bin/bash

# Script: setup_env.sh
# Purpose: Create and activate a Python virtual environment, then install dependencies.
# Usage: ./setup_env.sh or source scripts/activate_env.sh (from repo root)

# Determine the script directory and repo root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

# Constants
# Use /home/vscode/venv in Codespaces (prebuild creates it there), otherwise use repo-local venv
if [ -d "/home/vscode/venv" ]; then
    VENV_DIR="/home/vscode/venv"
else
    VENV_DIR="$REPO_ROOT/venv"
fi
REQUIREMENTS_FILE="$SCRIPT_DIR/requirements.txt"

# Set AWS region if not already set (e.g., by GitHub Actions)
if [ -z "$AWS_REGION" ]; then
    export AWS_REGION=us-east-1
fi
if [ -z "$AWS_DEFAULT_REGION" ]; then
    export AWS_DEFAULT_REGION="${AWS_REGION}"
fi

# ANSI color codes
COLOR_INFO="\033[1;34m"   # Blue
COLOR_ERROR="\033[1;31m"  # Red
COLOR_RESET="\033[0m"     # Reset color

# Function to print messages
print_message() {
    local type="$1"
    shift
    case "$type" in
        info)
            echo -e "${COLOR_INFO}[INFO]${COLOR_RESET} $*"
            ;;
        error)
            echo -e "${COLOR_ERROR}[ERROR]${COLOR_RESET} $*"
            ;;
    esac
}

# Function to check if Python 3.13+ is installed
check_python() {
    if ! command -v python3 >/dev/null 2>&1; then
        print_message error "Python 3 not found. Please install Python 3.13+ and retry."
        exit 1
    fi
    
    # Check Python version is 3.13+
    PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
    MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)
    
    if [ "$MAJOR" -lt 3 ] || ([ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 13 ]); then
        print_message error "Python 3.13+ required, found Python $PYTHON_VERSION"
        exit 1
    fi
    
    print_message info "Python $PYTHON_VERSION is installed."
}

# Function to create virtual environment
create_venv() {
    if [ ! -d "$VENV_DIR" ]; then
        print_message info "Creating virtual environment in ./$VENV_DIR..."
        python3 -m venv "$VENV_DIR" || {
            print_message error "Failed to create virtual environment."
            exit 1
        }
        print_message info "Virtual environment created."
    else
        print_message info "Virtual environment already exists in ./$VENV_DIR."
    fi
}

# Function to activate virtual environment
activate_venv() {
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate" || {
        print_message error "Activation failed."
        exit 1
    }

    if [[ -n "$VIRTUAL_ENV" ]]; then
        print_message info "Virtual environment activated."
    else
        print_message error "Failed to activate the virtual environment."
        exit 1
    fi
}

# Function to upgrade pip
upgrade_pip() {
    print_message info "Upgrading pip..."
    pip install --upgrade pip || {
        print_message error "Failed to upgrade pip."
        exit 1
    }
    print_message info "pip upgraded to the latest version."
}

# Function to install dependencies
install_dependencies() {
    if [ -f "$REQUIREMENTS_FILE" ]; then
        print_message info "Installing dependencies from $REQUIREMENTS_FILE..."
        pip install -r "$REQUIREMENTS_FILE" || {
            print_message error "Dependency installation failed."
            exit 1
        }
        print_message info "Dependencies installed successfully."
    else
        print_message info "No requirements.txt found at $REQUIREMENTS_FILE. Skipping dependency installation."
    fi
}

# Main function to orchestrate the setup
main() {
    check_python
    create_venv
    activate_venv
    upgrade_pip
    install_dependencies
    print_message info "Environment setup complete. Your virtual environment is ready to use."
}

# Execute the main function
main

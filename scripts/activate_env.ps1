# Script: activate_env.ps1
# Purpose: Create and activate a Python virtual environment, then install dependencies.
# Usage: .\scripts\activate_env.ps1 (from repo root)

# Determine paths
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$VenvDir = Join-Path $RepoRoot "venv"
$RequirementsFile = Join-Path $ScriptDir "requirements.txt"

# Set AWS region if not already set
if (-not $env:AWS_REGION) {
    $env:AWS_REGION = "us-east-1"
}
if (-not $env:AWS_DEFAULT_REGION) {
    $env:AWS_DEFAULT_REGION = $env:AWS_REGION
}

function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Blue
}

function Write-Error {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Test-Python {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) {
        Write-Error "Python not found. Please install Python 3.13+ and retry."
        exit 1
    }

    $version = python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    $parts = $version -split '\.'
    $major = [int]$parts[0]
    $minor = [int]$parts[1]

    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 13)) {
        Write-Error "Python 3.13+ required, found Python $version"
        exit 1
    }

    Write-Info "Python $version is installed."
}

function New-Venv {
    if (-not (Test-Path $VenvDir)) {
        Write-Info "Creating virtual environment in $VenvDir..."
        python -m venv $VenvDir
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Failed to create virtual environment."
            exit 1
        }
        Write-Info "Virtual environment created."
    } else {
        Write-Info "Virtual environment already exists in $VenvDir."
    }
}

function Enable-Venv {
    $activateScript = Join-Path $VenvDir "Scripts\Activate.ps1"
    if (-not (Test-Path $activateScript)) {
        Write-Error "Activation script not found at $activateScript"
        exit 1
    }

    & $activateScript

    if (-not $env:VIRTUAL_ENV) {
        Write-Error "Failed to activate the virtual environment."
        exit 1
    }

    Write-Info "Virtual environment activated."
}

function Update-Pip {
    Write-Info "Upgrading pip..."
    pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to upgrade pip."
        exit 1
    }
    Write-Info "pip upgraded to the latest version."
}

function Install-Dependencies {
    if (Test-Path $RequirementsFile) {
        Write-Info "Installing dependencies from $RequirementsFile..."
        pip install -r $RequirementsFile
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Dependency installation failed."
            exit 1
        }
        Write-Info "Dependencies installed successfully."
    } else {
        Write-Info "No requirements.txt found at $RequirementsFile. Skipping dependency installation."
    }
}

# Main
Test-Python
New-Venv
Enable-Venv
Update-Pip
Install-Dependencies
Write-Info "Environment setup complete. Your virtual environment is ready to use."

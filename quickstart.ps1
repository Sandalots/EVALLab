# Quick start script for EVALLab (Windows PowerShell)
# This script sets up a Python venv, installs requirements, downloads the supplementary material if needed, and runs the main script.

$ErrorActionPreference = 'Stop'

# Create venv if it doesn't exist
if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

# Activate venv
$venvActivate = ".venv\\Scripts\\Activate.ps1"
if (Test-Path $venvActivate) {
    & $venvActivate
} else {
    Write-Error "Could not find venv activation script at $venvActivate"
    exit 1
}

# Upgrade pip
python -m pip install --upgrade pip

# Install requirements
python -m pip install -r requirements.txt

# Check if supplementary_material directory exists
$codebaseDir = "papers/codebases/supplementary_material"
if (-not (Test-Path $codebaseDir)) {
    Write-Host "Decontextualization codebase not found."
    $zipPath = "papers/codebases/supplementary_material.zip"
    $url = "https://openreview.net/attachment?id=cK8YYMc65B&name=supplementary_material"
    try {
        Write-Host "Attempting to download Decontextualization codebase..."
        if (-not (Test-Path "papers/codebases")) {
            New-Item -ItemType Directory -Path "papers/codebases" | Out-Null
        }
        Invoke-WebRequest -Uri $url -OutFile $zipPath
        # Extract directly to papers/codebases/ to avoid duplicate folder
        Expand-Archive -Path $zipPath -DestinationPath "papers/codebases/"
        Remove-Item $zipPath
        Write-Host "Download and extraction complete."
    } catch {
        Write-Warning "Automatic download failed. Please manually download the codebase from $url and place it in $codebaseDir."
        exit 1
    }
} else {
    Write-Host "Decontextualization codebase found."
}

Write-Host "To run EVALLab on the Decontextualization paper, use the following command:"
Write-Host "python run_EVALLab.py --paper papers/decontextualisation.pdf --code ./papers/codebases/supplementary_material/"

if (Test-Path $codebaseDir) {
    python run_EVALLab.py --paper papers/decontextualisation.pdf --code ./papers/codebases/supplementary_material/
} else {
    Write-Warning "The manually placed Decontextualization codebase is required to run the example."
}

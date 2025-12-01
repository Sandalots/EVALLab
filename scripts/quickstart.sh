#!/bin/bash

# Quick start script for setting up EVALLab and running it on the sample Decontextualization research paper.
set -e

# Determine script and repo root directories
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_DIR"

# Create venv if it doesn't exist in repo root
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

# ollama serve in the background
if ! pgrep -f "ollama serve" > /dev/null; then
  echo "Starting ollama server..."
  ollama serve > /dev/null 2>&1 &
else
  echo "Ollama server is already running."
fi

# Activate venv from repo root
source .venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install requirements
pip install -r requirements.txt

# Check if papers/codebases/decontextualization directory exists
if [ ! -d "papers/codebases/decontextualization" ]; then

  # Check if user is linux or mac and has the curl command, download supplementary material
  if [[ "$OSTYPE" == "linux-gnu"* || "$OSTYPE" == "darwin"* ]]; then

    # Check if user has the curl command
    if command -v curl &> /dev/null; then
      echo "Downloading Decontextualization codebase..."

      # Make the codebases dir if it doesn't exist yet
      mkdir -p papers/codebases/

      # Download the zipped codebase to the codebases dir
      curl -L -o papers/codebases/supplementary_material.zip "https://openreview.net/attachment?id=cK8YYMc65B&name=supplementary_material"

      # Unzip the codebase
      unzip papers/codebases/supplementary_material.zip -d papers/codebases/

      # Remove the zip file
      rm papers/codebases/supplementary_material.zip

      # Remove __MACOSX directory if it exists
      if [ -d "papers/codebases/__MACOSX" ]; then
        rm -rf papers/codebases/__MACOSX
      fi

      # Rename supplementary_material to decontextualization if it exists
      if [ -d "papers/codebases/supplementary_material" ]; then
        mv papers/codebases/supplementary_material papers/codebases/decontextualization
      fi

      echo "Decontextualization codebase downloaded and extracted to papers/codebases/decontextualization."
    else
      echo "Please install curl to download the Decontextualization codebase automatically."
      echo "Alternatively, manually download the codebase from https://openreview.net/attachment?id=cK8YYMc65B&name=supplementary_material and place it in papers/codebases/decontextualization"
      exit 1
    fi
  else
    echo "Please manually download the Decontextualization codebase from https://openreview.net/attachment?id=cK8YYMc65B&name=supplementary_material and place it in papers/codebases/decontextualization"
    exit 1
  fi
else
  echo "Decontextualization codebase found."
fi

echo "To run EVALLab on the Decontextualization paper, use the following command:"
echo "python3 run_EVALLab.py papers/decontextualisation.pdf --code ./papers/codebases/decontextualization/"

# Run EVALLab if codebase exists
if [ ! -d "papers/codebases/decontextualization" ]; then
  echo "Note: The manually placed Decontextualization codebase is required to run the example."
else
  python3 run_EVALLab.py --paper papers/decontextualisation.pdf --code papers/codebases/decontextualization/
fi

# Open the dashboard to view visualizations
"$SCRIPT_DIR"/open_visualizations.sh || true

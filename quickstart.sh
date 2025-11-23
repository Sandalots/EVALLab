#!/bin/bash
# Quick start script for EVALLab
set -e

# Create venv if it doesn't exist
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

# Activate venv
source .venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install requirements
pip install -r requirements.txt

# check if papers/codebases/supplementary_materials directory exists
if [ ! -d "papers/codebases/supplementary_material" ]; then
# tell user to manually download the decontextualization codebase and place it here.
  # check if user is linux or mac and has the curl command, download https://openreview.net/attachment?id=cK8YYMc65B&name=supplementary_material using curl and place it in papers/codebases/
  if [[ "$OSTYPE" == "linux-gnu"* || "$OSTYPE" == "darwin"* ]]; then
    if command -v curl &> /dev/null; then
      echo "Downloading Decontextualization codebase..."
      mkdir -p papers/codebases/
      curl -L -o papers/codebases/supplementary_material.zip "https://openreview.net/attachment?id=cK8YYMc65B&name=supplementary_material"
      unzip papers/codebases/supplementary_material.zip -d papers/codebases/
      rm papers/codebases/supplementary_material.zip
      # remove __MACOSX directory if it exists
      if [ -d "papers/codebases/__MACOSX" ]; then
        rm -rf papers/codebases/__MACOSX
      fi
      echo "Decontextualization codebase downloaded and extracted to papers/codebases/supplementary_material."

    else
      echo "Please install curl to download the Decontextualization codebase automatically."
      echo "Alternatively, manually download the codebase from https://openreview.net/attachment?id=cK8YYMc65B&name=supplementary_material and place it in papers/codebases/supplementary_material"
      exit 1
    fi
  else
    echo "Please manually download the Decontextualization codebase from https://openreview.net/attachment?id=cK8YYMc65B&name=supplementary_material and place it in papers/codebases/supplementary_material"
    exit 1
  fi

# else tell user that the codebase is found
else
  echo "Decontextualization codebase found."
fi

# tell user to run python3 run_EVALLab.py papers/decontextualisation.pdf --code ./papers/codebases/supplementary_material
echo "To run EVALLab on the Decontextualization paper, use the following command:"
echo "python3 run_EVALLab.py papers/decontextualisation.pdf --code ./papers/codebases/supplementary_material/"

# check if papers/codebases/suplementary_materials exists
if [ ! -d "papers/codebases/supplementary_material" ]; then
    echo "Note: The manually placed Decontextualization codebase is required to run the example."

# else run python3 run_EVALLab.py papers/decontextualisation.pdf --code ./papers/codebases/supplementary_material
else
    python3 run_EVALLab.py --paper papers/decontextualisation.pdf --code ./papers/codebases/supplementary_material/
fi
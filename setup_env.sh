#!/bin/bash
# Script to set up the Conda environment for running real LLMs on Khipu

# Exit on error
set -e

ENV_NAME="llm-local"

echo "================================================================="
echo " Setting up Conda Environment: $ENV_NAME"
echo " This environment is required for running REAL LLMs (LLMReal)."
echo " (Note: MOCK mode does NOT require this setup)"
echo "================================================================="

# 1. Load Miniconda module
echo "[1/4] Loading miniconda module..."
module load miniconda/3.0

# 2. Create the environment if it doesn't exist
if conda env list | grep -q "\b${ENV_NAME}\b"; then
    echo "[2/4] Conda environment '$ENV_NAME' already exists. Skipping creation."
else
    echo "[2/4] Creating conda environment '$ENV_NAME' with Python 3.11..."
    conda create -y -n "$ENV_NAME" python=3.11
fi

# 3. Install packages
echo "[3/4] Installing PyTorch with CUDA 12.1 support..."
conda run -n "$ENV_NAME" pip install --upgrade pip
conda run -n "$ENV_NAME" pip install torch --index-url https://download.pytorch.org/whl/cu121

echo "[4/4] Installing Transformers, Accelerate, and BitsAndBytes for quantization..."
conda run -n "$ENV_NAME" pip install transformers accelerate bitsandbytes huggingface_hub

echo "================================================================="
echo " Environment setup completed successfully!"
echo " "
echo " To run a job using a real LLM, you can now run:"
echo "   sbatch run_job.sh real Qwen/Qwen2.5-Coder-7B-Instruct"
echo "================================================================="

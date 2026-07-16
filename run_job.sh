#!/bin/bash
#SBATCH --partition=gpu                  # Default partition (gpu)
#SBATCH --gres=gpu:a100_3g.20gb:1        # Default GPU resource (MIG A100 slice)
#SBATCH --mem=32G                        # Memory allocation
#SBATCH --cpus-per-task=8                # CPUs per task
#SBATCH --time=01:00:00                  # Time limit (default: 1 hour)
#SBATCH --job-name=llm_local_server      # Job name
#SBATCH --output=logs/slurm-%j.out       # Standard output log (created inside LLM-Local/logs/)
#SBATCH --error=logs/slurm-%j.err        # Standard error log

# Make sure we are in the LLM-Local directory
cd /home/cesar.perales/LLM-Local

# Create logs directory if it doesn't exist
mkdir -p logs

# 1. Parse command line arguments passed to the sbatch command
# Usage: sbatch run_job.sh [mode: mock|real] [model_id_or_path] [quantization: none|8bit|4bit]
MODE="${1:-mock}"
MODEL="${2:-Qwen/Qwen2.5-Coder-7B-Instruct}"
QUANT="${3:-none}"

echo "=========================================================="
echo "Starting SLURM Job for LLM-Local"
echo "Job ID: $SLURM_JOB_ID"
echo "Running on Node: $SLURMD_NODENAME"
echo "Mode: ${MODE^^}"
echo "Model: $MODEL"
echo "Quantization: $QUANT"
echo "=========================================================="

# 2. Configure environment based on mode
if [ "$MODE" = "real" ]; then
    echo "Configuring environment for REAL LLM execution..."
    
    # Load miniconda module
    module load miniconda/3.0
    
    # Activate environment
    ENV_NAME="llm-local"
    if conda env list | grep -q "\b${ENV_NAME}\b"; then
        echo "Activating conda environment: $ENV_NAME"
        # We need to source conda.sh to enable 'conda activate' inside subshells
        CONDA_BASE=$(conda info --base)
        source "$CONDA_BASE/etc/profile.d/conda.sh"
        conda activate "$ENV_NAME"
    else
        echo "WARNING: Conda environment '$ENV_NAME' not found!"
        echo "Did you run setup_env.sh? Attempting to run with base conda environment."
    fi
    
    # Configure Hugging Face cache directory to home folder (NFS shared)
    export HF_HOME="/home/cesar.perales/.cache/huggingface"
    mkdir -p "$HF_HOME"
    
    # Build quantization flags
    QUANT_FLAG=""
    if [ "$QUANT" = "8bit" ]; then
        QUANT_FLAG="--load_in_8bit"
    elif [ "$QUANT" = "4bit" ]; then
        QUANT_FLAG="--load_in_4bit"
    fi
    
    # Run the server with real model
    exec python3 server.py --mode real --model "$MODEL" $QUANT_FLAG

else
    # Mock mode
    echo "Configuring environment for MOCK LLM execution..."
    
    # Load a lightweight python module (fast load, no CUDA needed)
    module load python3/3.11.11 || true
    
    # Run the server in mock mode
    exec python3 server.py --mode mock --model "$MODEL"
fi

echo "=========================================================="
echo "SLURM Job finished."
echo "=========================================================="

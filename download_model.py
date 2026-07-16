import sys
import os
import argparse

def main():
    parser = argparse.ArgumentParser(description="Download models from Hugging Face Hub for offline use on Khipu")
    parser.add_argument("model_id", type=str, help="Hugging Face model ID (e.g., 'Qwen/Qwen2.5-Coder-7B-Instruct' or 'Qwen/Qwen2.5-Coder-32B-Instruct')")
    parser.add_argument("--dest", type=str, default=None, 
                        help="Local destination directory (default: models/<model_name>)")
    args = parser.parse_args()

    # Load huggingface_hub inside main to catch ImportErrors
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("\n[Error] huggingface_hub is not installed in your current Python environment.")
        print("Please activate your conda environment first:")
        print("  module load miniconda/3.0")
        print("  conda activate llm-local")
        sys.exit(1)

    # Format folder name based on model ID
    model_folder = args.model_id.replace('/', '_')
    if args.dest is None:
        dest_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", model_folder)
    else:
        dest_dir = os.path.abspath(args.dest)

    print("=" * 70)
    print(f"Downloading Model: {args.model_id}")
    print(f"Destination:     {dest_dir}")
    print("This runs on the Login Node (using internet) to save weights locally.")
    print("Once downloaded, the model will run completely offline on compute nodes.")
    print("=" * 70)
    print("Downloading files (this might take several minutes)...")
    print("-" * 70)

    try:
        # Download the model weights and tokenizer
        # ignore_patterns avoids downloading duplicate framework weights (e.g., tf/jax/rust)
        snapshot_download(
            repo_id=args.model_id,
            local_dir=dest_dir,
            local_dir_use_symlinks=False,  # Copy files directly so it's fully self-contained
            ignore_patterns=["*.msgpack", "*.h5", "*.ot"]
        )
        print("-" * 70)
        print(f"Success! Model weights saved in: {dest_dir}")
        print(f"To run this model offline in your SLURM job, use:")
        print(f"  make up MODE=real MODEL={dest_dir}")
        print("=" * 70)
    except Exception as e:
        print(f"\n[Error] Model download failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

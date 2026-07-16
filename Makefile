# Makefile for managing LLM-Local jobs on Khipu

# Default configuration variables
MODE ?= mock
MODEL ?= Qwen/Qwen2.5-Coder-7B-Instruct
QUANT ?= none
TIME ?= 01:00:00

# Dynamically set partition and resources based on mode if not overridden
ifeq ($(MODE),real)
  PARTITION ?= gpu
  GRES ?= gpu:a100_3g.20gb:1
else
  PARTITION ?= standard
  GRES ?= none
endif

.PHONY: help up down client status logs clean download

help:
	@echo "========================================================================="
	@echo "LLM-Local Management Interface"
	@echo "========================================================================="
	@echo "Available commands:"
	@echo "  make up          - Start the LLM server as a SLURM job"
	@echo "  make down        - Cancel the running SLURM job and clean up metadata"
	@echo "  make client      - Connect to the running LLM server via chat client"
	@echo "  make status      - Check if the LLM server is online and view details"
	@echo "  make logs        - Follow (tail -f) the stdout log of the latest job"
	@echo "  make download    - Download weights of MODEL from HF for offline use"
	@echo "  make clean       - Clean up stale connection files and logs"
	@echo "========================================================================="
	@echo "Customization parameters (override like 'make up MODE=real'):"
	@echo "  MODE             - Run mode: 'mock' (default) or 'real'"
	@echo "  MODEL            - Model ID or path (default: Qwen/Qwen2.5-Coder-7B-Instruct)"
	@echo "  QUANT            - Quantization (only for real mode): 'none' (default), '8bit', '4bit'"
	@echo "  TIME             - Execution time limit (default: 01:00:00)"
	@echo "  PARTITION        - SLURM partition (default: 'gpu' for real, 'standard' for mock)"
	@echo "  GRES             - GPU resources requested (default: 'gpu:a100_3g.20gb:1' for real)"
	@echo "========================================================================="

up:
	@echo "Submitting LLM-Local job..."
	@echo "  Partition:    $(PARTITION)"
	@echo "  GRES:         $(GRES)"
	@echo "  Time Limit:   $(TIME)"
	@echo "  Mode:         $(MODE)"
	@echo "  Model:        $(MODEL)"
	@if [ "$(MODE)" = "real" ]; then \
		echo "  Quantization: $(QUANT)"; \
	fi
	@echo "------------------------------------------------------------------------"
	@if [ "$(GRES)" = "none" ] || [ -z "$(GRES)" ]; then \
		sbatch --partition=$(PARTITION) --gres="" --time=$(TIME) run_job.sh $(MODE) $(MODEL) $(QUANT); \
	else \
		sbatch --partition=$(PARTITION) --gres=$(GRES) --time=$(TIME) run_job.sh $(MODE) $(MODEL) $(QUANT); \
	fi

down:
	@echo "Shutting down LLM-Local server..."
	@# Try reading the Job ID from connection.json
	@JOB_ID=$$(python3 -c "import json; print(json.load(open('connection.json'))['job_id'])" 2>/dev/null); \
	if [ ! -z "$$JOB_ID" ] && [ "$$JOB_ID" != "local" ] && [ "$$JOB_ID" != "manual" ]; then \
		echo "Found active Job ID $$JOB_ID in connection.json. Canceling..."; \
		scancel $$JOB_ID; \
	else \
		echo "No active job found in connection.json."; \
		echo "Checking squeue for any llm_local_server jobs belonging to $$USER..."; \
		JOB_ID=$$(squeue -u $$USER -o "%i %j" | grep llm_local | awk '{print $$1}' | head -n 1); \
		if [ ! -z "$$JOB_ID" ]; then \
			echo "Found running job $$JOB_ID. Canceling..."; \
			scancel $$JOB_ID; \
		else \
			echo "No running LLM-Local jobs found in the cluster queue."; \
		fi; \
	fi
	@rm -f connection.json
	@echo "Cleanup completed."

client:
	@/home/cesar.perales/.conda/envs/llm-local/bin/python3 client.py --chat

status:
	@/home/cesar.perales/.conda/envs/llm-local/bin/python3 client.py --status

logs:
	@LATEST_OUT=$$(ls -t logs/*.out 2>/dev/null | head -n 1); \
	if [ ! -z "$$LATEST_OUT" ]; then \
		LATEST_ERR=$${LATEST_OUT%.out}.err; \
		echo "Displaying latest logs (stdout + stderr): $$LATEST_OUT (Ctrl+C to stop)"; \
		echo "------------------------------------------------------------------------"; \
		tail -f "$$LATEST_OUT" "$$LATEST_ERR"; \
	else \
		echo "No log files found in logs/ directory."; \
	fi

clean:
	@rm -f connection.json
	@rm -rf logs/*
	@echo "Removed connection.json and cleaned logs/ directory."

download:
	@echo "Checking Conda environment for Hugging Face hub downloader..."
	@module load miniconda/3.0 && \
	CONDA_BASE=$$(conda info --base) && \
	source "$$CONDA_BASE/etc/profile.d/conda.sh" && \
	conda activate llm-local && \
	python3 download_model.py $(MODEL)

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a dual-project monorepo containing:

1. **HRM_Test/** - Hierarchical Reasoning Model: A novel recurrent neural network for abstract reasoning tasks (ARC puzzles, Sudoku, Mazes) achieving strong results with only 27M parameters and 1000 training examples
2. **Control_Plane_v2/** - Package management and multi-tier governance infrastructure for auditable agent coordination

## HRM_Test Commands

### Dataset Building
```bash
# Build ARC dataset (requires git submodules)
git submodule update --init --recursive
python dataset/build_arc_dataset.py

# Build Sudoku dataset with augmentation
python dataset/build_sudoku_dataset.py --output-dir data/sudoku-extreme-1k-aug-1000 --subsample-size 1000 --num-aug 1000
```

### Training
```bash
# Single GPU (e.g., RTX 4070)
OMP_NUM_THREADS=8 python pretrain.py data_path=data/sudoku-extreme-1k-aug-1000 epochs=20000 global_batch_size=384

# Multi-GPU distributed training
OMP_NUM_THREADS=8 torchrun --nproc-per-node 8 pretrain.py data_path=data/arc-aug-1000
```

### Evaluation
```bash
OMP_NUM_THREADS=8 torchrun --nproc-per-node 8 evaluate.py checkpoint=<path>
```

### Visualization
Open `puzzle_visualizer.html` in browser and upload the data/ folder.

## Control_Plane_v2 Commands

### Package Operations
```bash
python3 scripts/package_pack.py --src frameworks/FMWK-100.md --id PKG-FMWK-100 --token <token>
python3 scripts/package_install.py --archive packages_store/archive.tar.gz --id PKG-... --token <token>
python3 scripts/integrity_check.py --json
```

### Version Control
```bash
python3 scripts/cp_version_checkpoint.py --label "Production release" --token <token>
python3 scripts/cp_version_list.py
python3 scripts/cp_version_rollback.py --version-id VER-... --token <token>
```

### Testing
```bash
pytest tests/test_provenance.py
pytest tests/test_pristine.py
pytest tests/test_factory_canary.py
```

## HRM_Test Architecture

The Hierarchical Reasoning Model uses two interdependent recurrent modules:
- **H (High-level)**: Slow, abstract planning module (H_cycles iterations)
- **L (Low-level)**: Fast, detailed computation module (L_cycles iterations)

Key components in `models/`:
- `hrm/hrm_act_v1.py`: Main model with adaptive computation time (ACT) and halting Q-learning
- `layers.py`: FlashAttention, RoPE embeddings, SwiGLU, RMS normalization
- `losses.py`: Stablemax cross-entropy, ACT loss head combining LM loss with Q-halt learning
- `sparse_embedding.py`: Distributed sparse embeddings

Configuration uses Hydra/OmegaConf (`config/`). Training integrates with Weights & Biases for logging.

## Control_Plane_v2 Architecture

A minimal governance system with:
- **Tier separation**: HOT, Second Order, First Order tiers with separate codebases
- **Immutable ledger**: All operations logged for audit trail
- **Merkle verification**: Integrity checking via `lib/integrity.py` and `lib/merkle.py`
- **Role-based access**: admin, maintainer, auditor, reader roles in `lib/authz.py`
- **Pluggable auth**: passthrough (dev) or HMAC (production) via `lib/auth.py`

Key libraries in `lib/`:
- `gate_operations.py`: CRUD with authorization enforcement
- `packages.py`: Tar.gz packing with SHA256 digests
- `ledger_client.py`: Append-only event logging
- `provenance.py`: Source tracking and dependency resolution

Environment variables:
- `CONTROL_PLANE_AUTH_PROVIDER`: `passthrough` or `HMAC`
- `CONTROL_PLANE_SHARED_SECRET`: Required for HMAC auth

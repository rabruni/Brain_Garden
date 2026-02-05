# Brain Garden Playground - Gemini Context

This directory (`/Users/raymondbruni/Brain_Garden/playground`) functions as a monorepo containing two distinct but related projects: **Control_Plane_v2** (Infrastructure) and **HRM_Test** (Research/Model).

## 1. Control_Plane_v2 (Infrastructure)
**Directory:** `Control_Plane_v2/`
**Purpose:** A governance and package management system for AI agents, featuring an immutable ledger, tiered architecture, and signed package verification.

### Key Operations (Run from `Control_Plane_v2/` root)

#### Package Management
*   **Pack (Build):**
    ```bash
    python3 scripts/package_pack.py --src <source_path> --id <PKG-ID> --token <TOKEN>
    ```
    *Creates a `.tar.gz` in `packages_store/` and updates `registries/packages_registry.csv`.*
*   **Install:**
    ```bash
    python3 scripts/package_install.py --archive packages_store/<archive>.tar.gz --id <PKG-ID> --token <TOKEN>
    ```
    *Verifies signatures/digests and routes content to `modules/`, `extensions`, or external paths.*
*   **Integrity Check:**
    ```bash
    python3 scripts/integrity_check.py --json
    ```
    *Verifies registry hashes against filesystem and Merkle root.*

#### Version Control & Governance
*   **Checkpoint:** `python3 scripts/cp_version_checkpoint.py --label "Message"`
*   **Rollback:** `python3 scripts/cp_version_rollback.py --version-id <VER-ID>`
*   **List Versions:** `python3 scripts/cp_version_list.py`

### Architecture & Conventions
*   **Ledger:** Append-only logs in `ledger/`. All state changes (installs, packs) are logged.
*   **Auth:** Configured via env var `CONTROL_PLANE_AUTH_PROVIDER` (`passthrough` for dev, `hmac` for prod).
*   **Testing:** `pytest tests/` (covers auth, integrity, provenance).
*   **Conventions:**
    *   Do not manually edit `registries/*.csv` without rebuilding manifests.
    *   Preserve the "Pristine" state of `lib/` and `scripts/` unless performing a system upgrade.

---

## 2. HRM_Test (Research)
**Directory:** `HRM_Test/`
**Purpose:** Implementation of the **Hierarchical Reasoning Model (HRM)**, a recurrent neural network for abstract reasoning tasks (ARC, Sudoku, Maze).

### Key Operations (Run from `HRM_Test/` root)

#### Dataset Generation
*   **ARC:** `python dataset/build_arc_dataset.py` (Requires git submodules)
*   **Sudoku:** `python dataset/build_sudoku_dataset.py --output-dir data/sudoku-1k ...`
*   **Maze:** `python dataset/build_maze_dataset.py`

#### Training & Evaluation
*   **Training (Single GPU):**
    ```bash
    OMP_NUM_THREADS=8 python pretrain.py data_path=<data_dir> epochs=20000 global_batch_size=384
    ```
*   **Training (Multi-GPU):**
    ```bash
    torchrun --nproc-per-node 8 pretrain.py data_path=<data_dir>
    ```
*   **Evaluation:**
    ```bash
    torchrun --nproc-per-node 8 evaluate.py checkpoint=<path_to_ckpt>
    ```

### Architecture & Requirements
*   **Stack:** PyTorch, Hydra (config), Weights & Biases (logging).
*   **Dependencies:** Requires CUDA 12.6+ and `flash-attention` (2 or 3 depending on GPU).
*   **Model:** Recurrent architecture with High-level (planning) and Low-level (compute) modules.

---

## General Notes
*   **`CLAUDE.md` & `AGENTS.md`:** Reference these files in the root for additional context on agent behaviors and project-specific coding guidelines.
*   **Environment:**
    *   Python 3.11+ is standard.
    *   Be mindful of `CUDA_HOME` when building HRM extensions.

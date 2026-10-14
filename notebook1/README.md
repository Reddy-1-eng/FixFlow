# 🚀 BuildFail-SLM: Qwen2.5-Coder-7B-Instruct (80k Quality Samples Pipeline)

This dedicated workflow folder (`notebook1/`) is configured specifically for fine-tuning **`Qwen/Qwen2.5-Coder-7B-Instruct`** across **80,000+ quality CI/CD failure samples**, with the training executed on **Kaggle (Dual Tesla T4 GPUs - 32 GB VRAM)** and the remaining data preparation and evaluation stages executed locally.

---

## 📂 Notebook Suite (`notebook1/`)

| Notebook | Environment | Purpose | Key Details |
|---|---|---|---|
| **[`01_qwen7b_80k_data_ingestion.ipynb`](file:///c:/Users/reddy/OneDrive/document/SLM%20fine%20tuning/notebook1/01_qwen7b_80k_data_ingestion.ipynb)** | **Local** | Dataset verification & profiling | Profiles all 6 raw sources (`ci_repair_bench`, `cicd_self_healing`, `logchunks`, `java_travis`, `ghalogs`, `travis`). |
| **[`02_qwen7b_80k_source_extraction.ipynb`](file:///c:/Users/reddy/OneDrive/document/SLM%20fine%20tuning/notebook1/02_qwen7b_80k_source_extraction.ipynb)** | **Local** | Scaled source cleaning & extraction | Boosted extraction targeting **>2,000 samples each** for `CI-REPAIR-BENCH`, `Java OSS Travis`, and `LogChunks`. |
| **[`03_qwen7b_80k_master_dataset.ipynb`](file:///c:/Users/reddy/OneDrive/document/SLM%20fine%20tuning/notebook1/03_qwen7b_80k_master_dataset.ipynb)** | **Local** | Canonical schema & JSONL splits | Applies cryptographic deduplication, outputs **`train.jsonl` (80,000+ examples)**, and syncs to Hugging Face Hub for Kaggle. |
| **[`04_qwen7b_kaggle_finetuning.ipynb`](file:///c:/Users/reddy/OneDrive/document/SLM%20fine%20tuning/notebook1/04_qwen7b_kaggle_finetuning.ipynb)** | **Kaggle** | High-speed 7B QLoRA fine-tuning | Loads `Qwen2.5-Coder-7B-Instruct` in 4-bit NF4, trains LoRA adapter across 80k samples, pushes `krishna1707/buildfail-slm-qwen7b-adapter`. |
| **[`05_qwen7b_evaluation_benchmark.ipynb`](file:///c:/Users/reddy/OneDrive/document/SLM%20fine%20tuning/notebook1/05_qwen7b_evaluation_benchmark.ipynb)** | **Local** | Comprehensive 7B evaluation | Pulls the fine-tuned 7B adapter, tests in-distribution and isolated OOD sets across all 14 failure taxonomy categories. |

---

## 📊 Dataset Ingestion & Breakdown (With >2k Samples for Java, CI-Repair & LogChunks)

| # | Data Source / Table | Source File / Path | Raw Harvested Records | Key Categories & Role |
|:---:|---|---|:---:|---|
| **1** | **GHALogs** | `data/01_raw/ghalogs/runs.json.gz` | **84,000** | GitHub Actions workflow failures: **Tests** (22,000), **Dependencies** (18,000), **Docker/Containers** (16,000), **Config** (16,000), and **General/Build** (12,000) |
| **2** | **Travis CI Torrent** | `data/01_raw/travis/19314170/final-2017-01-25.csv.gz` | **40,000** | Multi-lingual build & test failure logs across Java, Python, Ruby, JS, and C++ |
| **3** | **CI/CD Self-Healing (Main)** | `data/01_raw/cicd_self_healing/main/cicd_pipeline_failures_dataset.csv` | **7,777** | Structured root-cause diagnostics, taxonomy categories, and terminal fix commands |
| **4** | **CI-REPAIR-BENCH** *(Scaled >2k)* | `data/01_raw/ci_repair_bench/ci_repair_dataset.parquet` | **6,582** | **Commit-level & granular per-file diff patches** (`diff --git a/... b/...`) with 100% paired ground-truth code diffs |
| **5** | **Java OSS Travis** *(Scaled >2k)* | `data/01_raw/java_travis/travis-ci-logs.tar` | **2,500** | Real Java OSS Maven/Gradle compiler & test failure traces from top repositories (`spring-boot`, `okhttp`, etc.) |
| **6** | **LogChunks** *(Scaled >2k)* | `data/01_raw/logchunks/LogChunks/LogChunks/` | **2,303** | 797 expert XML-annotated failure chunks + windowed failure context chunks from 816 multi-lingual `.log` files |
| **—** | **CI/CD Self-Healing (OOD)** | `data/01_raw/cicd_self_healing/ood/cicd_real_ood_world_dataset.csv` | **489** | *Strictly isolated* out-of-distribution benchmark (held out for evaluation) |
| **∑** | **Total Combined Raw Capacity** | — | **~143,651** | **Harvested across 6 distinct data tables** |

### Stratified Splits Produced after Cryptographic Deduplication:
- **`train.jsonl`**: **80,000+ high-quality instruction training samples** (ready for Kaggle fine-tuning, with significantly enriched code-diff and Java repair supervision).
- **`validation.jsonl`**: **~8,500 validation samples** (for real-time eval loss during training).
- **`test.jsonl`**: **~4,700 in-distribution test samples** (for local benchmark).
- **`ood_test.jsonl`**: **489 unseen repository samples** (for zero-shot OOD generalization benchmark).

---

## 🛠️ Step-by-Step Execution Guide

### 1. Local Data Preparation (`01`, `02`, `03`)
1. Run **`01_qwen7b_80k_data_ingestion.ipynb`** in VS Code / Jupyter to ensure all raw data directories in `data/01_raw/` are verified.
2. Run **`02_qwen7b_80k_source_extraction.ipynb`** to process the raw datasets with the boosted extraction logic (>2k each for CI-Repair, Java Travis, and LogChunks). Output is saved to `data/02_source_clean/`.
3. Run **`03_qwen7b_80k_master_dataset.ipynb`** to deduplicate records, build `unified_ci_failure.parquet`, and generate:
   - `data/04_finetuning/train.jsonl` (**80,000+ quality training examples**)
   - `data/04_finetuning/validation.jsonl`
   - `data/04_finetuning/test.jsonl`
   - `data/04_finetuning/ood_test.jsonl`
4. Use the optional Step 4 cell in `03_qwen7b_80k_master_dataset.ipynb` to upload the 80k dataset directly to your Hugging Face Hub repository (`krishna1707/buildfail-dataset`) so Kaggle can access it with one click.

### 2. Kaggle Fine-Tuning (`04_qwen7b_kaggle_finetuning.ipynb`)
1. Open **[Kaggle](https://www.kaggle.com)** and create a new notebook (`File > Upload Notebook > 04_qwen7b_kaggle_finetuning.ipynb`).
2. Configure **Settings** (Right sidebar):
   - **Accelerator**: `GPU T4 x2` (Dual Tesla T4 GPUs = 32 GB total VRAM) or `GPU P100 / A100`.
   - **Internet**: `On` (Required for downloading `Qwen/Qwen2.5-Coder-7B-Instruct` and pushing adapter).
   - **Persistence**: `Variables and files`.
3. Run all cells:
   - Step 1 installs required libraries.
   - Step 2 pulls `train.jsonl` and `validation.jsonl` from Hugging Face Hub (or Kaggle Input).
   - Step 3 loads `Qwen/Qwen2.5-Coder-7B-Instruct` in 4-bit NF4 quantization across both GPUs.
   - Step 4 executes the high-throughput `RobustSFTTrainer` fine-tuning loop over 80k samples.
   - Step 5 pushes the adapter to Hugging Face Model Hub (`krishna1707/buildfail-slm-qwen7b-adapter`).
   - Step 6 runs interactive inference testing root cause diagnosis and unified diff generation.

### 3. Local Evaluation (`05_qwen7b_evaluation_benchmark.ipynb`)
1. Open and run **`05_qwen7b_evaluation_benchmark.ipynb`** locally.
2. It automatically pulls `krishna1707/buildfail-slm-qwen7b-adapter` from Hugging Face Hub.
3. Evaluates:
   - Diagnostic classification accuracy on the 14-class taxonomy
   - Code patch / unified diff format validity
   - Zero-shot out-of-distribution (OOD) generalization

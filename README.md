# FixFlow — Autonomous CI/CD Failure Localization & Code Repair

**Powered by Fine-Tuned Small Language Model (`Qwen2.5-Coder-7B-Instruct` + QLoRA)**  
**Live Production Deployment:** [https://fixflow-beb5b.web.app](https://fixflow-beb5b.web.app)  
**Comprehensive End-to-End Documentation:** [docs/PROJECT_DOCUMENTATION.md](file:///c:/Users/reddy/OneDrive/document/SLM%20fine%20tuning/docs/PROJECT_DOCUMENTATION.md)

---

## 📌 Executive Summary
**FixFlow** (BuildFail-SLM) is an enterprise-grade AI/ML and DevOps engineering platform that autonomously ingests broken CI/CD pipeline runs, isolates failing stack traces and Abstract Syntax Tree (AST) contexts, and synthesizes syntactically valid unified code diffs (`--- a/... +++ b/...`) with repository-specific verification commands.

Unlike generic frontier LLM APIs, FixFlow runs **locally and privately on consumer GPU hardware** (~5.33 GB VRAM in 4-bit NF4 quantization on an NVIDIA RTX 3050 Laptop GPU), ensuring complete codebase security, zero per-token cloud costs, and sub-2-second patch generation.

```
Repository (URL / ZIP / Local)
   ↓
Repository & Workflow Analyzer (Language, Framework, Workflow Inputs)
   ↓
CI/CD Failure Chunk Localization (LogChunks, Traces, Assertions)
   ↓
Fine-Tuned Coding SLM (Qwen2.5-Coder-7B-Instruct + 80k-Sample QLoRA Adapter)
   ↓
Deterministic Consistency Gate & Patch Verifier (git apply check)
   ↓
Structured Diagnostic Output:
  - 13 Canonical Failure Categories (Zero Unknowns)
  - In-Depth Technical Root Cause Diagnosis
  - Actual Repair Target File & Repair Type
  - Non-Destructive Unified Diff (--- a/... +++ b/...)
  - Exact Terminal Verification Command (pytest, npm test, mvn test)
```

> **Non-Destructive Guarantee**: FixFlow is strictly read-only and diagnostic. It **never** mutates source code directly or makes unwanted commits. All patches are presented as unified diffs for human review.

---

## 🚀 Live Production & Model Assets

| Asset / Endpoint | Location / URL | Details |
| :--- | :--- | :--- |
| **Live Web App** | [https://fixflow-beb5b.web.app](https://fixflow-beb5b.web.app) | Multi-tenant Firebase Hosting with Google, GitHub, and Email Auth |
| **Alternative Web App** | [https://fixflow-beb5b.firebaseapp.com](https://fixflow-beb5b.firebaseapp.com) | Mirror CDN distribution |
| **Base Foundation Model** | [`Qwen/Qwen2.5-Coder-7B-Instruct`](https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct) | 7.61B parameter code intelligence foundation model |
| **Fine-Tuned Adapter** | [`krishna1707/buildfail-slm-qwen7b-adapter`](https://huggingface.co/krishna1707/buildfail-slm-qwen7b-adapter) | QLoRA adapter fine-tuned on 80,000+ CI failure-repair samples |
| **Curated Master Dataset** | [`krishna1707/buildfail-dataset`](https://huggingface.co/datasets/krishna1707/buildfail-dataset) | Harmonized multi-source CI failure dataset |
| **Local Backend API** | `http://127.0.0.1:8000` | FastAPI REST engine with PyTorch CUDA inference |
| **Local Frontend UI** | `http://localhost:3000` | Next.js 14/16 dashboard |

---

## 📁 Repository Structure
```text
.
├── backend/
│   ├── app.py                       # FastAPI REST API (Ingestion, Analysis, Pipeline)
│   ├── model.py                     # 4-bit NF4 SLM Loader on CUDA (Zero-fallback)
│   ├── predictor.py                 # ChatML Formatter, Predictor & Consistency Gate
│   ├── analyzer.py                  # AST, Stack trace, & Action input analyzer
│   ├── firebase_service.py          # Realtime Database sync & multi-tenant isolation
│   └── schemas.py                   # Pydantic request and response schemas
├── frontend/
│   ├── app/                         # Next.js App Router (Dashboard, Diff Viewer, Auth)
│   ├── lib/                         # Firebase client configuration (Google/GitHub Auth)
│   ├── public/                      # Static assets
│   └── package.json                 # Node dependencies
├── notebook1/                       # 80k Dataset & 7B QLoRA Fine-Tuning Suite
│   ├── 01_qwen7b_80k_data_ingestion.ipynb
│   ├── 02_qwen7b_80k_source_extraction.ipynb
│   ├── 03_qwen7b_80k_master_dataset.ipynb
│   ├── 04_qwen7b_kaggle_finetuning.ipynb
│   ├── 05_qwen7b_evaluation_benchmark.ipynb
│   └── README.md
├── docs/
│   └── PROJECT_DOCUMENTATION.md     # Full End-to-End Enterprise Specification
├── run.py                           # Unified single-command launcher (Backend + UI)
├── requirements.txt                 # Python dependencies
├── environment.yml                  # Conda environment definition
└── README.md
```

---

## 🎯 80k Master Dataset Suite (`notebook1/`)

The model is trained on a curated collection of **80,000+ high-quality failure-repair pairs** harvested across 6 distinct data tables:

| Source | Raw Records | Role in FixFlow | Direct Access URL |
| :--- | :---: | :--- | :--- |
| **Unified Master Dataset** | 80,000+ | Preprocessed & tokenized master train/val/test splits | [Hugging Face: krishna1707/buildfail-dataset](https://huggingface.co/datasets/krishna1707/buildfail-dataset) |
| **CI-REPAIR-BENCH** | 6,582 | Ground-truth paired code diffs (`diff --git a/... b/...`) | [Hugging Face: ci-benchmark-user/ci-repair-bench](https://huggingface.co/datasets/ci-benchmark-user/ci-repair-bench) |
| **GHALogs** | 84,000 | GitHub Actions workflow failures across tests & containers | [GitHub: PRL-PRG/ghalogs](https://github.com/PRL-PRG/ghalogs) / [Zenodo: 4646736](https://zenodo.org/record/4646736) |
| **Travis CI Torrent** | 40,000 | Multi-lingual build logs (Java, Python, JS, C++) | [TravisTorrent Portal](https://travistorrent.testroots.org/) |
| **CI/CD Self-Healing (Main & OOD)** | 8,266 | Root cause taxonomy, error classification, terminal commands | [GitHub: ai-cicd-failure-triage-agent](https://github.com/Vasishtha15/ai-cicd-failure-triage-agent) |
| **LogChunks** | 2,303 | Multilingual failure chunk localization (28+ languages) | [GitHub: gem-unipd/LogChunks](https://github.com/gem-unipd/LogChunks) / [Zenodo: 3874028](https://zenodo.org/record/3874028) |
| **Java OSS Travis-CI** | 2,500 | Real Maven/Gradle compiler and test failure traces | [GitHub: gem-unipd/travistorrent-tools](https://github.com/gem-unipd/travistorrent-tools) / [Zenodo: 1040474](https://zenodo.org/record/1040474) |

### 📚 Individual Dataset Details & Source URLs

1. **Unified Master Training & Evaluation Dataset**
   - **URL:** [https://huggingface.co/datasets/krishna1707/buildfail-dataset](https://huggingface.co/datasets/krishna1707/buildfail-dataset)
   - **Description:** Complete 80,000+ sample curated, deduplicated, and ChatML-tokenized master dataset containing `train.jsonl` (70,000 samples), `validation.jsonl` (6,240 samples), and `test.jsonl` (3,760 samples) partitioned using strict repository-level isolation to prevent data leakage.

2. **CI-REPAIR-BENCH (Developer Code-Diff Ground Truth)**
   - **URL:** [https://huggingface.co/datasets/ci-benchmark-user/ci-repair-bench](https://huggingface.co/datasets/ci-benchmark-user/ci-repair-bench)
   - **Description:** Primary code repair supervision dataset containing pairs of broken CI/CD builds and the exact developer git unified diff patches that resolved them across Python, JavaScript, Java, Go, and Ruby.

3. **GHALogs (GitHub Actions Workflow Mining)**
   - **URL:** [https://github.com/PRL-PRG/ghalogs](https://github.com/PRL-PRG/ghalogs) · [Zenodo: 4646736](https://zenodo.org/record/4646736)
   - **Description:** Large-scale mining of real-world GitHub Actions workflow executions, capturing workflow step YAML configurations, dependency installation failures, container execution crashes, and runner timeout telemetry.

4. **TravisTorrent Dataset**
   - **URL:** [https://travistorrent.testroots.org/](https://travistorrent.testroots.org/)
   - **Description:** Longitudinal dataset containing millions of continuous integration build logs from open-source GitHub projects, providing rich multi-lingual build failure and test failure contexts.

5. **CI/CD Self-Healing Agent Corpus (Main & OOD)**
   - **URL:** [https://github.com/Vasishtha15/ai-cicd-failure-triage-agent](https://github.com/Vasishtha15/ai-cicd-failure-triage-agent)
   - **Description:** Curated failure logs mapped to the 13-class failure taxonomy, root-cause explanations, and terminal remediation commands, including a held-out out-of-distribution (OOD) benchmark set for generalization testing.

6. **LogChunks (Multilingual Failure Chunk Localization)**
   - **URL:** [https://github.com/gem-unipd/LogChunks](https://github.com/gem-unipd/LogChunks) · [Zenodo: 3874028](https://zenodo.org/record/3874028)
   - **Description:** Expert XML-annotated failure logs spanning 28+ programming languages, providing ground-truth spans for the exact lines in multi-thousand-line CI logs where the root cause occurred.

7. **Java OSS Travis-CI**
   - **URL:** [https://github.com/gem-unipd/travistorrent-tools](https://github.com/gem-unipd/travistorrent-tools) · [Zenodo: 1040474](https://zenodo.org/record/1040474)
   - **Description:** Targeted corpus of real-world Maven, Gradle, and Ant compilation errors, Java type mismatches, and JUnit assertion failures.

> **Hugging Face Model & Artifact Links:**
> - **Fine-Tuned QLoRA Adapter:** [`https://huggingface.co/krishna1707/buildfail-slm-qwen7b-adapter`](https://huggingface.co/krishna1707/buildfail-slm-qwen7b-adapter)
> - **Foundation Base Model:** [`https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct`](https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct)

---

## 🛠️ Quickstart & Local Execution

### 1. Environment Setup
```bash
# Clone the repository
git clone https://github.com/Reddy-1-eng/FixFlow.git
cd FixFlow

# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\activate   # Linux/macOS: source .venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Install Frontend dependencies
cd frontend
npm install
cd ..
```

### 2. Configure Environment (`.env`)
```bash
cp .env.example .env
```
Ensure `.env` contains your Hugging Face credentials:
```env
BASE_MODEL_NAME=Qwen/Qwen2.5-Coder-7B-Instruct
ADAPTER_OUTPUT_DIR=krishna1707/buildfail-slm-qwen7b-adapter
HUGGINGFACE_TOKEN=hf_your_token_here
BACKEND_PORT=8000
```

### 3. Launch with One Command
```bash
python run.py
```
`run.py` automatically:
1. Cleans lingering processes on ports 8000 and 3000.
2. Starts the **FastAPI backend** on `http://127.0.0.1:8000` (loading the 7B model in 4-bit NF4 onto CUDA).
3. Starts the **Next.js frontend** on `http://localhost:3000`.
4. Opens your default browser to `http://localhost:3000`.

---

## 📖 Complete Documentation
For exhaustive architectural diagrams, quantitative benchmarks, API schemas, multi-tenant security architecture, and training details, see:
👉 **[PROJECT_DOCUMENTATION.md](file:///c:/Users/reddy/OneDrive/document/SLM%20fine%20tuning/docs/PROJECT_DOCUMENTATION.md)**

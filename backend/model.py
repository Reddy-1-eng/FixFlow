"""
BuildFail-SLM: Model Loader
Loads the fine-tuned PEFT/QLoRA adapter directly from Hugging Face Model Hub
with 4-bit NF4 quantization on CUDA (zero fallback mode).
"""

import os
os.environ["TQDM_DISABLE"] = "1"

import torch
from pathlib import Path
from typing import Optional
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from transformers.utils.logging import disable_progress_bar
disable_progress_bar()
from peft import PeftModel


def get_hf_token() -> Optional[str]:
    """Retrieve Hugging Face token strictly from server environment or backend .env file."""
    token = os.getenv("HUGGINGFACE_TOKEN") or os.getenv("HF_TOKEN")
    if token:
        return token
    for p in [Path(".env"), Path("../.env")]:
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("HUGGINGFACE_TOKEN=") or line.strip().startswith("HF_TOKEN="):
                    return line.split("=", 1)[1].strip("\"' ")
    return None


class ModelLoader:
    def __init__(self, base_model_name: Optional[str] = None, adapter_path: Optional[str] = None):
        self.base_model_name = base_model_name or os.getenv("BASE_MODEL_NAME", "Qwen/Qwen2.5-Coder-7B-Instruct")
        self.adapter_path = adapter_path or os.getenv("ADAPTER_OUTPUT_DIR", "krishna1707/buildfail-slm-qwen7b-adapter")
        self.hf_token = get_hf_token()
        self.model = None
        self.tokenizer = None
        self.device = "cuda:0"

    def load(self):
        """Loads fine-tuned BuildFail-SLM adapter directly from Hugging Face Hub with zero fallbacks."""
        if self.model is not None and self.tokenizer is not None:
            return

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA GPU is required to run BuildFail-SLM 7B. Strict mode: No CPU fallback allowed.")

        print(f"Loading BuildFail-SLM fine-tuned adapter from: https://huggingface.co/{self.adapter_path} (Device: cuda:0)...")
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.adapter_path,
            token=self.hf_token,
            trust_remote_code=True
        )
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        if hasattr(self.tokenizer, "model_max_length") and self.tokenizer.model_max_length < 2048:
            self.tokenizer.model_max_length = 32768

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True
        )

        base = AutoModelForCausalLM.from_pretrained(
            self.base_model_name,
            token=self.hf_token,
            quantization_config=bnb_config,
            device_map={"": 0},
            trust_remote_code=True
        )
        self.device = "cuda:0"

        self.model = PeftModel.from_pretrained(base, self.adapter_path, token=self.hf_token)
        if not isinstance(self.model, PeftModel):
            raise RuntimeError(f"Failed to attach fine-tuned adapter '{self.adapter_path}'. Zero fallback mode.")

        self.model.eval()
        self.model.config.use_cache = True
        diag = self.get_diagnostics()
        print("\n" + "="*50)
        print("MODEL_BASE:       ", diag["model_base"])
        print("MODEL_ADAPTER:    ", diag["model_adapter"])
        print("ADAPTER_LOADED:   ", diag["adapter_loaded"])
        print("MODEL_DEVICE:     ", diag["device"])
        print("="*50 + "\n")
        print("[OK] BuildFail-SLM fine-tuned adapter successfully initialized and ready for inference!")

    def get_diagnostics(self) -> dict:
        """Return diagnostic state of model and adapter (Section 4)."""
        adapter_loaded = isinstance(self.model, PeftModel) if self.model is not None else False
        return {
            "model_base": self.base_model_name,
            "model_adapter": self.adapter_path,
            "adapter_loaded": adapter_loaded,
            "model_loaded": self.model is not None,
            "device": self.device
        }

    def generate(self, prompt: str, max_new_tokens: int = 1024) -> str:
        """Inference pass returning raw generation from the fine-tuned SLM with zero fallbacks."""
        if self.model is None or self.tokenizer is None:
            self.load()

        if not isinstance(self.model, PeftModel):
            raise RuntimeError("Fine-tuned SLM Adapter is not loaded. Zero fallback allowed.")

        inputs = self.tokenizer(prompt, return_tensors="pt").to("cuda:0")
        with torch.inference_mode():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                temperature=0.1,
                top_p=0.9,
                use_cache=True,
                pad_token_id=self.tokenizer.eos_token_id
            )
        return self.tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)

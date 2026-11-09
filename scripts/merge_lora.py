"""把 LoRA adapter 合并进基座，产出可直接转 GGUF 的完整权重。

用法：
  python scripts/merge_lora.py <base_model> <adapter_dir> <output_dir>
"""

from __future__ import annotations

import sys

from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer


def main(base_path: str, adapter: str, out: str) -> None:
    tokenizer = AutoTokenizer.from_pretrained(base_path)
    base = AutoModelForCausalLM.from_pretrained(
        base_path, dtype="auto", device_map={"": "cpu"}, low_cpu_mem_usage=True
    )
    model = PeftModel.from_pretrained(base, adapter)
    merged = model.merge_and_unload()
    merged.save_pretrained(out, safe_serialization=True, max_shard_size="4GB")
    tokenizer.save_pretrained(out)
    print("MERGED_OK", out)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("usage: python scripts/merge_lora.py <base> <adapter> <out>")
    main(*sys.argv[1:])

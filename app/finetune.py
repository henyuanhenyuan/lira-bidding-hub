"""LoRA / SFT 测试链路：从真实研判与金标用例导出数据，生成 PEFT/TRL 配置。

本机不安装 torch/transformers 也能跑通「数据 → 配置 → 校验」；
训练本身交给 PEFT + TRL（报告里点名的标准选型），不做自研训练框架。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

from . import config, db

ACTION_TEXT = {
    "follow": "考虑跟进调价",
    "hold": "建议先观察",
    "adjust_coupon": "可投放店铺券对冲",
    "join_promo": "可报名同类活动",
    "no_action": "数据不足，保持现状",
}

SFT_SYSTEM = (
    "你是电商竞价分析助手。只根据给定事实输出 JSON："
    '{"action":"follow|hold|adjust_coupon|join_promo|no_action",'
    '"confidence":0到1,"narrative":"不超过60字的中文说明"}。'
    "不得编造事实，动作必须与严重度一致。"
)

TARGET_MODULES = [
    "q_proj", "k_proj", "v_proj", "o_proj",
    "gate_proj", "up_proj", "down_proj",
]


def finetune_dir() -> Path:
    path = Path(config.DATA_DIR) / "finetune"
    path.mkdir(parents=True, exist_ok=True)
    return path


def stack_status() -> dict[str, Any]:
    core = ("torch", "transformers", "peft", "trl", "datasets")
    extra = ("accelerate", "bitsandbytes")
    found = {name: bool(importlib.util.find_spec(name)) for name in (*core, *extra)}
    installed = all(found[name] for name in core)
    return {
        "framework": {"trainer": "trl.SFTTrainer", "peft": "peft.LoraConfig"},
        "modules": found,
        "installed": installed,
        "qlora_ready": installed and found["bitsandbytes"] and found["accelerate"],
        "note": (
            "训练依赖未安装不影响线上推理；导出数据与配置可直接在 GPU 机器上执行。"
            if not installed
            else "训练依赖齐全，可执行生成脚本。"
        ),
    }


def _facts_from_event(row: Any) -> dict[str, Any]:
    return {
        "title": row["title"],
        "event_type": row["event_type"],
        "severity": row["severity"],
        "my_price": row["my_price"],
        "price_low": row["price_low"],
        "price_high": row["price_high"],
        "action_hint": None,
    }


def _golden_samples(conn, limit: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT name, payload, expected_action, expected_event_type FROM eval_case"
        " ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    samples: list[dict[str, Any]] = []
    for row in rows:
        action = row["expected_action"]
        event_type = row["expected_event_type"] or "price_drop"
        narrative = f"{row['name']}：价格序列显示{event_type}，按 SOP 建议{ACTION_TEXT.get(action, action)}。"
        try:
            facts = json.loads(row["payload"])
        except (TypeError, ValueError):
            facts = {"case": row["name"]}
        samples.append(
            {
                "messages": [
                    {"role": "system", "content": SFT_SYSTEM},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "case": row["name"],
                                "event_type": event_type,
                                "facts": facts,
                            },
                            ensure_ascii=False,
                        )[:2400],
                    },
                    {
                        "role": "assistant",
                        "content": json.dumps(
                            {"action": action, "confidence": 0.7, "narrative": narrative},
                            ensure_ascii=False,
                        ),
                    },
                ],
                "meta": {"source": "golden", "case": row["name"]},
            }
        )
    return samples


def _suggestion_samples(conn, limit: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT s.action, s.confidence, s.narrative, s.guardrail,"
        " e.type AS event_type, e.severity, t.title, t.my_price,"
        " pp.price_low, pp.price_high"
        " FROM suggestion s"
        " JOIN event e ON e.id = s.event_id"
        " LEFT JOIN target t ON t.id = e.target_id"
        " LEFT JOIN price_point pp ON pp.target_id = e.target_id"
        "   AND pp.ts = (SELECT MAX(ts) FROM price_point WHERE target_id = e.target_id)"
        " WHERE s.narrative IS NOT NULL AND length(s.narrative) >= 8"
        " ORDER BY s.created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    samples: list[dict[str, Any]] = []
    for row in rows:
        facts = {
            "title": row["title"],
            "event_type": row["event_type"],
            "severity": row["severity"],
            "my_price": row["my_price"],
            "price_low": row["price_low"],
            "price_high": row["price_high"],
            "guardrail": row["guardrail"],
        }
        samples.append(
            {
                "messages": [
                    {"role": "system", "content": SFT_SYSTEM},
                    {"role": "user", "content": json.dumps(facts, ensure_ascii=False)},
                    {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "action": row["action"],
                                "confidence": round(float(row["confidence"] or 0.6), 2),
                                "narrative": row["narrative"],
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
                "meta": {"source": "suggestion", "event_type": row["event_type"]},
            }
        )
    return samples


def build_dataset(conn, limit: int = 400) -> dict[str, Any]:
    real = _suggestion_samples(conn, limit)
    golden = _golden_samples(conn, max(20, limit - len(real)))
    samples = real + golden
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for sample in samples:
        key = sample["messages"][-1]["content"]
        if key in seen:
            continue
        seen.add(key)
        unique.append(sample)

    path = finetune_dir() / f"sft-{db.now_iso().replace(':', '').replace('+', '_')}.jsonl"
    chars = 0
    with path.open("w", encoding="utf-8") as handle:
        for sample in unique:
            line = json.dumps(sample, ensure_ascii=False)
            chars += len(line)
            handle.write(line + "\n")

    return {
        "path": str(path),
        "name": path.name,
        "samples": len(unique),
        "from_suggestions": len(real),
        "from_golden": len(golden),
        "chars": chars,
        "estimated_tokens": int(chars / 1.6),
        "system_prompt": SFT_SYSTEM,
    }


def latest_dataset() -> dict[str, Any] | None:
    files = sorted(finetune_dir().glob("sft-*.jsonl"), key=lambda item: item.stat().st_mtime, reverse=True)
    if not files:
        return None
    path = files[0]
    lines = path.read_text(encoding="utf-8").splitlines()
    return {
        "path": str(path),
        "name": path.name,
        "samples": len([line for line in lines if line.strip()]),
        "bytes": path.stat().st_size,
    }


def _config(base_model: str, dataset_path: str, method: str, epochs: int, lr: float) -> dict[str, Any]:
    return {
        "method": method,
        "base_model": base_model,
        "dataset": dataset_path,
        "device": "auto",
        "framework": {
            "trainer": "trl.SFTTrainer",
            "peft": "peft.LoraConfig",
            "note": "使用标准 PEFT/TRL，不引入自研训练框架",
        },
        "quantization": {
            "load_in_4bit": method == "qlora",
            "bnb_4bit_quant_type": "nf4",
            "bnb_4bit_compute_dtype": "bfloat16",
            "bnb_4bit_use_double_quant": True,
        },
        "lora": {
            "r": 16,
            "alpha": 32,
            "dropout": 0.05,
            "target_modules": TARGET_MODULES,
            "bias": "none",
        },
        "train": {
            "epochs": epochs,
            "learning_rate": lr,
            "batch_size": 1,
            "gradient_accumulation": 4,
            "max_seq_length": 512,
            "max_steps": -1,
            "bf16": True,
            "gradient_checkpointing": method == "qlora",
            "logging_steps": 5,
            "max_gpu_memory": "7GiB",
            "max_cpu_memory": "24GiB",
        },
        "output_dir": f"data/finetune/{method}-out",
    }


TRAIN_SCRIPT = '''"""自动生成：PEFT + TRL LoRA / QLoRA 启动脚本。

用法：
  pip install torch transformers peft trl datasets accelerate bitsandbytes
  python data/finetune/train_lora.py --config <config.json>

本脚本不使用自研训练框架；参数改 config 即可。
"""
import inspect
import json
import sys
import time
from pathlib import Path

import torch
import transformers
from datasets import load_dataset
from peft import LoraConfig
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import SFTConfig, SFTTrainer


def _dtype(name):
    return getattr(torch, name or "bfloat16")


def _dtype_key():
    major = int(transformers.__version__.split(".")[0])
    return "dtype" if major >= 5 else "torch_dtype"


def _supported(cls, keys):
    params = inspect.signature(cls.__init__).parameters
    return [key for key in keys if key in params]


def main(config_path: str) -> None:
    cfg = json.load(open(config_path, encoding="utf-8"))
    train = cfg["train"]
    quant = cfg.get("quantization") or {}
    started = time.time()

    tokenizer = AutoTokenizer.from_pretrained(cfg["base_model"], trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    device = cfg.get("device") or "auto"
    max_memory = None
    if device == "cpu":
        device_map = {"": "cpu"}
    elif device == "cuda":
        device_map = {"": 0}
    else:
        device_map = "auto"
        if train.get("max_gpu_memory"):
            max_memory = {
                0: train["max_gpu_memory"],
                "cpu": train.get("max_cpu_memory", "24GiB"),
            }
    kwargs = {"trust_remote_code": True, "low_cpu_mem_usage": True, "device_map": device_map}
    if max_memory:
        kwargs["max_memory"] = max_memory
    if quant.get("load_in_4bit"):
        from transformers import BitsAndBytesConfig

        kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type=quant.get("bnb_4bit_quant_type", "nf4"),
            bnb_4bit_compute_dtype=_dtype(quant.get("bnb_4bit_compute_dtype")),
            bnb_4bit_use_double_quant=bool(quant.get("bnb_4bit_use_double_quant", True)),
        )
        kwargs[_dtype_key()] = _dtype(quant.get("bnb_4bit_compute_dtype"))
    else:
        kwargs[_dtype_key()] = "auto"

    model = AutoModelForCausalLM.from_pretrained(cfg["base_model"], **kwargs)
    if train.get("gradient_checkpointing"):
        model.gradient_checkpointing_enable()
        model.enable_input_require_grads()
    model.config.use_cache = False

    dataset = load_dataset("json", data_files=cfg["dataset"], split="train")

    def render(row):
        text = tokenizer.apply_chat_template(
            row["messages"], tokenize=False, add_generation_prompt=False
        )
        return {"text": text}

    dataset = dataset.map(render, remove_columns=dataset.column_names)
    peft = LoraConfig(
        r=cfg["lora"]["r"],
        lora_alpha=cfg["lora"]["alpha"],
        lora_dropout=cfg["lora"]["dropout"],
        target_modules=cfg["lora"]["target_modules"],
        bias=cfg["lora"]["bias"],
        task_type="CAUSAL_LM",
    )

    options = {
        "output_dir": cfg["output_dir"],
        "num_train_epochs": train["epochs"],
        "learning_rate": train["learning_rate"],
        "per_device_train_batch_size": train["batch_size"],
        "gradient_accumulation_steps": train["gradient_accumulation"],
        "gradient_checkpointing": bool(train.get("gradient_checkpointing")),
        "bf16": bool(train.get("bf16")),
        "logging_steps": train.get("logging_steps", 5),
        "report_to": "none",
        "save_strategy": "no",
        "dataset_text_field": "text",
    }
    if device == "cpu":
        options["use_cpu"] = True
    if train.get("max_steps", -1) and train["max_steps"] > 0:
        options["max_steps"] = int(train["max_steps"])
    length_keys = _supported(SFTConfig, ("max_length", "max_seq_length"))
    if length_keys:
        options[length_keys[0]] = train["max_seq_length"]
    args = SFTConfig(**options)

    trainer_kwargs = {"model": model, "args": args, "train_dataset": dataset, "peft_config": peft}
    if "processing_class" in inspect.signature(SFTTrainer.__init__).parameters:
        trainer_kwargs["processing_class"] = tokenizer
    trainer = SFTTrainer(**trainer_kwargs)
    result = trainer.train()

    out = Path(cfg["output_dir"])
    trainer.save_model(str(out))
    tokenizer.save_pretrained(str(out))
    metrics = getattr(result, "metrics", {}) or {}
    summary = {
        "train_loss": round(float(result.training_loss), 6),
        "steps": int(result.global_step),
        "epochs": round(float(metrics.get("epoch", getattr(result, "epoch", 0) or 0)), 4),
        "runtime_s": round(time.time() - started, 1),
        "device": str(trainer.model.device),
        "output_dir": str(out),
    }
    (out / "train_metrics.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--config") + 1])
'''


def create_job(
    conn,
    *,
    name: str,
    base_model: str,
    method: str,
    teacher: str,
    epochs: int,
    lr: float,
    dataset_path: str,
    actor: str,
) -> dict[str, Any]:
    if method not in {"lora", "qlora", "sft"}:
        raise ValueError("method 只能是 lora / qlora / sft")
    if not dataset_path or not Path(dataset_path).exists():
        raise ValueError("数据集不存在，请先生成数据集")
    job_id = db.new_id()
    folder = finetune_dir()
    config_path = folder / f"config-{job_id}.json"
    config_path.write_text(
        json.dumps(_config(base_model, dataset_path, method, epochs, lr), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    script_path = folder / "train_lora.py"
    script_path.write_text(TRAIN_SCRIPT, encoding="utf-8")
    samples = sum(1 for line in Path(dataset_path).read_text(encoding="utf-8").splitlines() if line.strip())
    now = db.now_iso()
    conn.execute(
        "INSERT INTO finetune_job (id, name, base_model, method, teacher, dataset_path,"
        " config_path, samples, status, created_by, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            job_id, name, base_model, method, teacher, dataset_path,
            str(config_path), samples, "ready", actor, now, now,
        ),
    )
    return get_job(conn, job_id)


def get_job(conn, job_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM finetune_job WHERE id = ?", (job_id,)).fetchone()
    if not row:
        raise KeyError(job_id)
    job = dict(row)
    config_path = Path(job["config_path"]) if job["config_path"] else None
    if config_path and config_path.exists():
        job["config"] = json.loads(config_path.read_text(encoding="utf-8"))
    else:
        job["config"] = None
    return job


def list_jobs(conn, limit: int = 20) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, name, base_model, method, teacher, samples, status,"
        " created_by, created_at, updated_at FROM finetune_job"
        " ORDER BY created_at DESC LIMIT ?",
        (max(1, min(100, limit)),),
    ).fetchall()
    return [dict(row) for row in rows]


def validate_job(conn, job_id: str) -> dict[str, Any]:
    job = get_job(conn, job_id)
    checks: list[dict[str, Any]] = []
    errors: list[str] = []

    dataset = Path(job["dataset_path"])
    if not dataset.exists():
        errors.append("数据集文件不存在")
        checks.append({"name": "dataset.exists", "ok": False})
    else:
        lines = [line for line in dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
        bad = 0
        for line in lines:
            try:
                row = json.loads(line)
                roles = [item.get("role") for item in row.get("messages", [])]
                if roles != ["system", "user", "assistant"]:
                    bad += 1
            except ValueError:
                bad += 1
        ok = bool(lines) and bad == 0
        if not ok:
            errors.append(f"数据行不合法：{bad} / {len(lines)}")
        checks.append({"name": "dataset.jsonl", "ok": ok, "detail": f"{len(lines)} 行，坏行 {bad}"})

    config = job.get("config") or {}
    config_ok = bool(config.get("base_model") and config.get("lora") and config.get("train"))
    if not config_ok:
        errors.append("训练配置缺字段")
    checks.append({"name": "config.peft_trl", "ok": config_ok})

    stack = stack_status()
    checks.append(
        {
            "name": "deps.train_stack",
            "ok": stack["installed"],
            "detail": stack["note"],
        }
    )

    now = db.now_iso()
    status = "validated" if not errors else "invalid"
    conn.execute(
        "UPDATE finetune_job SET status = ?, detail = ?, updated_at = ? WHERE id = ?",
        (status, json.dumps({"checks": checks, "errors": errors}, ensure_ascii=False), now, job_id),
    )
    return {
        "id": job_id,
        "ok": not errors,
        "checks": checks,
        "errors": errors,
        "deps_ready": stack["installed"],
        "train_command": f"python data/finetune/train_lora.py --config {job['config_path']}",
        "status": status,
    }

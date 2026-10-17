"""Local DeepSeek-R1-Distill-Qwen-1.5B inference with the shared MCP data source."""
from __future__ import annotations

import json
import os
import threading
from typing import Any, Iterator

MODEL_ID = "deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B"
_MODEL_LOCK = threading.Lock()
_TOKENIZER = None
_MODEL = None
_LOAD_ERROR: str | None = None


def _model_path() -> str:
    configured = os.environ.get("LOCAL_MODEL_PATH", "").strip()
    if configured:
        return configured
    configured_cache = os.environ.get("LOCAL_MODEL_CACHE", "").strip()
    base = configured_cache or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "cache", "models"))
    return os.path.join(base, "deepseek-ai", "DeepSeek-R1-Distill-Qwen-1.5B")


def load_model() -> tuple[Any, Any]:
    global _TOKENIZER, _MODEL, _LOAD_ERROR
    if _TOKENIZER is not None and _MODEL is not None:
        return _TOKENIZER, _MODEL
    with _MODEL_LOCK:
        if _TOKENIZER is not None and _MODEL is not None:
            return _TOKENIZER, _MODEL
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            path = _model_path()
            if not os.path.isdir(path):
                from modelscope import snapshot_download

                os.makedirs(os.path.dirname(path), exist_ok=True)
                snapshot_download(MODEL_ID, cache_dir=os.path.dirname(os.path.dirname(path)))
            if not os.path.isdir(path):
                raise FileNotFoundError(f"本地模型权重目录不存在：{path}")
            tokenizer = AutoTokenizer.from_pretrained(path, trust_remote_code=True)
            kwargs: dict[str, Any] = {"trust_remote_code": True, "device_map": "auto"}
            kwargs["dtype"] = torch.float16 if torch.cuda.is_available() else torch.float32
            model = AutoModelForCausalLM.from_pretrained(path, **kwargs).eval()
            if getattr(model.config, "pad_token_id", None) is None:
                model.config.pad_token_id = tokenizer.eos_token_id
            _TOKENIZER, _MODEL = tokenizer, model
            _LOAD_ERROR = None
            return tokenizer, model
        except Exception as exc:  # model loading errors are shown by /health
            _LOAD_ERROR = str(exc).strip() or "本地模型加载失败"
            raise RuntimeError(_LOAD_ERROR) from exc


def status() -> dict[str, Any]:
    if _TOKENIZER is not None and _MODEL is not None:
        return {"modelReady": True, "model": MODEL_ID, "modelPath": _model_path()}
    installed = os.path.isfile(os.path.join(_model_path(), "config.json"))
    return {"modelReady": installed, "modelInstalled": installed, "model": MODEL_ID, "modelPath": _model_path(), "message": _LOAD_ERROR or ("本地模型权重已安装，首次推理时加载" if installed else "本地模型未安装，首次推理将从 ModelScope 下载约 3.55 GB 权重")}


def _mcp_context(mcp_context: Any) -> str:
    if not mcp_context:
        return ""
    return "\n以下是通过与云端智投相同的今日投资 MCP 获取的实时数据。仅使用这些数据中明确存在的事实：\n" + json.dumps(mcp_context, ensure_ascii=False, default=str)


def _messages(prompt: str, system_prompt: str, history: list[dict[str, str]], mcp_context: Any = None) -> list[dict[str, str]]:
    system = (system_prompt or "你是智投问答。请客观分析，不承诺收益。") + _mcp_context(mcp_context)
    messages = [{"role": "system", "content": system}]
    messages.extend({"role": str(item.get("role") or "user"), "content": str(item.get("content") or "")} for item in history[-8:])
    messages.append({"role": "user", "content": prompt})
    return messages


def generate(prompt: str, system_prompt: str = "", history: list[dict[str, str]] | None = None, mcp_context: Any = None) -> Iterator[str]:
    tokenizer, model = load_model()
    messages = _messages(prompt, system_prompt, history or [], mcp_context)
    if hasattr(tokenizer, "apply_chat_template"):
        encoded = tokenizer.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt")
        model_device = getattr(model, "device", None)
        if model_device is not None:
            encoded = encoded.to(model_device)
    else:
        encoded = tokenizer("\n".join(f"{m['role']}: {m['content']}" for m in messages), return_tensors="pt").to(model.device)
    input_length = encoded.shape[-1]
    import torch
    with torch.no_grad():
        output = model.generate(encoded, max_new_tokens=int(os.environ.get("LOCAL_MODEL_MAX_NEW_TOKENS", "512")), do_sample=True, temperature=0.6, top_p=0.9, pad_token_id=tokenizer.eos_token_id)
    text = tokenizer.decode(output[0][input_length:], skip_special_tokens=True).strip()
    for index in range(0, len(text), 24):
        yield text[index:index + 24]

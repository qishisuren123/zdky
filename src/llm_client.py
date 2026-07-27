"""
LLM 统一调用客户端
支持: Gemini (OpenAI 兼容) / Claude (Anthropic Messages API 或兼容网关) / GPT 系（OpenAI 兼容渠道，
支持一个可选的"免费/优先渠道"与一个"付费/兜底渠道"双通道回落）
本地 key 从 AUTORESEARCH_CONFIG 指向的私有配置或环境变量读取

免费窗口路由（北京时间 00:00-08:00，如已在私有配置里启用可选免费渠道）：
  - GPT: 优先走可选免费渠道（Responses API），失败回落付费渠道
  - Claude: 部分免费网关对 Anthropic 协议兼容性较差，若探测到异常则始终走付费渠道；
            免费渠道版本仅建议配合 Claude Code CLI 使用。

代理策略：
  - 如部署环境访问受限，可通过 AUTORESEARCH_PROXY_URL 配置一个本地代理（默认 http://127.0.0.1:7890）
  - 启动前自动 TCP 探测代理是否存活；如代理死了：
      · 需要代理的可选渠道 → 明确报错并返回 None，**不会崩**
      · 不需要代理的付费/直连渠道 → 正常工作
  - 所有调用强制 trust_env=False，避免环境变量污染
"""

import json
import os
import httpx
import socket
import time as _global_time
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config.local.json"
EXAMPLE_CONFIG_PATH = REPO_ROOT / "config.example.json"
CONFIG_PATH = Path(os.environ.get("AUTORESEARCH_CONFIG", DEFAULT_CONFIG_PATH))
PROXY_URL = os.environ.get("AUTORESEARCH_PROXY_URL", "http://127.0.0.1:7890")
_proxy = urlparse(PROXY_URL)
_PROXY_HOST = _proxy.hostname or "127.0.0.1"
_PROXY_PORT = _proxy.port or 7890


_PROXY_CACHE = {"checked_at": 0.0, "alive": None}


def proxy_alive(ttl_seconds=20):
    """快速 TCP 探测代理端口是否监听；结果缓存 ttl_seconds 秒"""
    now = _global_time.time()
    if _PROXY_CACHE["alive"] is not None and now - _PROXY_CACHE["checked_at"] < ttl_seconds:
        return _PROXY_CACHE["alive"]
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.5)
        ok = s.connect_ex((_PROXY_HOST, _PROXY_PORT)) == 0
        s.close()
    except Exception:
        ok = False
    _PROXY_CACHE["alive"] = ok
    _PROXY_CACHE["checked_at"] = now
    return ok


def _httpx_kwargs(needs_proxy, *, timeout=120):
    """
    返回 httpx.Client 的标准 kwargs。
    - needs_proxy=True：仅在代理活着时加 proxy；代理死时返回 None（上层应跳过/降级）
    - needs_proxy=False：明确不走代理，且 trust_env=False 避免 env 污染
    """
    base = {"timeout": timeout, "trust_env": False}
    if not needs_proxy:
        return base
    if proxy_alive():
        base["proxy"] = PROXY_URL
        return base
    return None  # 信号：代理需要但不可用


def load_config():
    path = CONFIG_PATH.expanduser()
    if not path.exists():
        path = EXAMPLE_CONFIG_PATH
    with open(path) as f:
        return json.load(f)


def get_preset(name):
    config = load_config()
    return config.get("presets", {}).get(name)


def _cfg_value(cfg, key, default=None):
    """Read a config value directly or from an environment-variable indirection.

    Public templates use fields such as api_key_env/base_url_env so users can
    keep secrets out of Git. Private legacy configs with direct api_key/base_url
    values continue to work.
    """
    env_key = cfg.get(f"{key}_env")
    if env_key:
        value = os.environ.get(env_key)
        if value:
            return value
    return cfg.get(key, default)


def _cfg_list(cfg, key):
    """Read a list config value, supporting comma-separated env values."""
    env_key = cfg.get(f"{key}_env")
    if env_key:
        value = os.environ.get(env_key)
        if value:
            return [item.strip() for item in value.split(",") if item.strip()]
    value = cfg.get(key, [])
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


def _require_cfg_value(cfg, key, preset_name):
    value = _cfg_value(cfg, key)
    if value:
        return value
    env_key = cfg.get(f"{key}_env")
    suffix = f" or set ${env_key}" if env_key else ""
    raise RuntimeError(f"Preset '{preset_name}' is missing '{key}'{suffix}")


def _resolve_alias(name):
    """Map public short aliases to concrete preset names."""
    config = load_config()
    aliases = config.get("aliases", {}) or config.get("_aliases", {})
    return aliases.get(name, name)


def _resolve_claude_preset(name):
    """把短名映射到真实 preset 名"""
    return _resolve_alias(name)


# ============================================================
# 单一 provider 简易模式：只需一个 OpenAI 兼容的 base_url + api_key
# 就能跑通全流程，不需要任何 config.json / config.local.json。
# 优先级最高：只要下面两个环境变量都设置了，call_model() 就会无视
# 具体传入的模型名，统一走这一个端点。
# ============================================================
SIMPLE_BASE_URL = os.environ.get("AUTORESEARCH_API_BASE_URL")
SIMPLE_API_KEY = os.environ.get("AUTORESEARCH_API_KEY")
SIMPLE_MODEL = os.environ.get("AUTORESEARCH_API_MODEL", "gpt-4o-mini")


def simple_mode_enabled():
    return bool(SIMPLE_BASE_URL and SIMPLE_API_KEY)


def call_simple(prompt, temperature=0.3, max_tokens=2000, retries=3, **_ignored):
    """通用 OpenAI 兼容 Chat Completions 调用：一个 base_url + 一个 api_key 打通全流程。

    只要设置 AUTORESEARCH_API_BASE_URL 和 AUTORESEARCH_API_KEY，任何声称支持
    OpenAI Chat Completions 协议的网关都可以直接用（包括几乎所有商业中转/自建网关）。
    """
    if not simple_mode_enabled():
        raise RuntimeError(
            "Simple mode requires AUTORESEARCH_API_BASE_URL and AUTORESEARCH_API_KEY."
        )

    import time as _time
    url = SIMPLE_BASE_URL.rstrip("/") + "/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {SIMPLE_API_KEY}",
    }
    payload = {
        "model": SIMPLE_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    for attempt in range(retries):
        try:
            with httpx.Client(timeout=120, trust_env=False) as client:
                resp = client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            elif resp.status_code >= 500 and attempt < retries - 1:
                _time.sleep(5)
                continue
            else:
                print(f"  [Simple/{SIMPLE_MODEL}] HTTP {resp.status_code}: {resp.text[:200]}")
                return None
        except Exception as e:
            if attempt < retries - 1:
                _time.sleep(5)
                continue
            print(f"  [Simple/{SIMPLE_MODEL}] 失败(重试{retries}次): {e}")
            return None


def _is_free_channel_window():
    """北京时间（UTC+8）00:00–08:00 为灵活Claude免费时段"""
    import datetime
    bj_hour = (datetime.datetime.utcnow().hour + 8) % 24
    return 0 <= bj_hour < 8


# ============================================================
# Gemini 系列（OpenAI 兼容格式，需代理）
# ============================================================
def call_gemini(prompt, preset_name="gemini-3.1-flash-lite", temperature=0.3, max_tokens=2000, retries=3):
    cfg = get_preset(preset_name)
    if not cfg:
        return None

    import time as _time
    url = _cfg_value(cfg, "base_url", default="").rstrip("/") + "/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {_require_cfg_value(cfg, 'api_key', preset_name)}",
    }
    payload = {
        "model": cfg["model"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    # Gemini 在受限网络下必须走代理；config 字段 needs_proxy 默认 False，
    # 但实测官方 generativelanguage.googleapis.com 直连不通 → 这里强制按 True 处理
    needs_proxy = cfg.get("needs_proxy", False) or "googleapis.com" in _cfg_value(cfg, "base_url", default="")

    for attempt in range(retries):
        kwargs = _httpx_kwargs(needs_proxy=needs_proxy, timeout=120)
        if kwargs is None:
            print(f"  [Gemini/{preset_name}] 代理不可用，跳过")
            return None
        try:
            with httpx.Client(**kwargs) as client:
                resp = client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"].get("content")
                if content is None:
                    print(f"  [Gemini] 无输出内容（max_tokens 过小或全用于 thinking）")
                    return None
                return content
            elif resp.status_code >= 500 and attempt < retries - 1:
                _time.sleep(5)
                continue
            else:
                print(f"  [Gemini] HTTP {resp.status_code}: {resp.text[:100]}")
                return None
        except Exception as e:
            if attempt < retries - 1:
                _time.sleep(5)
                continue
            print(f"  [Gemini] 失败(重试{retries}次): {e}")
            return None


# ============================================================
# 免费渠道 Claude（免费窗口，通过 Claude Code CLI 调用）
# 直接 API 调有 bug，但 CLI 加 --betas context-1m-2025-08-07 可以正常工作。
# ============================================================
def call_free_channel_claude(prompt, model="claude-opus-4-7", temperature=0.3, max_tokens=2000):
    """通过 Claude Code CLI 调用免费渠道（1M context）。
    北京时间 00:00-08:00 免费；逐 key 轮换；--no-session-persistence 保证无状态。
    部分部署环境需要代理才能连通该免费渠道。
    成功返回字符串；全部失败/无代理 返回 None。"""
    import subprocess, os

    if not proxy_alive():
        print(f"  [灵活Claude] 代理 {PROXY_URL} 不可用，跳过 → 上层会回落到付费渠道")
        return None

    lh_cfg = get_preset("free-channel-claude")
    if not lh_cfg:
        return None

    keys = _cfg_list(lh_cfg, "auth_keys")
    base_url = _require_cfg_value(lh_cfg, "base_url", "free-channel-claude")

    for i, key in enumerate(keys):
        print(f"  [灵活Claude/{model}] 尝试 key {i+1}/{len(keys)}...")
        env = os.environ.copy()
        env["ANTHROPIC_AUTH_TOKEN"] = key
        env["ANTHROPIC_BASE_URL"] = base_url
        # 显式把代理传给 claude CLI（它内部用 Node fetch，会读 HTTPS_PROXY）
        env["HTTPS_PROXY"] = PROXY_URL
        env["HTTP_PROXY"] = PROXY_URL
        env["https_proxy"] = PROXY_URL
        env["http_proxy"] = PROXY_URL

        cmd = [
            "claude", "-p", prompt,
            "--model", model,
            "--betas", "context-1m-2025-08-07",
            "--no-session-persistence",
            "--dangerously-skip-permissions",
        ]
        try:
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=lh_cfg.get("timeout", 3600),
                stdin=subprocess.DEVNULL,
            )
            if result.returncode == 0:
                out = result.stdout.strip()
                if out:
                    return out
                print(f"  [灵活Claude] key {i+1} 返回为空，尝试下一个")
            else:
                err = (result.stderr or result.stdout or "").strip()
                print(f"  [灵活Claude] key {i+1} 失败(exit {result.returncode}): {err[:150]}")
        except subprocess.TimeoutExpired:
            print(f"  [灵活Claude] key {i+1} 超时")
        except Exception as e:
            print(f"  [灵活Claude] key {i+1} 异常: {type(e).__name__}: {e}")

    print(f"  [灵活Claude/{model}] 所有 key 均失败")
    return None


# ============================================================
# Claude 系列（主入口：免费窗口优先灵活Claude CLI，否则走付费渠道）
# ============================================================
def call_claude(prompt, preset_name="claude-sonnet-4-6", temperature=0.3, max_tokens=2000, retries=3):
    resolved = _resolve_claude_preset(preset_name)
    cfg = get_preset(resolved)
    if not cfg:
        print(f"  [Claude] 未找到 preset: {resolved}")
        return None

    # 免费窗口：优先灵活Claude CLI
    if _is_free_channel_window():
        result = call_free_channel_claude(
            prompt, model=cfg["model"],
            temperature=temperature, max_tokens=max_tokens,
        )
        if result is not None:
            return result
        print(f"  [Claude] 灵活Claude 全部失败，回落收费版本 ({resolved})")

    # 收费版本（Anthropic Messages API 或兼容网关）
    if cfg.get("provider") not in ("anthropic_gateway", "anthropic_messages"):
        print(f"  [Claude] preset {resolved} 不是 Anthropic Messages 兼容配置，请更新本地配置")
        return None

    import time as _time
    url = _cfg_value(cfg, "base_url", default="").rstrip("/") + "/v1/messages"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {_require_cfg_value(cfg, 'auth_token', resolved)}",
        "anthropic-version": "2023-06-01",
        "User-Agent": "curl/7.88.1",
    }
    payload = {
        "model": cfg["model"],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }

    for attempt in range(retries):
        try:
            kwargs = _httpx_kwargs(needs_proxy=cfg.get("needs_proxy", False), timeout=180)
            if kwargs is None:
                print(f"  [Claude/{cfg['model']}] 代理需要但不可用，跳过")
                return None
            with httpx.Client(**kwargs) as client:
                resp = client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                for block in data.get("content", []):
                    if block.get("type") == "text":
                        return block.get("text", "")
                return None
            elif resp.status_code >= 500 and attempt < retries - 1:
                _time.sleep(5)
                continue
            else:
                print(f"  [Claude/{cfg['model']}] HTTP {resp.status_code}: {resp.text[:200]}")
                if attempt < retries - 1:
                    _time.sleep(5)
                    continue
                return None
        except Exception as e:
            if attempt < retries - 1:
                _time.sleep(5)
                continue
            print(f"  [Claude/{cfg['model']}] 失败(重试{retries}次): {e}")
            return None


# ============================================================
# 免费渠道 GPT（免费窗口，OpenAI Responses API）
# ============================================================
def _extract_responses_text(data):
    """从 Responses API 返回体里提取最终的 output_text"""
    for item in data.get("output", []):
        if isinstance(item, dict) and item.get("type") == "message":
            for c in item.get("content", []):
                if isinstance(c, dict) and c.get("type") == "output_text":
                    return c.get("text", "")
    return ""


def call_free_channel_gpt(prompt, preset_name="free-channel-gpt", max_output_tokens=None):
    """北京时间00:00-08:00免费；多 key 轮换；走 OpenAI Responses API。
    免费渠道供应商可能对直连 SSL 有限制，必须经代理；代理不可用时返回 None 让上层回落收费。"""
    cfg = get_preset(preset_name)
    if not cfg or cfg.get("provider") != "openai_responses":
        return None

    if not proxy_alive():
        print(f"  [灵活GPT] 代理不可用（SSH 隧道断了？），跳过 → 上层会回落到收费中转站")
        return None

    keys = _cfg_list(cfg, "auth_keys")
    if not keys:
        return None
    timeout = cfg.get("timeout", 600)
    url = _cfg_value(cfg, "base_url", default="").rstrip("/") + cfg.get("endpoint", "/v1/responses")
    model = cfg["model"]

    payload = {"model": model, "input": prompt, "stream": True}
    if max_output_tokens is not None:
        payload["max_output_tokens"] = max_output_tokens

    for i, key in enumerate(keys):
        print(f"  [灵活GPT/{model}] 尝试 key {i+1}/{len(keys)}...")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "Accept": "text/event-stream",
        }
        try:
            kwargs = _httpx_kwargs(needs_proxy=True, timeout=timeout)
            if kwargs is None:
                return None
            chunks = []
            final_text = ""
            with httpx.Client(**kwargs) as client:
                with client.stream("POST", url, headers=headers, json=payload) as resp:
                    if resp.status_code != 200:
                        body = resp.read().decode("utf-8", "ignore")[:200]
                        print(f"  [灵活GPT] key {i+1} HTTP {resp.status_code}: {body}")
                        continue
                    for line in resp.iter_lines():
                        if not line:
                            continue
                        # httpx 的 iter_lines 已经按行切，但部分实现仍可能给 bytes
                        if isinstance(line, bytes):
                            line = line.decode("utf-8", "ignore")
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            evt = json.loads(data)
                        except Exception:
                            continue
                        etype = evt.get("type", "")
                        # Responses API 流式增量
                        if etype == "response.output_text.delta":
                            chunks.append(evt.get("delta", ""))
                        # 兼容部分网关使用的 OpenAI Chat 风格 delta
                        elif "choices" in evt:
                            for ch in evt.get("choices", []):
                                d = ch.get("delta", {}) or {}
                                if d.get("content"):
                                    chunks.append(d["content"])
                        # 流结束聚合事件，作为兜底
                        elif etype in ("response.completed", "response.done"):
                            final_text = _extract_responses_text(evt.get("response", {})) or final_text
            text = "".join(chunks).strip() or final_text.strip()
            if text:
                return text
            print(f"  [灵活GPT] key {i+1} 流结束但未收集到文本，尝试下一个")
        except Exception as e:
            print(f"  [灵活GPT] key {i+1} 失败: {type(e).__name__}: {e}")

    print(f"  [灵活GPT/{model}] 所有 key 均失败")
    return None


# ============================================================
# GPT-5.5（主入口：免费窗口优先灵活，否则走收费中转站）
# ============================================================
def call_gpt(prompt, temperature=0.3, max_tokens=2000, retries=2, force_paid=False):
    """始终优先免费渠道（实测全天可用，免费窗口外也能跑通），失败回落收费中转站。
    force_paid=True 可强制走收费版本（用于排除灵活渠道质量问题时）。"""
    # 1) 始终优先灵活（24h 可用，省钱）
    if not force_paid:
        result = call_free_channel_gpt(prompt, "free-channel-gpt", max_output_tokens=max_tokens)
        if result:
            return result
        print(f"  [GPT] 灵活GPT 全部失败，回落收费中转站")

    # 2) 收费中转站（OpenAI Chat Completions 格式）
    cfg = get_preset("gpt-5.5")
    if not cfg:
        return None

    url = _cfg_value(cfg, "base_url", default="").rstrip("/") + "/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {_require_cfg_value(cfg, 'api_key', 'gpt-5.5')}",
    }
    payload = {
        "model": cfg["model"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    import time
    for attempt in range(retries + 1):
        try:
            kwargs = _httpx_kwargs(needs_proxy=cfg.get("needs_proxy", False), timeout=120)
            if kwargs is None:
                print(f"  [GPT/收费] 代理需要但不可用，放弃")
                return None
            with httpx.Client(**kwargs) as client:
                resp = client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            else:
                if attempt < retries:
                    time.sleep(5)
                    continue
                print(f"  [GPT/收费] HTTP {resp.status_code}: {resp.text[:100]}")
                return None
        except Exception as e:
            if attempt < retries:
                time.sleep(5)
                continue
            print(f"  [GPT/收费] 失败: {e}")
            return None


# ============================================================
# 便捷接口（按任务复杂度选模型）
# ============================================================
def call_flash(prompt, **kwargs):
    """简单任务：简易模式下直接走统一端点；否则优先 Gemini Flash Lite，失败时回落 GPT-5.5。"""
    if simple_mode_enabled():
        return call_simple(prompt, **kwargs)
    result = call_gemini(prompt, "gemini-3.1-flash-lite", **kwargs)
    if result:
        return result
    print("  [Flash] Gemini 不可用，回落 GPT-5.5")
    return call_gpt(prompt, **kwargs)


def call_pro(prompt, **kwargs):
    """综合研判：简易模式下直接走统一端点；否则优先 Gemini 3.1 Pro，失败时回落 GPT-5.5。"""
    kwargs.setdefault("temperature", 0.2)
    kwargs.setdefault("max_tokens", 3000)
    if simple_mode_enabled():
        return call_simple(prompt, **kwargs)
    result = call_gemini(prompt, "gemini-3.1-pro", **kwargs)
    if result:
        return result
    print("  [Pro] Gemini 不可用，回落 GPT-5.5")
    return call_gpt(prompt, **kwargs)


def call_model(model_name, prompt, **kwargs):
    """通用入口，按名称调用。

    简易模式（AUTORESEARCH_API_BASE_URL + AUTORESEARCH_API_KEY 均已设置）优先：
    所有模型名统一路由到同一个 OpenAI 兼容端点，方便只有一个 API 的用户直接跑通全流程。
    """
    if simple_mode_enabled():
        return call_simple(prompt, **kwargs)
    if model_name == "gemini-pro":
        return call_pro(prompt, **kwargs)
    elif model_name == "gemini-flash":
        return call_flash(prompt, **kwargs)
    elif model_name == "claude-opus":
        # call_claude 内部负责免费窗口判断，并在失败时回落付费渠道。
        return call_claude(prompt, "claude-opus", **kwargs)
    elif model_name == "claude-sonnet":
        return call_claude(prompt, "claude-sonnet", **kwargs)
    elif model_name == "claude-haiku":
        return call_claude(prompt, "claude-haiku", **kwargs)
    elif model_name == "gpt-5.5":
        return call_gpt(prompt, **kwargs)
    else:
        print(f"  未知模型: {model_name}")
        return None


if __name__ == "__main__":
    import datetime
    bj_hour = (datetime.datetime.utcnow().hour + 8) % 24
    free = _is_free_channel_window()
    print(f"测试所有模型连通性... (北京时间 {bj_hour:02d}:xx，免费窗口: {free})")
    print(f"  Gemini Flash:        {call_flash('1+1=?', max_tokens=20)}")
    print(f"  GPT-5.5(自动路由):   {call_gpt('1+1=?', max_tokens=30)}")
    print(f"  GPT-5.5(强制收费):   {call_gpt('1+1=?', max_tokens=30, force_paid=True)}")
    if free:
        print(f"  GPT-5.5(灵活直调):   {call_free_channel_gpt('1+1=?', max_output_tokens=30)}")
    print(f"  Claude Sonnet:       {call_claude('1+1=?', 'claude-sonnet-4-6', max_tokens=20)}")
    print(f"  Claude Opus:         {call_claude('1+1=?', 'claude-opus-4-7', max_tokens=20)}")

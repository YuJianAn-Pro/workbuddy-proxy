#!/usr/bin/env python3
"""
WorkBuddy AI 国际版反向代理服务
将 OpenAI 兼容格式的请求转发到 WorkBuddy AI 国际版云端 API

参考: @magpie-community/opencode-workbuddy-auth (npm)
关键: 第一条消息必须是 system prompt; conversation id 通过 header 传递; 仅支持流式

用法:
    python workbuddy_proxy.py --port 8080
    python workbuddy_proxy.py --port 8080 --jwt <JWT token> --user-id <用户UID>

环境变量:
    WB_PROXY_PORT      - 监听端口（默认 8080）
    WB_JWT_TOKEN       - JWT token（默认从 token_live.txt 读取）
    WB_USER_ID         - 用户 UID
    WB_SYSTEM_PROMPT   - 默认 system prompt
"""

import json
import os
import sys
import time
import uuid
import argparse
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler

# ============ 配置 ============
CONFIG = {
    "port": int(os.environ.get("WB_PROXY_PORT", "8080")),
    "cloud_url": os.environ.get("WB_CLOUD_URL", "https://www.workbuddy.ai/v2/chat/completions"),
    "jwt_token": os.environ.get("WB_JWT_TOKEN", ""),
    "user_id": os.environ.get("WB_USER_ID", "256b7a9e-5c20-4a31-a94f-71f7f04380db"),
    "system_prompt": os.environ.get("WB_SYSTEM_PROMPT", "You are a helpful, harmless, and honest assistant."),
    "ide_version": "5.8.4",
}

# 从文件加载 JWT token（支持 EXE 模式：从 EXE 所在目录查找）
if not CONFIG["jwt_token"]:
    # 确定配置文件目录：EXE 模式下用 EXE 所在目录，否则用脚本所在目录
    if getattr(sys, 'frozen', False):
        config_dir = os.path.dirname(sys.executable)
    else:
        config_dir = os.path.dirname(os.path.abspath(__file__))

    token_file = os.path.join(config_dir, "token_live.txt")
    if os.path.exists(token_file):
        with open(token_file, "r") as f:
            CONFIG["jwt_token"] = f.read().strip()

# 国际版完整模型列表（从用户截图 + /v3/config）
ALL_MODELS = [
    "auto",
    "hy4-preview", "hy3",
    "step-5-preview",
    "deepseek-v4.1-flash",
    "gpt-6-sol", "gpt-6-luna",
    "gpt-5.6-terra", "gpt-5.6-luna",
    "gpt-5.5", "gpt-5.4", "gpt-5.3-codex",
    "gemini-3.1-pro", "gemini-3.5-flash",
    "glm-5.3", "glm-5.2",
    "kimi-k3", "kimi-k2.6",
    "minimax-m3",
]

# 模型名映射（OpenAI 常见名 -> WorkBuddy 名）
MODEL_MAP = {
    "gpt-4o": "gpt-5.6-luna",
    "gpt-4": "gpt-5.6-luna",
    "gpt-3.5-turbo": "gpt-5.6-luna",
    "claude-3-5-sonnet": "gpt-5.6-luna",
    "claude-opus-4": "gpt-6-sol",
}


def build_headers(conv_id=None):
    """构建 WorkBuddy 国际版请求头"""
    cid = conv_id or str(uuid.uuid4())
    return {
        "Authorization": f"Bearer {CONFIG['jwt_token']}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "User-Agent": f"WorkBuddy/{CONFIG['ide_version']}",
        "X-User-Id": CONFIG["user_id"],
        "X-Domain": "workbuddy.ai",
        "X-Product": "SaaS",
        "X-IDE-Type": "WorkBuddy",
        "X-Agent-Purpose": "conversation",
        "X-IDE-Name": "WorkBuddy",
        "X-IDE-Version": CONFIG["ide_version"],
        "X-Agent-Intent": "craft",
        "X-Requested-With": "XMLHttpRequest",
        "X-Agent-Type": "main",
        "X-Conversation-ID": cid,
        "X-Conversation-Request-ID": str(uuid.uuid4()),
        "X-Conversation-Message-ID": str(uuid.uuid4()),
        "X-Request-ID": str(uuid.uuid4()),
        "Origin": "https://www.workbuddy.ai",
        "Referer": "https://www.workbuddy.ai/",
    }


def normalize_messages(messages):
    """确保第一条消息是 system prompt"""
    if not messages:
        return [{"role": "system", "content": CONFIG["system_prompt"]}]
    if messages[0].get("role") != "system":
        messages = [{"role": "system", "content": CONFIG["system_prompt"]}] + messages
    return messages


def normalize_model(model):
    """规范化模型名"""
    if not model:
        return "gpt-5.6-luna"
    model_lower = model.lower()
    return MODEL_MAP.get(model_lower, model_lower)


class ProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"[{time.strftime('%H:%M:%S')}] {args[0]}")

    def _send_json(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_sse_headers(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

    def do_GET(self):
        if self.path == "/v1/models":
            self._send_json(200, {
                "object": "list",
                "data": [
                    {"id": m, "object": "model", "created": 0, "owned_by": "workbuddy"}
                    for m in ALL_MODELS
                ]
            })
        elif self.path == "/health":
            self._send_json(200, {
                "status": "ok",
                "upstream": CONFIG["cloud_url"],
                "jwt": "configured" if CONFIG["jwt_token"] else "missing",
                "user_id": CONFIG["user_id"],
            })
        else:
            self._send_json(404, {"error": {"message": "Not found"}})

    def _convert_responses_to_chat(self, request_data):
        """将 OpenAI Responses API 请求转换为 Chat Completions 格式"""
        model = normalize_model(request_data.get("model", "gpt-5.6-luna"))
        raw_input = request_data.get("input", "")
        instructions = request_data.get("instructions", "")

        # 提取消息内容（处理字符串、数组、content 数组等多种格式）
        def extract_content(content):
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts = []
                for c in content:
                    if not isinstance(c, dict):
                        continue
                    ctype = c.get("type", "")
                    if ctype in ("input_text", "output_text", "text"):
                        parts.append(c.get("text", ""))
                    elif ctype == "refusal":
                        parts.append(c.get("refusal", ""))
                return "".join(parts)
            return str(content) if content else ""

        # input 可以是字符串或消息数组
        if isinstance(raw_input, str):
            messages = [{"role": "user", "content": raw_input}]
        elif isinstance(raw_input, list):
            messages = []
            for item in raw_input:
                if not isinstance(item, dict):
                    continue
                role = item.get("role", "user")
                content = extract_content(item.get("content", ""))

                # 处理 assistant 消息中的 tool_calls
                tool_calls = item.get("tool_calls", [])
                msg = {"role": role, "content": content}
                if tool_calls and role == "assistant":
                    msg["tool_calls"] = tool_calls

                # 处理 tool 消息的 tool_call_id
                if role == "tool":
                    msg["tool_call_id"] = item.get("tool_call_id", "")

                # 跳过空内容的 tool 消息（WorkBuddy 可能不喜欢）
                if role == "tool" and not content:
                    continue

                messages.append(msg)
        else:
            messages = [{"role": "user", "content": str(raw_input)}]

        # 处理 system prompt：优先用 instructions，否则用默认
        has_system = any(m.get("role") == "system" for m in messages)
        if instructions:
            system_msg = {"role": "system", "content": instructions}
            if has_system:
                # 替换已有的 system 消息
                messages = [system_msg] + [m for m in messages if m.get("role") != "system"]
            else:
                messages = [system_msg] + messages
        elif not has_system:
            messages = [{"role": "system", "content": CONFIG["system_prompt"]}] + messages

        chat_req = {
            "model": model,
            "messages": messages,
            "stream": True,  # WorkBuddy 仅支持流式
        }

        # 传递可选参数
        if "max_output_tokens" in request_data:
            chat_req["max_tokens"] = request_data["max_output_tokens"]
        if "temperature" in request_data:
            chat_req["temperature"] = request_data["temperature"]
        if "top_p" in request_data:
            chat_req["top_p"] = request_data["top_p"]

        # 转换 tools 格式：Responses API 扁平 -> Chat Completions 嵌套
        if "tools" in request_data:
            converted_tools = []
            for tool in request_data["tools"]:
                if tool.get("type") == "function" and "function" not in tool:
                    # Responses API 格式：{"type":"function","name":"...","description":"...","parameters":{...}}
                    converted_tools.append({
                        "type": "function",
                        "function": {
                            "name": tool.get("name", ""),
                            "description": tool.get("description", ""),
                            "parameters": tool.get("parameters", {}),
                        }
                    })
                else:
                    # 已经是 Chat Completions 格式或其他类型，直接保留
                    converted_tools.append(tool)
            chat_req["tools"] = converted_tools

        # 转换 tool_choice 格式
        if "tool_choice" in request_data:
            tc = request_data["tool_choice"]
            if isinstance(tc, dict) and tc.get("type") == "function" and "function" not in tc:
                chat_req["tool_choice"] = {
                    "type": "function",
                    "function": {"name": tc.get("name", "")}
                }
            else:
                chat_req["tool_choice"] = tc

        return chat_req

    def _stream_sse_to_responses(self, upstream_resp, resp_id, model):
        """将上游 Chat Completions SSE 转换为 Responses API SSE 格式并发送
        先收集完整文本，再以 SSE 事件格式发送（可靠，不会超时）"""
        full_text = self._collect_sse_to_text(upstream_resp)
        msg_id = f"msg_{uuid.uuid4().hex[:24]}"
        now = int(time.time())

        self._send_sse_headers()

        events = [
            {
                "type": "response.created",
                "response": {
                    "id": resp_id,
                    "object": "response",
                    "created": now,
                    "model": model,
                    "status": "in_progress",
                    "output": [],
                    "usage": None,
                }
            },
            {
                "type": "response.output_text.started",
                "item_id": msg_id,
                "output_index": 0,
                "content_index": 0,
            },
            {
                "type": "response.output_text.delta",
                "item_id": msg_id,
                "output_index": 0,
                "content_index": 0,
                "delta": full_text,
            },
            {
                "type": "response.output_text.done",
                "item_id": msg_id,
                "output_index": 0,
                "content_index": 0,
                "text": full_text,
            },
            {
                "type": "response.completed",
                "response": {
                    "id": resp_id,
                    "object": "response",
                    "created": now,
                    "model": model,
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "id": msg_id,
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": full_text}],
                        }
                    ],
                    "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                }
            },
        ]

        for evt in events:
            self.wfile.write(f"data: {json.dumps(evt, ensure_ascii=False)}\n\n".encode("utf-8"))
            self.wfile.flush()

        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def _collect_sse_to_text(self, upstream_resp):
        """收集上游 SSE 响应，提取完整文本（逐行读取，检测到 [DONE] 即停止）"""
        full_text = ""
        buffer = ""
        done = False

        while not done:
            chunk = upstream_resp.read(4096)
            if not chunk:
                break
            buffer += chunk.decode("utf-8", errors="replace")

            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    done = True
                    break
                try:
                    data = json.loads(data_str)
                    if data.get("choices"):
                        delta = data["choices"][0].get("delta", {})
                        full_text += delta.get("content", "")
                except:
                    pass

        return full_text

    def do_POST(self):
        is_responses = self.path in ["/v1/responses", "/responses"]
        is_chat = self.path in ["/v1/chat/completions", "/chat/completions"]

        if not is_responses and not is_chat:
            self._send_json(404, {"error": {"message": "Not found"}})
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else b"{}"

        # 记录收到的请求（调试用）
        try:
            import time as _t
            _ts = _t.strftime('%H%M%S')
            with open(rf"C:\Users\Administrator\_wb\req_body_{_ts}.json", "wb") as _f:
                _f.write(body)
            with open(r"C:\Users\Administrator\_wb\request_log.txt", "a", encoding="utf-8") as _f:
                _f.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
                _f.write(f"Path: {self.path}\n")
                _f.write(f"Body size: {len(body)} bytes, saved to req_body_{_ts}.json\n")
                # 解析结构
                try:
                    _rd = json.loads(body)
                    _f.write(f"Top-level keys: {list(_rd.keys())}\n")
                    _f.write(f"Model: {_rd.get('model')}\n")
                    _f.write(f"Stream: {_rd.get('stream')}\n")
                    _inp = _rd.get('input', '')
                    if isinstance(_inp, list):
                        _f.write(f"Input messages count: {len(_inp)}\n")
                        for _i, _m in enumerate(_inp):
                            _role = _m.get('role', '?')
                            _content = _m.get('content', '')
                            _clen = len(_content) if isinstance(_content, str) else len(json.dumps(_content, ensure_ascii=False))
                            _f.write(f"  [{_i}] role={_role}, content_len={_clen}\n")
                    if 'tools' in _rd:
                        _f.write(f"Tools count: {len(_rd['tools'])}\n")
                        for _tl in _rd['tools'][:5]:
                            _f.write(f"  - {_tl.get('name', _tl.get('function', {}).get('name', '?'))}\n")
                    if 'instructions' in _rd:
                        _f.write(f"Instructions length: {len(_rd['instructions'])}\n")
                except Exception as _e:
                    _f.write(f"Parse error: {_e}\n")
        except:
            pass

        try:
            request_data = json.loads(body)
        except json.JSONDecodeError:
            self._send_json(400, {"error": {"message": "Invalid JSON"}})
            return

        # 转换请求格式
        if is_responses:
            chat_req = self._convert_responses_to_chat(request_data)
            stream = request_data.get("stream", False)
        else:
            chat_req = {
                "model": normalize_model(request_data.get("model", "gpt-5.6-luna")),
                "messages": normalize_messages(request_data.get("messages", [])),
                "stream": True,
            }
            stream = request_data.get("stream", False)
            if "max_completion_tokens" in request_data and "max_tokens" not in chat_req:
                chat_req["max_tokens"] = request_data["max_completion_tokens"]

        model = chat_req["model"]
        body_bytes = json.dumps(chat_req, ensure_ascii=False).encode("utf-8")
        headers = build_headers()
        req = urllib.request.Request(CONFIG["cloud_url"], data=body_bytes, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                if is_responses and stream:
                    # Responses API 流式
                    resp_id = f"resp_{uuid.uuid4().hex[:24]}"
                    self._stream_sse_to_responses(resp, resp_id, model)
                elif is_responses and not stream:
                    # Responses API 非流式
                    full_text = self._collect_sse_to_text(resp)
                    resp_id = f"resp_{uuid.uuid4().hex[:24]}"
                    msg_id = f"msg_{uuid.uuid4().hex[:24]}"
                    self._send_json(200, {
                        "id": resp_id,
                        "object": "response",
                        "created": int(time.time()),
                        "model": model,
                        "output": [
                            {
                                "type": "message",
                                "id": msg_id,
                                "role": "assistant",
                                "content": [{"type": "output_text", "text": full_text}],
                            }
                        ],
                        "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                    })
                elif stream:
                    # Chat Completions 流式：透传，检测到 [DONE] 后停止
                    self._send_sse_headers()
                    buffer = ""
                    done = False
                    while not done:
                        chunk = resp.read(4096)
                        if not chunk:
                            break
                        buffer += chunk.decode("utf-8", errors="replace")
                        # 直接转发原始字节
                        self.wfile.write(chunk)
                        self.wfile.flush()
                        # 检测 [DONE]
                        if "data: [DONE]" in buffer:
                            done = True
                else:
                    # Chat Completions 非流式
                    full_text = self._collect_sse_to_text(resp)
                    self._send_json(200, {
                        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
                        "object": "chat.completion",
                        "created": int(time.time()),
                        "model": model,
                        "choices": [{
                            "index": 0,
                            "message": {"role": "assistant", "content": full_text},
                            "finish_reason": "stop"
                        }],
                        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                    })
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            try:
                err_json = json.loads(error_body)
                msg = err_json.get("msg", error_body[:200])
            except:
                msg = error_body[:200]
            # 记录上游错误
            try:
                with open(r"C:\Users\Administrator\_wb\request_log.txt", "a", encoding="utf-8") as _f:
                    _f.write(f"UPSTREAM ERROR {e.code}: {error_body[:500]}\n")
            except:
                pass
            self._send_json(e.code, {"error": {"message": f"WorkBuddy API error ({e.code}): {msg}"}})
        except Exception as e:
            self._send_json(502, {"error": {"message": f"Proxy error: {str(e)}"}})


def main():
    parser = argparse.ArgumentParser(description="WorkBuddy AI 国际版反向代理")
    parser.add_argument("--port", type=int, default=CONFIG["port"])
    parser.add_argument("--jwt", default=CONFIG["jwt_token"])
    parser.add_argument("--user-id", default=CONFIG["user_id"])
    parser.add_argument("--system-prompt", default=CONFIG["system_prompt"])
    args = parser.parse_args()

    CONFIG["port"] = args.port
    if args.jwt:
        CONFIG["jwt_token"] = args.jwt
    if args.user_id:
        CONFIG["user_id"] = args.user_id
    if args.system_prompt:
        CONFIG["system_prompt"] = args.system_prompt

    if not CONFIG["jwt_token"]:
        print("[错误] 未配置 JWT token。请用 --jwt 参数或设置 WB_JWT_TOKEN 环境变量，或在同目录放置 token_live.txt")
        sys.exit(1)

    server = HTTPServer(("0.0.0.0", CONFIG["port"]), ProxyHandler)
    print("=" * 60)
    print("WorkBuddy AI 国际版反向代理已启动")
    print(f"监听: http://0.0.0.0:{CONFIG['port']}")
    print(f"OpenAI 兼容端点: http://127.0.0.1:{CONFIG['port']}/v1/chat/completions")
    print(f"模型列表: http://127.0.0.1:{CONFIG['port']}/v1/models")
    print(f"健康检查: http://127.0.0.1:{CONFIG['port']}/health")
    print(f"上游 API: {CONFIG['cloud_url']}")
    print(f"JWT: 已配置 ({len(CONFIG['jwt_token'])} chars)")
    print(f"用户 UID: {CONFIG['user_id']}")
    print("=" * 60)
    print("在其他 Agent 中配置:")
    print(f"  Base URL: http://127.0.0.1:{CONFIG['port']}/v1")
    print(f"  API Key: 任意值（如 sk-xxx）")
    print(f"  可用模型: {', '.join(ALL_MODELS[:8])} ...")
    print("=" * 60)
    print("测试命令:")
    print(f'  curl http://127.0.0.1:{CONFIG["port"]}/v1/chat/completions \\')
    print(f'    -H "Content-Type: application/json" \\')
    print(f'    -d \'{{"model":"gpt-5.6-luna","messages":[{{"role":"user","content":"你好"}}],"stream":true}}\'')
    print("=" * 60)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
        server.shutdown()


if __name__ == "__main__":
    main()

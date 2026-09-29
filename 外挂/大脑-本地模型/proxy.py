#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Responses ⇄ Chat Completions 转换代理（只依赖标准库）

她（Coopanion 的核心）说话走的是 **OpenAI Responses 协议**：
    POST <baseUrl>/responses    请求体是 Responses 格式（instructions / input items / tools）
    响应是 Responses 的 SSE 流（response.created → output_item.added → … → response.completed）

而本地推理服务和绝大多数本地/国内服务只有 **Chat Completions**：
    POST <baseUrl>/chat/completions

这个代理就干一件事：把两边的格式互转，让她的 provider 只要把 baseUrl 指到这里就能用本地模型。

用法：
    python3 proxy.py --端口 8899 --上游 http://127.0.0.1:1337/v1 --模型 deepseek-r1-distill-qwen-7b
    # 然后把她 provider 配置里的 baseUrl 改成 http://127.0.0.1:8899/v1

已验证的约束（照 build/cortico/src/protocol/open-responses 抄的，改了会挂）：
    · 事件类型必须在白名单里；
    · sequence_number 必须严格递增；
    · 每个 output item 先 added 后 done，id 要一致；
    · 终止事件 response.completed 里的 output 数组必须与 announced 的 item 一一对应。
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

序号 = {"n": 0}


def 下一号() -> int:
    序号["n"] += 1
    return 序号["n"]


def sse(事件: dict) -> bytes:
    return f"event: {事件['type']}\ndata: {json.dumps(事件, ensure_ascii=False)}\n\n".encode()


def 取文本(内容) -> str:
    """Responses 的 content 可能是字符串，也可能是 [{type:'input_text'|'output_text', text}]。"""
    if isinstance(内容, str):
        return 内容
    if isinstance(内容, list):
        段 = []
        for c in 内容:
            if isinstance(c, dict):
                if c.get("text"):
                    段.append(str(c["text"]))
            elif isinstance(c, str):
                段.append(c)
        return "\n".join(段)
    return "" if 内容 is None else str(内容)


def 转成聊天请求(体: dict) -> dict:
    消息 = []
    if 体.get("instructions"):
        消息.append({"role": "system", "content": 取文本(体["instructions"])})

    for 项 in 体.get("input") or []:
        if not isinstance(项, dict):
            continue
        类 = 项.get("type")
        if 类 == "message" or 项.get("role"):
            角色 = 项.get("role") or "user"
            if 角色 in ("developer", "system"):
                角色 = "system"
            消息.append({"role": 角色, "content": 取文本(项.get("content"))})
        elif 类 == "function_call":
            消息.append({"role": "assistant", "content": None, "tool_calls": [{
                "id": 项.get("call_id") or 项.get("id") or "call_0",
                "type": "function",
                "function": {"name": 项.get("name", ""), "arguments": 项.get("arguments") or "{}"},
            }]})
        elif 类 == "function_call_output":
            出 = 项.get("output")
            消息.append({"role": "tool", "tool_call_id": 项.get("call_id") or "call_0",
                         "content": 出 if isinstance(出, str) else json.dumps(出, ensure_ascii=False)})
        elif 类 == "reasoning":
            continue                      # 本地模型不需要回放推理

    请求 = {"model": 体.get("model") or "", "messages": 消息, "stream": False}
    if 体.get("tools"):
        请求["tools"] = [{"type": "function", "function": {
            "name": t.get("name", ""), "description": t.get("description", ""),
            "parameters": t.get("parameters") or {"type": "object", "properties": {}},
        }} for t in 体["tools"] if isinstance(t, dict)]
        if 体.get("tool_choice") in ("auto", "none", "required"):
            请求["tool_choice"] = 体["tool_choice"]
        elif isinstance(体.get("tool_choice"), dict):
            名 = 体["tool_choice"].get("name")
            请求["tool_choice"] = {"type": "function", "function": {"name": 名}} if 名 else "auto"
        if 体.get("parallel_tool_calls") is not None:
            请求["parallel_tool_calls"] = bool(体["parallel_tool_calls"])
    for k in ("temperature", "top_p", "max_output_tokens", "max_tokens"):
        if 体.get(k) is not None:
            请求["max_tokens" if k == "max_output_tokens" else k] = 体[k]
    return 请求


def 造响应壳(体: dict, 模型: str) -> dict:
    """照 createResponse() 的字段抄一份，providers/openai-responses-compat 会校验其中的字段。"""
    return {
        "id": "resp_local_" + str(int(time.time() * 1000)),
        "object": "response", "created_at": int(time.time()), "completed_at": None,
        "status": "in_progress", "incomplete_details": None, "model": 模型,
        "previous_response_id": 体.get("previous_response_id"),
        "instructions": 体.get("instructions"), "output": [], "error": None,
        "tools": 体.get("tools") or [], "tool_choice": 体.get("tool_choice") or "auto",
        "truncation": 体.get("truncation") or "disabled",
        "parallel_tool_calls": bool(体.get("parallel_tool_calls")),
        "text": 体.get("text") or {"format": {"type": "text"}},
        "top_p": 体.get("top_p") or 1, "presence_penalty": 体.get("presence_penalty") or 0,
        "frequency_penalty": 体.get("frequency_penalty") or 0, "top_logprobs": 0,
        "temperature": 体.get("temperature") or 1, "reasoning": None,
        "usage": None, "max_output_tokens": 体.get("max_output_tokens"),
        "max_tool_calls": 体.get("max_tool_calls"), "store": False, "background": False,
        "service_tier": "default", "metadata": 体.get("metadata"),
        "safety_identifier": None, "prompt_cache_key": None,
    }


def 造事件流(体: dict, 模型: str, 消息: dict, 用量: dict) -> list:
    """把 Chat Completions 的一条回复翻成 Responses 的整串事件。"""
    事件, 输出项 = [], []
    壳 = 造响应壳(体, 模型)
    事件.append(sse({"type": "response.created", "sequence_number": 下一号(), "response": 壳}))

    工具调用 = 消息.get("tool_calls") or []
    文本 = 取文本(消息.get("content")).strip()

    if 工具调用:
        for i, 调 in enumerate(工具调用):
            函数 = 调.get("function") or {}
            项id = f"fc_{int(time.time()*1000)}_{i}"
            调id = 调.get("id") or f"call_{i}"
            参 = 函数.get("arguments") or "{}"
            项 = {"id": 项id, "type": "function_call", "status": "in_progress",
                  "call_id": 调id, "name": 函数.get("name", ""), "arguments": ""}
            事件.append(sse({"type": "response.output_item.added", "sequence_number": 下一号(),
                             "output_index": i, "item": 项}))
            事件.append(sse({"type": "response.function_call_arguments.delta", "sequence_number": 下一号(),
                             "item_id": 项id, "output_index": i, "delta": 参}))
            事件.append(sse({"type": "response.function_call_arguments.done", "sequence_number": 下一号(),
                             "item_id": 项id, "output_index": i, "arguments": 参}))
            完 = {**项, "status": "completed", "arguments": 参}
            事件.append(sse({"type": "response.output_item.done", "sequence_number": 下一号(),
                             "output_index": i, "item": 完}))
            输出项.append(完)
    else:
        项id = f"msg_{int(time.time()*1000)}"
        项 = {"id": 项id, "type": "message", "status": "in_progress", "role": "assistant", "content": []}
        事件.append(sse({"type": "response.output_item.added", "sequence_number": 下一号(),
                         "output_index": 0, "item": 项}))
        事件.append(sse({"type": "response.content_part.added", "sequence_number": 下一号(),
                         "item_id": 项id, "output_index": 0, "content_index": 0,
                         "part": {"type": "output_text", "text": "", "annotations": []}}))
        if 文本:
            事件.append(sse({"type": "response.output_text.delta", "sequence_number": 下一号(),
                             "item_id": 项id, "output_index": 0, "content_index": 0, "delta": 文本}))
        事件.append(sse({"type": "response.output_text.done", "sequence_number": 下一号(),
                         "item_id": 项id, "output_index": 0, "content_index": 0, "text": 文本}))
        部 = {"type": "output_text", "text": 文本, "annotations": []}
        事件.append(sse({"type": "response.content_part.done", "sequence_number": 下一号(),
                         "item_id": 项id, "output_index": 0, "content_index": 0, "part": 部}))
        完 = {"id": 项id, "type": "message", "status": "completed", "role": "assistant", "content": [部]}
        事件.append(sse({"type": "response.output_item.done", "sequence_number": 下一号(),
                         "output_index": 0, "item": 完}))
        输出项.append(完)

    终 = {**壳, "status": "completed", "completed_at": int(time.time()), "output": 输出项,
          "usage": {"input_tokens": 用量.get("prompt_tokens", 0),
                    "output_tokens": 用量.get("completion_tokens", 0),
                    "total_tokens": 用量.get("total_tokens", 0),
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens_details": {"reasoning_tokens": 0}}}
    事件.append(sse({"type": "response.completed", "sequence_number": 下一号(), "response": 终}))
    return 事件


class 处理器(BaseHTTPRequestHandler):
    """HTTP handler that rewrites a Chat Completions request into the upstream API's format and streams the answer back.
    
    HTTP 处理器：把 Chat Completions 请求转成上游 API 的格式，再把回答以 SSE 流式转回来。
    """
    上游 = ""
    模型 = ""

    def log_message(self, 格式, *参数):          # 安静点，只在出错时说话
        pass

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            体 = json.dumps({"object": "list", "data": [{"id": self.模型, "object": "model"}]}).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(体)))
            self.end_headers()
            self.wfile.write(体)
            return
        self.send_error(404)

    def do_POST(self):
        if not self.path.rstrip("/").endswith("/responses"):
            self.send_error(404, "只认 /responses")
            return
        长度 = int(self.headers.get("content-length") or 0)
        原文 = self.rfile.read(长度).decode("utf-8", "ignore")
        try:
            体 = json.loads(原文)
        except Exception as exc:
            self.send_error(400, f"请求体不是 JSON: {exc}")
            return

        print(f"  [代理] 收到 /responses：{len(体.get('input') or [])} 条输入、"
              f"{len(体.get('tools') or [])} 个工具、stream={bool(体.get('stream'))}",
              file=sys.stderr, flush=True)
        聊天 = 转成聊天请求(体)
        聊天["model"] = 聊天.get("model") or self.模型
        if not 聊天["model"]:
            聊天["model"] = self.模型
        url = self.上游.rstrip("/") + "/chat/completions"
        请求 = urllib.request.Request(url, data=json.dumps(聊天, ensure_ascii=False).encode(),
                                     headers={"content-type": "application/json"})
        try:
            with urllib.request.urlopen(请求, timeout=180) as 应答:
                回 = json.loads(应答.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            明细 = exc.read().decode("utf-8", "ignore")[:400]
            print(f"  [代理] 上游 {exc.code}: {明细}", file=sys.stderr, flush=True)
            self.send_error(502, f"上游报错 {exc.code}")
            return
        except Exception as exc:
            print(f"  [代理] 连不上上游 {url}: {exc}", file=sys.stderr, flush=True)
            self.send_error(502, f"连不上上游: {exc}")
            return

        选择 = (回.get("choices") or [{}])[0]
        消息 = 选择.get("message") or {}
        用量 = 回.get("usage") or {}
        事件表 = 造事件流(体, 聊天["model"], 消息, 用量)

        # ⚠️ 关键：核心的传输层按「调用方给没给 onEvent」决定当流还是当 JSON：
        #    · 请求体里 stream=true  → 必须回 SSE（一帧一个事件，事件就是那个 JSON）
        #    · stream 假/没有       → 必须回一个完整的 Response JSON 对象
        #    （回错了会报 “Unexpected token 'e', "event: res"... is not valid JSON” —— 踩过）
        if 体.get("stream"):
            self.send_response(200)
            self.send_header("content-type", "text/event-stream; charset=utf-8")
            self.send_header("cache-control", "no-cache")
            self.end_headers()
            for 事件 in 事件表:
                self.wfile.write(事件)
            self.wfile.flush()
        else:
            终 = json.loads(事件表[-1].split(b"data: ", 1)[1].decode("utf-8"))
            数据 = json.dumps(终["response"], ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json; charset=utf-8")
            self.send_header("content-length", str(len(数据)))
            self.end_headers()
            self.wfile.write(数据)


def main():
    解 = argparse.ArgumentParser()
    解.add_argument("--端口", type=int, default=8899)
    解.add_argument("--上游", default="http://127.0.0.1:1337/v1")
    解.add_argument("--模型", default="deepseek-r1-distill-qwen-7b")
    参 = 解.parse_args()
    处理器.上游, 处理器.模型 = 参.上游, 参.模型
    服务 = ThreadingHTTPServer(("127.0.0.1", 参.端口), 处理器)
    print(f"  代理起来了：http://127.0.0.1:{参.端口}/v1  →  {参.上游}  (模型 {参.模型})")
    服务.serve_forever()


if __name__ == "__main__":
    main()

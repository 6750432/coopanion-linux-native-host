#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""假模型（零成本测试用）：不接任何真模型，按「台词.json」里写好的内容回一条。

用法：
    python3 mock.py --端口 8111 --台词 台词.json

台词.json 两种写法：
    {"工具": "pet_say", "参数": {"脚本": "【开心】你好呀！"}}      # 回一个工具调用
    {"文本": "你好呀！"}                                          # 回一段纯文本

每次请求都会把它收到的东西记到 mock 日志（stderr），方便核对代理转得对不对。
"""
import argparse
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

台词 = {"工具": "pet_say", "参数": {"脚本": "【开心】你好呀！"}}


def 载台词():
    global 台词
    路径 = Path(参.台词)
    if 路径.exists():
        try:
            台词 = json.loads(路径.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  台词文件读不了（用默认）: {exc}", file=sys.stderr)


class 处理器(BaseHTTPRequestHandler):
    """HTTP handler answering `/v1/chat/completions` with canned lines — a fake OpenAI-compatible brain.
    
    HTTP 处理器：给 `/v1/chat/completions` 回预先写好的台词，冒充一个 OpenAI 兼容的「大脑」。
    """
    def log_message(self, *a):
        pass

    def do_POST(self):
        if not self.path.rstrip("/").endswith("/chat/completions"):
            self.send_error(404)
            return
        长度 = int(self.headers.get("content-length") or 0)
        体 = json.loads(self.rfile.read(长度).decode("utf-8", "ignore"))
        载台词()

        消息 = 体.get("messages") or []
        工具名 = [t.get("function", {}).get("name") for t in (体.get("tools") or [])]
        print(f"  [假模型] 收到 {len(消息)} 条消息、{len(工具名)} 个工具 "
              f"{工具名[:6]}，最后一条 = {json.dumps(消息[-1], ensure_ascii=False)[:120]}",
              file=sys.stderr, flush=True)

        # 防循环：如果对话里已经出现过 pet_say 的调用，这次就只回一段纯文本（她不显示纯文本，于是自然收尾）
        上次模型轮 = None
        for m in 消息:
            if m.get("role") == "assistant" and m.get("tool_calls"):
                上次模型轮 = m
        # 只看「上一轮模型干了什么」：上一轮已经在 pet_say 了就不再重复（否则她会无限自说自话）
        已经说过 = bool(上次模型轮) and any("pet_say" in json.dumps(c.get("function") or {}, ensure_ascii=False)
                                            for c in 上次模型轮["tool_calls"])
        回复 = {"role": "assistant", "content": None}
        if 台词.get("工具") and not 已经说过:
            回复["tool_calls"] = [{"id": f"call_mock_{int(time.time()*1000)}", "type": "function",
                                  "function": {"name": 台词["工具"],
                                               "arguments": json.dumps(台词.get("参数", {}), ensure_ascii=False)}}]
        else:
            回复["content"] = "（已经打过招呼了）" if 已经说过 else 台词.get("文本", "……")

        出 = {"id": "chatcmpl-mock", "object": "chat.completion", "created": int(time.time()),
              "model": 体.get("model") or "mock",
              "choices": [{"index": 0, "message": 回复, "finish_reason": "tool_calls" if 台词.get("工具") else "stop"}],
              "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}
        数据 = json.dumps(出, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(数据)))
        self.end_headers()
        self.wfile.write(数据)


if __name__ == "__main__":
    解 = argparse.ArgumentParser()
    解.add_argument("--端口", type=int, default=8111)
    解.add_argument("--台词", default=str(Path(__file__).with_name("台词.json")))
    参 = 解.parse_args()
    print(f"  假模型起来了：http://127.0.0.1:{参.端口}/v1/chat/completions（台词 {参.台词}）")
    ThreadingHTTPServer(("127.0.0.1", 参.端口), 处理器).serve_forever()

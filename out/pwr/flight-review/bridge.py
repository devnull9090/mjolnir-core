"""Drive this rehearsal through the project's stdio MCP server, including background capture."""
import base64
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

def call(name, args=None):
    args = args or {}
    if name == "game_input":
        assert args.get("method") == "game"
    if name == "game_screenshot":
        assert args.get("background_only") and not args.get("foreground")
    requests = [
        {"id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","clientInfo":{"name":"pwr-rehearsal","version":"1"},"capabilities":{}}},
        {"method":"notifications/initialized"},
        {"id":2,"method":"tools/call","params":{"name":name,"arguments":args}},
    ]
    proc = subprocess.run(["node", str(ROOT/"tools/mcp/game/server.mjs")],
        input="".join(json.dumps({"jsonrpc":"2.0",**r})+"\n" for r in requests),
        cwd=ROOT, capture_output=True, text=True, timeout=max(45, args.get("timeout_ms",0)/1000+8,
            args.get("wait_seconds",0)+12))
    proc.check_returncode()
    replies=[json.loads(line) for line in proc.stdout.splitlines() if line]
    result=next(reply for reply in replies if reply.get("id")==2)
    if "error" in result: raise RuntimeError(result["error"])
    result=result["result"]
    if result.get("isError"): raise RuntimeError(str(result["content"])[:800])
    return result["content"]

def shot(filename):
    result=call("game_screenshot",{"max_width":1600,"background_only":True})
    for row in result:
        if row["type"]=="image": Path(filename).write_bytes(base64.b64decode(row["data"]))
        elif row["type"]=="text": print(row["text"],flush=True)

def runlua(code):
    return " ".join(row["text"] for row in call("game_lua",{"code":code}) if row["type"]=="text")

if __name__=="__main__":
    if sys.argv[1]=="shot": shot(sys.argv[2])
    elif sys.argv[1]=="lua": print(runlua(sys.stdin.read()))
    else: print(call(sys.argv[1], json.loads(sys.argv[2]) if len(sys.argv)>2 else {}))

import json, os

path = os.path.join(os.environ["APPDATA"], "Claude", "claude_desktop_config.json")

with open(path, "r", encoding="utf-8") as f:
    config = json.load(f)

config["mcpServers"] = {
    "lapis-nexus": {
        "command": r"C:\Users\LG\AppData\Local\pypoetry\Cache\virtualenvs\langchain-kr-0bF25OO7-py3.11\Scripts\python.exe",
        "args": [r"C:\Users\LG\Documents\langchain-kr\29_FINAL\backend\mcp_server.py"]
    }
}

with open(path, "w", encoding="utf-8") as f:
    json.dump(config, f, ensure_ascii=False, indent=2)

print("저장 완료!")
print(f"경로: {path}")

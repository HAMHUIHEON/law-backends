import os, time, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")
from dotenv import load_dotenv; load_dotenv()
from utils.llm import get_llm

llm = get_llm()
print("LLM:", type(llm).__name__)

t = time.time()
r = llm.invoke("Say hi in one word.")
elapsed = time.time() - t

meta = getattr(r, "response_metadata", {})
model = meta.get("model", meta.get("model_name", "unknown"))
print(f"model  : {model}")
print(f"elapsed: {elapsed:.2f}s")
print(f"content: {r.content[:80]}")

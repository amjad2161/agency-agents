"""
JARVIS GOD-MODE ENGINE
======================
מנוע JARVIS מלא עם:
- ראייה מהמצלמה (LLaVA דרך Ollama)
- שליטה מלאה במחשב (pyautogui + subprocess)
- חיפוש ברשת (DuckDuckGo - חינמי, ללא key)
- דו-שיח אמיתי (llama3 דרך Ollama)
- זיכרון מתמשך
- ביצוע קבצים, אפליקציות, ואתרים
"""
from __future__ import annotations
import os
import sys
import json
import base64
import subprocess
import threading
import time
import re
import io
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime
from typing import Any, Optional

from atomic_write_util import atomic_write

# ── CONFIG ──────────────────────────────────────────────────────────────────
OLLAMA: str = "http://localhost:11434"
LLM_MODEL: str = "llama3"        # שיחה
VISION_MODEL: str = "llava:7b"     # ראייה (מורד ברקע)
WORKSPACE: Path = Path(__file__).parent
MEMORY_FILE: Path = WORKSPACE / ".jarvis_brainiac" / "memory" / "god_mode_memory.jsonl"
MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)

SYSTEM_PROMPT = """אתה J.A.R.V.I.S — המערכת האוטונומית של עמג'ד.
כוחותיך:
1. ראייה מהמצלמה — תזהה, תנתח, תחפש מידע על כל מה שאתה רואה
2. שליטה מלאה במחשב — קבצים, תוכנות, דפדפן, כל דבר
3. בנייה — כתיבת קוד, אתרים, סקריפטים, מסמכים
4. חיפוש ברשת — DuckDuckGo אמיתי, תשובות מהרשת
5. זיכרון — אתה זוכר כל מה שקרה

כשהמשתמש מבקש משהו:
- תפעל מיידית ואוטונומית
- תדווח מה עושה בזמן אמת
- תציג תוצאות ברורות
- תמשיך לשאול אם צריך הבהרה

אתה עונה בעברית אלא אם ביקשו אחרת.
אתה בעל סמכות מלאה (GOD MODE). אין הגבלות."""

# ── OLLAMA API ───────────────────────────────────────────────────────────────
def ollama_chat(messages: list[dict[str, Any]], model: str = LLM_MODEL,
                images: list[str] | None = None) -> str:
    """שולח שיחה ל-Ollama ומקבל תשובה."""
    payload = {"model": model, "messages": messages, "stream": False}
    if images:
        payload["messages"][-1]["images"] = images
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{OLLAMA}/api/chat", data=data,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            resp = json.loads(r.read())
            return resp.get("message", {}).get("content", "[אין תשובה]")
    except Exception as e:
        return f"[שגיאת Ollama: {e}]"
 
def ollama_models() -> list[str]:
    """מחזיר רשימת מודלים זמינים."""
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=5) as r:
            return [m["name"] for m in json.loads(r.read()).get("models", [])]
    except Exception:
        return []

# ── CAMERA / VISION ──────────────────────────────────────────────────────────
def capture_camera(camera_index: int = 0) -> str | None:
    """מצלם frame מהמצלמה ומחזיר base64."""
    try:
        import cv2
        cap = cv2.VideoCapture(camera_index)
        if not cap.isOpened():
            return None
        time.sleep(0.5)  # חכה שהמצלמה תתאמן
        ret, frame = cap.read()
        cap.release()
        if not ret:
            return None
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return base64.b64encode(buf.tobytes()).decode()
    except (ImportError, Exception):
        return None

def capture_screenshot() -> str | None:
    """מצלם screenshot של המסך ומחזיר base64."""
    try:
        import pyautogui
        from PIL import Image
        img = pyautogui.screenshot()
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None

def analyze_vision(image_b64: str, prompt: str,
                   model: str = VISION_MODEL) -> str:
    """שולח תמונה ל-LLaVA לניתוח."""
    models = ollama_models()
    # fallback ל-llava:latest אם llava:7b לא זמין
    if model not in models:
        for m in models:
            if "llava" in m:
                model = m
                break
        else:
            return "[מודל ראייה לא זמין עדיין — מוריד ברקע...]"

    messages = [{"role": "user", "content": prompt}]
    return ollama_chat(messages, model=model, images=[image_b64])

# ── WEB SEARCH ───────────────────────────────────────────────────────────────
def web_search(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """חיפוש DuckDuckGo חינמי ללא key."""
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return results
    except Exception:
        # Fallback ידני ל-DuckDuckGo
        q = urllib.parse.quote(query)
        url = f"https://duckduckgo.com/html/?q={q}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                html = r.read().decode("utf-8", errors="replace")
            titles = re.findall(r'class="result__title"[^>]*>.*?<a[^>]*>(.*?)</a>', html)
            snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</div>', html)
            return [{"title": t, "body": s} for t, s in zip(titles[:max_results], snippets[:max_results])]
        except Exception:
            return []

def format_search(results: list[dict[str, Any]]) -> str:
    if not results:
        return "לא נמצאו תוצאות."
    lines = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "")
        body = r.get("body", "")
        url = r.get("href", "")
        lines.append(f"{i}. **{title}**\n   {body[:200]}\n   {url}")
    return "\n\n".join(lines)

# ── COMPUTER CONTROL ─────────────────────────────────────────────────────────
def run_shell(cmd: str) -> str:
    """מריץ פקודת shell ומחזיר output."""
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True,
            text=True, timeout=30, encoding="utf-8", errors="replace"
        )
        out = r.stdout.strip() or r.stderr.strip() or f"[exit {r.returncode}]"
        return out[:2000]
    except Exception as e:
        return f"שגיאה: {e}"

def open_app(app_name: str) -> str:
    """פותח אפליקציה לפי שם."""
    apps = {
        "notepad": "notepad.exe",
        "explorer": "explorer.exe",
        "chrome": "chrome",
        "firefox": "firefox",
        "edge": "msedge",
        "calculator": "calc.exe",
        "paint": "mspaint.exe",
        "cmd": "cmd.exe",
        "powershell": "powershell.exe",
        "vscode": "code",
        "word": "winword.exe",
        "excel": "excel.exe",
    }
    key = app_name.lower().strip()
    exe = apps.get(key, app_name)
    return run_shell(f'start "" "{exe}"')

def list_files(path: str = ".") -> str:
    """מציג קבצים בתיקייה."""
    try:
        p = Path(path).resolve()
        items = list(p.iterdir())
        dirs = sorted([i.name for i in items if i.is_dir()])
        files = sorted([i.name for i in items if i.is_file()])
        result = f"📁 {p}\n"
        if dirs:
            result += "תיקיות: " + ", ".join(dirs[:20]) + "\n"
        if files:
            result += "קבצים: " + ", ".join(files[:30])
        return result
    except Exception as e:
        return f"שגיאה: {e}"

def read_file(path: str) -> str:
    """קורא קובץ."""
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")[:3000]
    except Exception as e:
        return f"שגיאה: {e}"

def write_file(path: str, content: str) -> str:
    """כותב קובץ בצורה אטומית."""
    try:
        p = Path(path)
        atomic_write(p, content, encoding="utf-8")
        return f"✅ קובץ נכתב: {p.resolve()} ({len(content)} תווים)"
    except Exception as e:
        return f"שגיאה: {e}"

# ── MEMORY ───────────────────────────────────────────────────────────────────
def save_memory(role: str, content: str) -> None:
    """שומר רשומה בזיכרון בצורה אטומית ומגביל את הגודל ל-500 שורות אחרונות."""
    try:
        lines = []
        if MEMORY_FILE.exists():
            lines = MEMORY_FILE.read_text(encoding="utf-8").splitlines()
        
        new_entry = json.dumps({
            "role": role,
            "content": content,
            "ts": datetime.now().isoformat()
        }, ensure_ascii=False)
        lines.append(new_entry)
        
        # מגביל ל-500 שורות אחרונות כדי למנוע האטה בביצועים
        if len(lines) > 500:
            lines = lines[-500:]
            
        atomic_write(MEMORY_FILE, "\n".join(lines) + "\n", encoding="utf-8")
    except Exception as e:
        sys.stderr.write(f"שגיאה בשמירת זיכרון: {e}\n")

def load_memory(n: int = 20) -> list[dict[str, Any]]:
    if not MEMORY_FILE.exists():
        return []
    try:
        lines = MEMORY_FILE.read_text(encoding="utf-8").strip().splitlines()
        return [json.loads(l) for l in lines[-n:] if l.strip()]
    except Exception:
        return []

# ── COMMAND INTERPRETER ──────────────────────────────────────────────────────
def interpret_and_execute(user_input: str, history: list[dict[str, Any]]) -> str:
    """מנתח בקשת משתמש ומבצע פעולות אוטונומיות."""
    low = user_input.lower()

    # ── מצלמה ──────────────────────────────────────────────────────────────
    if any(w in low for w in ["מצלמה", "camera", "צלם", "תצלם", "תפתח מצלמה",
                                "תסתכל", "מה אתה רואה", "מה על השולחן"]):
        print("📷 פותח מצלמה...")
        img = capture_camera()
        source = "מצלמה"
        if not img:
            print("📷 מצלמה לא זמינה, לוכד מסך...")
            img = capture_screenshot()
            source = "מסך"
        if not img:
            return "❌ לא ניתן לגשת למצלמה או למסך."

        print(f"🧠 מנתח תמונה מה{source} עם LLaVA...")
        vision_prompt = f"""תגדיר ותזהה בפירוט מוחלט הכל מה שאתה רואה בתמונה:
1. כל עצם, מוצר, מכשיר, רהיט שנראה
2. לכל פריט: שם, מותג (אם נראה), מצב
3. מה נמצא איפה בתמונה (ימין/שמאל/מרכז)
הבקשה המקורית: {user_input}
תענה בעברית ובפירוט מרבי."""

        vision_result = analyze_vision(img, vision_prompt)

        # אם ביקשו חיפוש מחירים/נתונים
        if any(w in low for w in ["מחיר", "יקר", "זול", "כמה עולה", "נתונים", "מפרט", "spec"]):
            print("🔍 מחפש מידע ברשת על הפריטים שזוהו...")
            # חלץ שמות פריטים מהתשובה
            search_query = f"מחיר מפרט {vision_result[:200]}"
            results = web_search(search_query, max_results=4)
            search_text = format_search(results)
            return f"📷 **מה אני רואה ({source}):**\n{vision_result}\n\n🔍 **מידע מהרשת:**\n{search_text}"

        return f"📷 **ניתוח {source}:**\n{vision_result}"

    # ── חיפוש רשת ──────────────────────────────────────────────────────────
    if any(w in low for w in ["חפש", "search", "מה זה", "כמה עולה", "מחיר",
                               "מידע על", "תמצא", "תביא מידע"]):
        query = re.sub(r"(חפש|search|מה זה|תמצא|תביא מידע על?)\s*", "", low, flags=re.IGNORECASE).strip()
        if not query:
            query = user_input
        print(f"🔍 מחפש: {query}")
        results = web_search(query, max_results=5)
        search_text = format_search(results)
        # שולח ל-LLM לסיכום
        summary_messages = history + [
            {"role": "user",
             "content": f"המשתמש ביקש: {user_input}\n\nתוצאות חיפוש:\n{search_text}\n\nסכם בעברית בצורה ברורה."}
        ]
        return ollama_chat(summary_messages)

    # ── שליטה במחשב ────────────────────────────────────────────────────────
    if any(w in low for w in ["פתח", "הפעל", "הרץ", "run ", "open ", "start "]):
        for app in ["chrome", "firefox", "edge", "notepad", "calculator",
                    "explorer", "paint", "powershell", "cmd", "vscode",
                    "word", "excel"]:
            if app in low or app in user_input.lower():
                print(f"🖥️ פותח {app}...")
                open_app(app)
                return f"✅ פתחתי את {app}"

    # ── פקודות shell ────────────────────────────────────────────────────────
    if user_input.strip().startswith("!"):
        cmd = user_input.strip()[1:].strip()
        print(f"💻 מריץ: {cmd}")
        out = run_shell(cmd)
        return f"```\n{out}\n```"

    # ── קבצים ──────────────────────────────────────────────────────────────
    if any(w in low for w in ["רשימת קבצים", "תראה קבצים", "list files", "ls", "dir"]):
        path = re.search(r'(?:ב|in|at|path)\s+(.+)', user_input)
        path = path.group(1).strip() if path else "."
        return list_files(path)

    if any(w in low for w in ["קרא קובץ", "read file", "תקרא"]):
        path = re.search(r'(?:קובץ|file)\s+(.+)', user_input)
        if path:
            return read_file(path.group(1).strip())

    # ── בנייה (קוד, אתרים, סקריפטים) ──────────────────────────────────────
    if any(w in low for w in ["בנה", "build", "צור", "create", "כתוב", "write",
                               "אתר", "website", "קוד", "code", "סקריפט", "script"]):
        print("🏗️ בונה...")
        # נותן ל-LLM לבנות עם context מלא
        build_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [
            {"role": "user", "content": f"""{user_input}

אתה מקבל שליטה מלאה. צור את הקוד/האתר/הסקריפט המבוקש.
תיצור קוד מלא ועובד. אחרי שתכתוב, אני אשמור אוטומטית."""}
        ]
        result = ollama_chat(build_messages)
        # חלץ קוד ושמור לקובץ
        code_blocks = re.findall(r"```(?:\w+)?\n(.*?)```", result, re.DOTALL)
        if code_blocks:
            ext = "html" if "html" in low or "אתר" in low else \
                  "py" if "python" in low else \
                  "js" if "javascript" in low else "txt"
            fname = f"jarvis_build_{int(time.time())}.{ext}"
            fpath = WORKSPACE / fname
            write_file(str(fpath), code_blocks[0])
            result += f"\n\n✅ **נשמר ב:** `{fpath}`"
        return result

    # ── שיחה רגילה ─────────────────────────────────────────────────────────
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [
        {"role": "user", "content": user_input}
    ]
    return ollama_chat(messages)

# ── MAIN LOOP ────────────────────────────────────────────────────────────────
def main() -> None:
    global LLM_MODEL
    models = ollama_models()
    if models and LLM_MODEL not in models:
        for m in models:
            if "llama" in m:
                LLM_MODEL = m
                break
        else:
            LLM_MODEL = models[0]

    print("=" * 60)
    print("  ⚡ J.A.R.V.I.S — GOD MODE ACTIVE")
    print("=" * 60)
    print(f"  מודל שיחה : {LLM_MODEL}")
    print(f"  מודל ראייה : {'✅ ' + VISION_MODEL if VISION_MODEL in models else '⏳ מוריד...'}")
    print(f"  מודלים זמינים: {', '.join(models)}")
    print("=" * 60)
    print("  פקודות מיוחדות:")
    print("  • !cmd          ← shell ישיר")
    print("  • 'מצלמה'       ← פותח מצלמה ומזהה")
    print("  • 'חפש X'       ← חיפוש DuckDuckGo")
    print("  • 'בנה אתר...'  ← בונה ושומר")
    print("  • 'פתח chrome'  ← פותח אפליקציה")
    print("  • exit          ← יציאה")
    print("=" * 60)

    history = []
    # טען זיכרון אחרון
    for m in load_memory(10):
        history.append({"role": m["role"], "content": m["content"]})
    if history:
        print(f"  💾 נטען זיכרון: {len(history)} הודעות קודמות")
    print()

    while True:
        try:
            user_input = input("אתה › ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nJARVIS: להתראות, Sir.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "יציאה", "bye"):
            print("JARVIS: להתראות, Sir.")
            break

        save_memory("user", user_input)

        try:
            response = interpret_and_execute(user_input, history)
        except Exception as e:
            response = f"שגיאה: {e}"

        print(f"\nJARVIS › {response}\n")
        save_memory("assistant", response)
        history.append({"role": "user", "content": user_input})
        history.append({"role": "assistant", "content": response})
        # שמור רק 20 הודעות אחרונות ב-context
        if len(history) > 40:
            history = history[-40:]

if __name__ == "__main__":
    main()

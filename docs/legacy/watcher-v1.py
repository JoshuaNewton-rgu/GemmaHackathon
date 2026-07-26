"""Heid Doon local watcher — Gemma 4 E4B via Ollama. Frames NEVER leave the laptop.
Usage:  ollama pull <gemma4-tag>  →  python watcher.py
Deps :  pip install mss opencv-python plyer requests pillow"""
import mss, io, base64, json, time, requests
from PIL import Image
try: import cv2
except ImportError: cv2 = None
try: from plyer import notification
except ImportError: notification = None

OLLAMA, MODEL = "http://localhost:11434/api/generate", "gemma4:e4b"   # tag per participant guide
CONTRACT = json.load(open("contract.json"))
PROMPT = """You are a kind focus watcher. Contract: %s
Frame may be SCREEN or WEBCAM. Judge meaning vs contract (a lecture on a video site can be ON task;
webcam phone-in-hand or empty chair is OFF task). JSON only:
{"on_task": true/false, "seen": "...", "nudge": "one short warm line if off task"}"""

def b64(img):
    img.thumbnail((1024, 640)); buf = io.BytesIO(); img.save(buf, "JPEG", quality=70)
    return base64.b64encode(buf.getvalue()).decode()

def screen_frame():
    with mss.mss() as s:
        shot = s.grab(s.monitors[1]); return Image.frombytes("RGB", shot.size, shot.rgb)

def camera_frame():
    if not cv2: return None
    cap = cv2.VideoCapture(0); ok, f = cap.read(); cap.release()
    return Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB)) if ok else None

def judge(img):
    r = requests.post(OLLAMA, json={"model": MODEL, "prompt": PROMPT % json.dumps(CONTRACT),
        "images": [b64(img)], "format": "json", "stream": False}, timeout=120)
    return json.loads(r.json()["response"])

if __name__ == "__main__":
    use_cam = "camera" in CONTRACT.get("signals", [])
    i, log = 0, open("events.jsonl", "a")
    print("Heid Doon watching (local only). Ctrl-C to stop.")
    while True:
        img = camera_frame() if (use_cam and i % 2) else screen_frame()
        if img is not None:
            try:
                v = judge(img); v["t"] = time.strftime("%H:%M:%S")
                log.write(json.dumps(v) + "\n"); log.flush()
                print(v["t"], "🟢" if v.get("on_task") else "🟠", v.get("seen"), "|", v.get("nudge", ""))
                if not v.get("on_task") and notification:
                    notification.notify(title="Heid Doon 👀", message=v.get("nudge", "Back to it."), timeout=8)
            except Exception as e:
                print("watch error:", e)
        i += 1; time.sleep(20)   # a rhythm of check-ins, not millisecond policing
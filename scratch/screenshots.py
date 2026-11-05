"""Full-page screenshots of the seven chapters (headless Chrome via the DevTools protocol).

Kept outside the project's dependencies: needs a local Chrome and a running dashboard
(`streamlit run app.py --server.port 8765`). Run: .venv\\Scripts\\python scratch\\screenshots.py
"""

import asyncio
import base64
import json
import subprocess
import time
import urllib.request
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parent.parent
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BASE = "http://localhost:8765"
PAGES = {"1_story": "", "2_corridors": "corridors", "3_collateral": "collateral", "4_france": "france",
         "5_calendar": "calendar", "6_japan": "japan", "7_desk_note": "desk-note", "8_appendix": "robustness"}
WIDTH = 1280


async def shoot(ws_url: str, url: str, out: Path) -> None:
    async with websockets.connect(ws_url, max_size=2 ** 28) as ws:
        n = 0

        async def call(method, **params):
            nonlocal n
            n += 1
            await ws.send(json.dumps({"id": n, "method": method, "params": params}))
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("id") == n:
                    return msg.get("result", {})

        await call("Emulation.setDeviceMetricsOverride", width=WIDTH, height=900, deviceScaleFactor=1, mobile=False)
        await call("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": "light"}])
        await call("Page.enable")
        await call("Page.navigate", url=url)
        await asyncio.sleep(15)  # Streamlit renders over a websocket after load: wait in real time
        # Streamlit scrolls inside its main container: expand it so the whole page is laid out.
        height = (await call("Runtime.evaluate", returnByValue=True, expression="""
            (() => { const m = document.querySelector('[data-testid="stMain"]') || document.body;
                     const h = Math.max(m.scrollHeight, document.body.scrollHeight);
                     document.querySelectorAll('[data-testid="stAppViewContainer"], [data-testid="stMain"], .stApp')
                       .forEach(e => { e.style.height = h + 'px'; e.style.overflow = 'visible'; });
                     return h; })()"""))["result"]["value"]
        await call("Emulation.setDeviceMetricsOverride", width=WIDTH, height=int(height) + 40, deviceScaleFactor=1,
                   mobile=False)
        await asyncio.sleep(3)
        shot = await call("Page.captureScreenshot", format="png", captureBeyondViewport=True)
        out.write_bytes(base64.b64decode(shot["data"]))
        print(out.name, int(height), "px")


def main() -> None:
    proc = subprocess.Popen([CHROME, "--headless=new", "--remote-debugging-port=9333", "--disable-gpu",
                             "--hide-scrollbars", f"--user-data-dir={ROOT / 'scratch' / 'chrome-profile'}",
                             "about:blank"])
    try:
        for _ in range(30):
            try:
                tabs = json.load(urllib.request.urlopen("http://127.0.0.1:9333/json"))
                break
            except Exception:
                time.sleep(1)
        ws_url = next(t["webSocketDebuggerUrl"] for t in tabs if t["type"] == "page")
        for name, path in PAGES.items():
            asyncio.run(shoot(ws_url, f"{BASE}/{path}", ROOT / "docs" / "images" / f"{name}.png"))
    finally:
        proc.terminate()


if __name__ == "__main__":
    main()

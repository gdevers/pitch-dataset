"""Headless-Chrome smoke test + screenshots for the 3D strike zone page.

Drives Chrome over the DevTools protocol (``websockets``; no Playwright), calls the page's
``window.Z3D`` hooks, saves PNGs and fails if the page logs any console error or exception.

    uv run python scripts/zone3d_shots.py                       # static docs/zone-3d.html
    uv run python scripts/zone3d_shots.py --live http://127.0.0.1:8799/zone3d
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import itertools
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

import websockets

ROOT = Path(__file__).resolve().parents[1]
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
WIDTH, HEIGHT = 1400, 1000
_CLIP_JS = """(() => {
  const rs = __SELECTORS__.map(s => document.querySelector(s).getBoundingClientRect());
  const x0 = Math.min(...rs.map(r => r.left)), y0 = Math.min(...rs.map(r => r.top));
  const x1 = Math.max(...rs.map(r => r.right)), y1 = Math.max(...rs.map(r => r.bottom));
  return {x: x0 + scrollX - 6, y: y0 + scrollY - 6, width: x1 - x0 + 12, height: y1 - y0 + 12};
})()"""


def _new_target(port: int) -> dict[str, Any]:
    req = urllib.request.Request(f"http://127.0.0.1:{port}/json/new?about:blank", method="PUT")
    return json.loads(urllib.request.urlopen(req).read())


class CDP:
    def __init__(self, ws: Any) -> None:
        self.ws = ws
        self.ids = itertools.count(1)
        self.pending: dict[int, asyncio.Future] = {}
        self.errors: list[str] = []
        self.reader = asyncio.create_task(self._read())

    async def _read(self) -> None:
        async for raw in self.ws:
            msg = json.loads(raw)
            if "id" in msg and msg["id"] in self.pending:
                self.pending.pop(msg["id"]).set_result(msg)
                continue
            method, params = msg.get("method"), msg.get("params", {})
            if method == "Runtime.exceptionThrown":
                d = params["exceptionDetails"]
                self.errors.append(f"exception: {d.get('exception', {}).get('description') or d.get('text')}")
            elif method == "Runtime.consoleAPICalled" and params.get("type") in ("error", "assert"):
                args = " ".join(str(a.get("value", a.get("description", ""))) for a in params.get("args", []))
                self.errors.append(f"console.{params['type']}: {args}")
            elif method == "Log.entryAdded" and params["entry"].get("level") == "error":
                self.errors.append(f"log: {params['entry'].get('text')} {params['entry'].get('url', '')}")

    async def send(self, method: str, params: dict[str, Any] | None = None, timeout: float = 60) -> dict[str, Any]:
        mid = next(self.ids)
        fut = asyncio.get_running_loop().create_future()
        self.pending[mid] = fut
        await self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        msg = await asyncio.wait_for(fut, timeout)
        if "error" in msg:
            raise RuntimeError(f"{method}: {msg['error']}")
        return msg["result"]

    async def js(self, expr: str, timeout: float = 60) -> Any:
        res = await self.send(
            "Runtime.evaluate",
            {"expression": expr, "awaitPromise": True, "returnByValue": True},
            timeout,
        )
        if "exceptionDetails" in res:
            raise RuntimeError(f"JS failed: {expr}\n{res['exceptionDetails']}")
        return res["result"].get("value")

    async def shot(self, path: Path, selectors: list[str]) -> None:
        rect = await self.js(_CLIP_JS.replace("__SELECTORS__", json.dumps(selectors)))
        await asyncio.sleep(0.4)
        res = await self.send(
            "Page.captureScreenshot",
            {"format": "png", "clip": {**rect, "scale": 1}, "captureBeyondViewport": True},
        )
        path.write_bytes(base64.b64decode(res["data"]))
        print(f"  saved {path} ({path.stat().st_size // 1024} KB)")


async def open_page(port: int, url: str) -> tuple[Any, CDP]:
    target = await asyncio.to_thread(_new_target, port)
    ws = await websockets.connect(target["webSocketDebuggerUrl"], max_size=64 * 1024 * 1024)
    cdp = CDP(ws)
    for domain in ("Runtime", "Log", "Page"):
        await cdp.send(f"{domain}.enable")
    await cdp.send(
        "Emulation.setDeviceMetricsOverride",
        {"width": WIDTH, "height": HEIGHT, "deviceScaleFactor": 1, "mobile": False},
    )
    await cdp.send("Page.navigate", {"url": url})
    for _ in range(240):
        await asyncio.sleep(0.25)
        if await cdp.js("document.readyState === 'complete' && !!window.Z3D"):
            break
    await cdp.js("window.Z3D.ready")
    state = await cdp.js("window.Z3D.state")
    if not state["ready"]:
        raise RuntimeError(f"page not ready: {state}")
    return ws, cdp


STAGE = [".z3-grid"]


async def static_suite(cdp: CDP, out: Path) -> None:
    for cam in ("catcher", "batter", "pitcher", "side"):
        await cdp.js(f"window.Z3D.setCamera('{cam}')")
        await cdp.shot(out / f"zone3d_{cam}.png", STAGE)

    i = await cdp.js(
        "(() => { const rs = window.Z3D.rows(); let best = -1, d = 0;"
        "rs.forEach((r, i) => { if (r.res === 'IP' && r.dist > d && r.la > 15) { d = r.dist; best = i; } }); return best; })()"
    )
    await cdp.js(f"window.Z3D.selectPitch({i}); window.Z3D.setCamera('field')")
    await cdp.shot(out / "zone3d_field_arc.png", STAGE)

    await cdp.js("window.Z3D.setPitcher(656302)")  # Dylan Cease: slider-heavy
    await cdp.js("window.Z3D.setFilter({pt: 'SL', n: 100})")
    await cdp.js("window.Z3D.setCamera('catcher')")
    await cdp.shot(out / "zone3d_slider_break.png", STAGE)

    await cdp.js("window.Z3D.setFilter({pt: 'all'})")
    await cdp.js("window.Z3D.setTunnel(true)")
    await cdp.shot(out / "zone3d_tunnel.png", [".z3-grid", "#z3-tunnel"])
    await cdp.js("window.Z3D.setTunnel(false)")

    # playback + back-of-zone example + full page
    await cdp.js("window.Z3D.setMode('all'); window.Z3D.setSpeed(0.1); window.Z3D.play()")
    await asyncio.sleep(1.5)
    state = await cdp.js("window.Z3D.state")
    assert state["playing"], state
    await cdp.shot(out / "zone3d_playback.png", STAGE)
    await cdp.js("window.Z3D.stop()")
    row = await cdp.js("document.querySelector('.z3-ex') && Number(document.querySelector('.z3-ex').dataset.row)")
    if row is not None:
        await cdp.js(f"window.Z3D.selectRowId({row})")
        await cdp.shot(out / "zone3d_backzone_example.png", STAGE)
    await cdp.js("window.Z3D.setCamera('catcher')")
    await cdp.shot(out / "zone3d_full.png", ["main"])


async def live_suite(cdp: CDP, out: Path) -> None:
    await cdp.js("window.Z3D.setCamera('catcher')")
    i = await cdp.js("window.Z3D.findPitch(r => r.res === 'IP')")
    if i >= 0:
        await cdp.js(f"window.Z3D.selectPitch({i})")
    await cdp.shot(out / "zone3d_live.png", [".z3-grid"])
    await cdp.js("window.Z3D.setFilter({pt: 'CH', count: 'two_strike', result: 'all', n: 200})")
    state = await cdp.js("window.Z3D.state")
    print(f"  live filter CH/two_strike: {state['nShown']} pitches shown")


async def run(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    failures = 0
    suites = []
    if not args.skip_static:
        suites.append(("static", Path(args.html).resolve().as_uri(), static_suite))
    if args.live:
        suites.append(("live", args.live, live_suite))
    for name, url, suite in suites:
        print(f"[{name}] {url}")
        ws, cdp = await open_page(args.port, url)
        await suite(cdp, out)
        page_errors = (await cdp.js("window.Z3D.state"))["errors"]
        errs = cdp.errors + [f"page: {e}" for e in page_errors]
        print(f"  console errors/exceptions: {len(errs)}")
        for e in errs:
            print(f"    {e}")
        failures += len(errs)
        cdp.reader.cancel()
        await ws.close()
    return 1 if failures else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--html", default=str(ROOT / "docs" / "zone-3d.html"))
    ap.add_argument("--live", default=None, help="Live page URL, e.g. http://127.0.0.1:8799/zone3d")
    ap.add_argument("--skip-static", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "logs" / "shots"))
    ap.add_argument("--port", type=int, default=9333)
    ap.add_argument("--chrome", default=CHROME)
    args = ap.parse_args()

    profile = Path(tempfile.mkdtemp(prefix="chrome-z3d-", dir=ROOT / "logs"))
    proc = subprocess.Popen(
        [
            args.chrome, "--headless=new", f"--remote-debugging-port={args.port}",
            "--use-angle=swiftshader", "--enable-unsafe-swiftshader", f"--window-size={WIDTH},{HEIGHT}",
            f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
            "--hide-scrollbars", "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{args.port}/json/version", timeout=1)
                break
            except OSError:
                time.sleep(0.2)
        return asyncio.run(run(args))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(profile, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

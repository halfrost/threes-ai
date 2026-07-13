"""Discover the selectors driver.py needs, on a live Threes page.

driver.py's DOM reader needs three selectors: the board container, the next-tile
preview, and the game-over marker. This opens the page, finds every numbered
tile, infers the smallest common ancestor that bounds them (a good board-selector
candidate), and prints CSS selectors for the tiles, the likely next preview, and
any <canvas> (which means you must use the OCR route instead). Paste the output
back and finalize driver.py's SITES config or pass --board-selector etc.

Usage:  python probe.py [--url https://threesjs.io/] [--headless]
"""
from __future__ import annotations
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from common import VALUE  # noqa: E402

TILE_VALUES = [str(v) for v in VALUE if v >= 1]

PROBE_JS = r"""
(vals) => {
  const want = new Set(vals);
  const sel = (el) => {
    if (el.id) return '#' + el.id;
    const cls = (el.className && el.className.toString().trim().split(/\s+/)
                 .filter(Boolean).map(c => '.' + c).join('')) || '';
    return el.tagName.toLowerCase() + cls;
  };
  const tiles = [];
  for (const el of document.querySelectorAll('*')) {
    const t = (el.textContent || '').trim();
    if (!want.has(t)) continue;
    if ([...el.children].some(c => (c.textContent || '').trim() === t)) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    tiles.push({v: t, sel: sel(el), parentSel: el.parentElement ? sel(el.parentElement) : '',
                cx: r.left + r.width / 2, cy: r.top + r.height / 2});
  }
  // smallest element whose rect contains all tile centres = likely board container
  let container = null, best = Infinity;
  if (tiles.length) {
    const minx = Math.min(...tiles.map(t => t.cx)), maxx = Math.max(...tiles.map(t => t.cx));
    const miny = Math.min(...tiles.map(t => t.cy)), maxy = Math.max(...tiles.map(t => t.cy));
    for (const el of document.querySelectorAll('*')) {
      const r = el.getBoundingClientRect();
      if (r.left <= minx && r.top <= miny && r.right >= maxx && r.bottom >= maxy) {
        const area = r.width * r.height;
        if (area > 0 && area < best) { best = area; container = sel(el); }
      }
    }
  }
  return {tiles, container, hasCanvas: !!document.querySelector('canvas'),
          canvasSel: document.querySelector('canvas') ? sel(document.querySelector('canvas')) : ''};
}
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="https://threesjs.io/")
    ap.add_argument("--headless", action="store_true")
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=a.headless)
        page = browser.new_page()
        page.goto(a.url)
        page.wait_for_timeout(2500)
        try:
            page.click("body")
        except Exception:
            pass
        r = page.evaluate(PROBE_JS, TILE_VALUES)
        print(f"\nURL: {a.url}")
        print(f"canvas present: {r['hasCanvas']}"
              + (f"  ({r['canvasSel']})  -> use the OCR route (--site threesgame)" if r["hasCanvas"] else ""))
        print(f"numbered tiles found: {len(r['tiles'])}")
        if r["tiles"]:
            print(f"suggested --board-selector:  {r['container']}")
            sels = sorted({t["sel"] for t in r["tiles"]})
            print(f"tile element selectors seen: {sels}")
            print("tiles (value @ x,y):")
            for t in r["tiles"][:16]:
                print(f"   {t['v']:>4} @ {t['cx']:.0f},{t['cy']:.0f}  ({t['sel']})")
        else:
            print("No numbered tiles in the DOM — the board is likely a <canvas>; "
                  "use the OCR route. Start a game first if the page loaded a menu.")
        print("\nNext, verify:  python driver.py --site threesjs "
              f"--url {a.url} --board-selector '{r.get('container','')}'")
        browser.close()


if __name__ == "__main__":
    main()

"""One-time helper: clear the play.threesgame.com tutorial by hand so a persistent
profile skips it afterwards. The official Threes web starts with a multi-stage
guided tutorial (add 1&2, 3+3=6, ...) that the search/spam can't clear on its
own, so a human plays it once here; the profile (localStorage) then remembers it.

Run it (NOT via a heredoc — input()/detection need a real window):
    SSL_CERT_FILE=~/.threes-ca.pem python deploy/web/threesgame_clear_tutorial.py

A visible Chrome opens on play.threesgame.com. Play through the tutorial with the
arrow keys until a NORMAL game appears (board fills with tiles). The script polls
the board and auto-closes once it sees a real game (>= 6 tiles), saving the
profile to ~/.threes-tg-profile. You can also just close the window yourself.
"""
import io
import os
import time

from PIL import Image
from playwright.sync_api import sync_playwright

PROFILE = os.path.expanduser("~/.threes-tg-profile")
COLC = [331, 523, 716, 908]
ROWC = [512, 771, 1029, 1288]


def cls(im, x, y, h=48):
    px = list(im.crop((x - h, y - h, x + h, y + h)).resize((10, 10)).getdata())
    n = len(px)
    r, g, b = (sum(p[k] for p in px) / n for k in range(3))
    if b > g + 18 and b > r + 40 and r < 175:
        return 1                                        # blue
    if r > g + 30 and r > b + 30 and g < 170:
        return 2                                        # red
    if r > 195 and g > 195 and b > 185 and abs(r - g) < 25:
        return 3                                        # white
    return 0                                            # empty


def tile_count(pg):
    im = Image.open(io.BytesIO(pg.screenshot(type="png"))).convert("RGB")
    return sum(1 for r in range(4) for c in range(4) if cls(im, COLC[c], ROWC[r]) > 0)


def main():
    print(f"Opening play.threesgame.com — clear the tutorial by hand. Profile: {PROFILE}")
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE, channel="chrome", headless=False,
            args=["--ignore-certificate-errors"],
            viewport={"width": 420, "height": 760}, device_scale_factor=3)
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        pg.goto("https://play.threesgame.com/", wait_until="domcontentloaded")
        stable = 0
        try:
            for _ in range(600):          # up to ~10 min
                pg.wait_for_timeout(1000)
                try:
                    n = tile_count(pg)
                except Exception:
                    break                 # window closed by the user
                if n >= 6:
                    stable += 1
                    if stable >= 2:
                        print(f"Detected a normal game ({n} tiles) — tutorial cleared, "
                              "profile saved. Closing in 5s...")
                        pg.wait_for_timeout(5000)
                        break
                else:
                    stable = 0
        except KeyboardInterrupt:
            pass
        finally:
            try:
                ctx.close()
            except Exception:
                pass
    print("Done. Profile ~/.threes-tg-profile now skips the tutorial.")


if __name__ == "__main__":
    main()

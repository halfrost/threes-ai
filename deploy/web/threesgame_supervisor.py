"""Watchdog that drives threesgame_driver.py to a full game despite the WebGL
wedge.

play.threesgame.com intermittently wedges the Chrome<->Playwright channel: some
in-flight call (a keypress, a localStorage read) blocks forever and cannot be
interrupted in-process (page/CDP timeouts and SIGALRM all fail against the sync
greenlet — verified). The only reliable cure is to kill the whole process. This
supervisor does exactly that:

  * runs threesgame_driver.py on a PERSISTENT profile, which appends every
    confirmed move to a shared JSONL log (its mtime is our heartbeat);
  * if the log stops growing for --stall-timeout seconds, the inner is wedged, so
    we SIGKILL its process group and any Chrome on that profile, then relaunch;
  * the game persisted itself to localStorage slot.0, so the relaunched inner
    RESUMES the exact in-progress board (verified) and keeps appending;
  * when the inner exits 0 (real game over) we assemble the whole game from the
    JSONL into a replay (engine/replay.go schema, plays in web/replay.html) and
    keep it iff it beats the best (deploy/recorder.py BestKeeper), alongside the
    settlement screenshot the inner grabbed.

Run:
  go run ../../cmd/moveserver -addr :9053 -deckaware &
  SSL_CERT_FILE=~/.threes-ca.pem python threesgame_supervisor.py \
      --server http://127.0.0.1:9053 --record-dir ../../results/replays/threesgame --games 5
"""
import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from recorder import GameRecorder, BestKeeper  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
INNER = os.path.join(HERE, "threesgame_driver.py")


def _pkill_profile(profile):
    """Kill any Chrome still holding this profile (a killed inner can orphan it)."""
    subprocess.run(["pkill", "-9", "-f", profile], check=False)


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def _count_plies(path):
    """Confirmed moves recorded so far (JSONL lines that aren't terminal markers)."""
    n = 0
    try:
        with open(path) as f:
            for line in f:
                if line.strip() and '"terminal"' not in line:
                    n += 1
    except OSError:
        pass
    return n


def _wipe(profile, log_path):
    """Start a brand-new game: drop the profile (localStorage) and the ply log."""
    shutil.rmtree(profile, ignore_errors=True)
    _pkill_profile(profile)
    try:
        os.remove(log_path)
    except OSError:
        pass
    open(log_path, "w").close()


def run_one_game(a, profile, log_path, png_path):
    """Drive one full game to completion, relaunching the inner on every wedge.
    Returns True if a real game-over was reached.

    Resume only works once the game is a few moves in — a game wedged at 0 moves
    reloads into a limbo that won't accept input (verified: resuming a 12-move
    game is seamless, a 0-move game is stuck). So until >=2 moves are safely
    banked, treat every stall as "start over fresh"; after that, resume."""
    _wipe(profile, log_path)

    env = dict(os.environ)
    restarts = 0
    while restarts <= a.max_restarts:
        proc = subprocess.Popen(
            [sys.executable, INNER,
             "--server", a.server, "--profile", profile,
             "--resume-log", log_path, "--gameover-png", png_path,
             "--moves", str(a.moves), "--depth-cap", str(a.depth_cap)]
            + (["--headed"] if a.headed else []),
            env=env, start_new_session=True)     # own process group so we can killpg
        tag = f"[sup] run {restarts} pid={proc.pid}"
        print(tag, flush=True)

        # watch: exit? or heartbeat (log mtime) stalled?
        last_beat = time.time()
        last_mtime = _mtime(log_path)
        while True:
            time.sleep(2.0)
            rc = proc.poll()
            if rc is not None:
                if rc == 0:
                    print(f"{tag}: exited 0 (game over)", flush=True)
                    return True
                print(f"{tag}: exited {rc}", flush=True)
                break
            mt = _mtime(log_path)
            if mt > last_mtime:
                last_mtime, last_beat = mt, time.time()
            elif time.time() - last_beat > a.stall_timeout:
                print(f"{tag}: WEDGED ({a.stall_timeout}s no progress, "
                      f"{_count_plies(log_path)} plies) — kill", flush=True)
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                _pkill_profile(profile)
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    pass
                break

        restarts += 1
        if _count_plies(log_path) < 2:
            print("[sup]   <2 moves banked — wiping for a fresh start", flush=True)
            _wipe(profile, log_path)
        else:
            time.sleep(1.5)     # let Chrome fully release the profile before resuming
    print(f"[sup] gave up after {a.max_restarts} restarts", flush=True)
    return False


def assemble(log_path, depth_cap):
    """Build a replay dict from the full JSONL ply log."""
    rec = GameRecorder(agent="threesgame-web-expectimax", depth_cap=depth_cap)
    last_board = [[0] * 4 for _ in range(4)]
    terminal = None
    with open(log_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if "terminal" in r:
                terminal = r["terminal"]
                continue
            rec.record(r["b"], r["n"], r["m"])
            last_board = r["b"]
    rec.finish(terminal if terminal is not None else last_board)
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://127.0.0.1:9053")
    ap.add_argument("--record-dir", default="")
    ap.add_argument("--games", type=int, default=1)
    ap.add_argument("--moves", type=int, default=2000)
    ap.add_argument("--depth-cap", type=int, default=5)
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--stall-timeout", type=float, default=30.0)
    ap.add_argument("--max-restarts", type=int, default=40)
    ap.add_argument("--profile", default=os.path.expanduser("~/.threes-tg-profile"))
    ap.add_argument("--work-dir", default="/tmp/threesgame_sup")
    a = ap.parse_args()

    os.makedirs(a.work_dir, exist_ok=True)
    keeper = BestKeeper(a.record_dir) if a.record_dir else None
    for g in range(a.games):
        log_path = os.path.join(a.work_dir, f"plies_{g}.jsonl")
        png_path = os.path.join(a.work_dir, f"gameover_{g}.png")
        print(f"=== game {g+1}/{a.games} ===", flush=True)
        over = run_one_game(a, a.profile, log_path, png_path)
        rec = assemble(log_path, a.depth_cap)
        replay = rec.replay_dict()
        score = replay["final_score"]
        msg = (f"game {g+1}/{a.games}: over={over} score={score} "
               f"max_tile={replay['max_tile']} moves={replay['moves']}")
        if keeper:
            shot = None
            try:
                with open(png_path, "rb") as f:
                    shot = f.read()
            except OSError:
                pass
            saved, _, best = keeper.consider(replay, shot)
            msg += f" | best {best}" + (" -> NEW BEST saved" if saved else "")
        print(msg, flush=True)


if __name__ == "__main__":
    main()

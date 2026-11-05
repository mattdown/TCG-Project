"""A short teaser video for part 1: a few seconds of each demo, spliced, for social posts.

    uv run --project PythonServer --with playwright python Blog/teaser.py   # Blog/build/tcg_part1_teaser.mp4

Run from the repository root, after building the demo pages (or pass --pages with a folder of them). Each
clip steps a page's timeline with window.seek(t), as the visualisers' --render does; the card lab has no
timeline, so it is scrolled and clicked instead. Needs ffmpeg and Chrome.
"""
import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

OUT = Path(__file__).with_name("build")
WIDTH, HEIGHT, FPS, FADE = 1920, 1080, 30, 0.3

# (page, start, end, speed): seconds on the page's own timeline, played `speed` times faster.
CLIPS = [
    ("title", 0, 2.6, 1),
    ("design_loop", 0, 11, 1.4),
    ("gnn_visualiser_1", 1.5, 6.5, 1.25),
    ("gnn_visualiser_2", 11, 21, 2),
    ("gnn_visualiser_3", 1, 11, 2.5),
    ("card_generation_visualiser", 2, 8, 2),
    ("card_generation_visualiser", 40, 54.2, 2),
    ("card_lab", 0, 7, 1),
    ("end", 0, 3.4, 1),
]

CARD = """<!doctype html><meta charset="utf-8">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Marcellus+SC&family=Outfit:wght@500;700&display=swap">
<style>
  body { margin: 0; width: 1920px; height: 1080px; display: flex; flex-direction: column; justify-content: center;
         align-items: center; text-align: center; background: radial-gradient(#0B1612, #050C0A 70%); color: #E6FBF4; }
  h1 { font: 92px/1.1 "Marcellus SC", serif; margin: 0 160px; }
  p { font: 500 44px/1.4 Outfit, sans-serif; color: #7EF0D8; margin: 36px 0 0; }
  small { display: block; font: 500 34px/1.6 Outfit, sans-serif; color: #9FB8B0; }
</style>
<body>BODY</body>"""
TITLE = "<h1>Using AI playtesting to design an original trading card game</h1><p>Part 1: generating cards and a GNN agent</p>"
END = ("<h1>Part 1 is out</h1><p>mattdown.ai/posts/tcg-part-1</p>"
       "<small>Code: github.com/mattdown/TCG-Project</small>")


def frames(tab, clip, write):
    page, t0, t1, speed = clip
    n = round((t1 - t0) / speed * FPS)
    if page in ("title", "end", "card_lab"):
        if page == "card_lab":
            return lab_frames(tab, n, write)
        shot = tab.screenshot(type="png")
        for _ in range(n):
            write(shot)
        return
    for i in range(n):
        tab.evaluate(f"window.seek({t0 + i * speed / FPS})")
        write(tab.screenshot(type="png"))


def lab_frames(tab, n, write):
    """The lab's header, a slow scroll through the cards, then one card opened."""
    hold, scroll = round(1.2 * FPS), round(3.0 * FPS)
    shot = tab.screenshot(type="png")
    for _ in range(hold):
        write(shot)
    top = tab.evaluate("document.querySelector('.slot').getBoundingClientRect().top + scrollY - 140")
    for i in range(scroll):
        x = (i + 1) / scroll
        tab.evaluate(f"scrollTo(0, {top * (1 - (1 - x) ** 3)})")
        write(tab.screenshot(type="png"))
    tab.click(".slot >> nth=3")
    tab.wait_for_timeout(700)
    shot = tab.screenshot(type="png")
    for _ in range(n - hold - scroll):
        write(shot)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pages", type=Path, default=OUT, help="the folder with the built demo pages")
    parser.add_argument("--out", type=Path, default=OUT / "tcg_part1_teaser.mp4")
    args = parser.parse_args()
    if not shutil.which("ffmpeg"):
        raise SystemExit("needs ffmpeg on the PATH")
    from playwright.sync_api import sync_playwright

    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
        tmp = Path(tmp)
        browser = p.chromium.launch(channel="chrome")
        parts = []
        for k, clip in enumerate(CLIPS):
            page = clip[0]
            lab = page == "card_lab"
            # The lab is a document, not a 16:9 stage: lay it out smaller and zoom, so its cards fill the frame.
            tab = browser.new_page(viewport={"width": 1600, "height": 900} if lab else {"width": WIDTH, "height": HEIGHT},
                                   device_scale_factor=WIDTH / 1600 if lab else 1)
            if page in ("title", "end"):
                tab.set_content(CARD.replace("BODY", TITLE if page == "title" else END))
                tab.evaluate("document.fonts.ready")
                tab.wait_for_timeout(300)
            else:
                tab.goto((args.pages / f"{page}.html").resolve().as_uri() + ("" if lab else "?render=1"))
                if lab or page == "design_loop":
                    tab.wait_for_timeout(2000)
                else:
                    tab.wait_for_function("window.ready === true")
            part = tmp / f"{k:02d}.mp4"
            length = (clip[2] - clip[1]) / clip[3]
            ffmpeg = subprocess.Popen(
                ["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(FPS), "-i", "-",
                 "-vf", f"scale={WIDTH}:{HEIGHT},fade=in:d={FADE},fade=out:st={length - FADE:.3f}:d={FADE}",
                 "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-r", str(FPS), str(part)],
                stdin=subprocess.PIPE)
            frames(tab, clip, ffmpeg.stdin.write)
            ffmpeg.stdin.close()
            ffmpeg.wait()
            tab.close()
            parts.append(part)
            print(f"{page} {clip[1]}–{clip[2]} s: {length:.1f} s")
        browser.close()
        (tmp / "list.txt").write_text("".join(f"file '{f}'\n" for f in parts))
        args.out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(tmp / "list.txt"),
                        "-c", "copy", "-movflags", "+faststart", str(args.out)], check=True)
    print(f"Wrote {args.out} ({args.out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()

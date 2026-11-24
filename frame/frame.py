"""Turn any photo or drawing into the frame picture: check it, fit it to the Kindle screen, tune it for
E Ink, write a preview, and (only with --publish) put it online.

    python scripts/frame.py PHOTO                    # check + make the picture + preview, nothing goes online
    python scripts/frame.py PHOTO --publish          # same, then publish.py (www.ozgurgulsuna.com/works.bmp)

Steps:
  1. Check   upright from the phone's rotation tag; size, brightness, contrast, noise; GPS warning.
  2. Fit     600x800 portrait. Landscape photos are turned clockwise (--no-turn: crop a portrait piece).
             The crop window sits in the centre; --at 0..1 moves it (0 = left/top, 1 = right/bottom),
             or --fit keeps everything with white bars. --blur x,y,x,y,... blurs a polygon (number plate,
             face), in pixels of the upright photo; repeat for more.
  3. Adjust  tones stretched black..white, mid-greys lifted (--gamma, E Ink shows greys darker than a
             screen), light sharpening after the shrink, 16 greys with dithering. --paper for drawings
             on paper: paper -> clean white, so the grain doesn't speckle.
  4. Preview 02_visual/kindle/previews/NAME_preview.png: the photo with the crop box, the final picture
             at 1:1, and the check results.
  5. Publish only with --publish, after the preview was written.

Settings are saved next to the photo (PHOTO.frame.json) and reused next time, so a later
"frame.py PHOTO --publish" makes exactly the picture you previewed. Flags on the command line win.
Output: 02_visual/kindle/NAME.bmp (24-bit, 600x800), NAME = --name or the photo's file name.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageStat

try:                                    # iPhone HEIC photos, if pillow-heif is installed (it is on GitHub)
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

W, H = 600, 800
GREYS = 16
ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "02_visual" / "kindle"
LANCZOS = Image.Resampling.LANCZOS
FLOYD = Image.Dither.FLOYDSTEINBERG
SAVED = ("name", "turn", "at", "fit", "blur", "gamma", "paper", "sharpen")   # settings kept in PHOTO.frame.json


# ---------- 1. Check ----------

def has_gps(im):
    try:
        return bool(im.getexif().get_ifd(0x8825))
    except Exception:
        return False


def stats(grey):
    """Brightness (mean), contrast (1st..99th percentile spread) and noise of a greyscale image."""
    small = grey.copy(); small.thumbnail((800, 800), LANCZOS)
    h = small.histogram(); n = sum(h)
    def pct(p):
        c = 0
        for v, k in enumerate(h):
            c += k
            if c >= p * n:
                return v
        return 255
    # noise: how much the picture differs from a 3x3 median of itself (grain, sensor noise, JPEG speckle)
    med = small.filter(ImageFilter.MedianFilter(3)).tobytes()
    noise = sum(abs(p - q) for p, q in zip(small.tobytes(), med)) / len(med)
    return dict(mean=ImageStat.Stat(small).mean[0], p1=pct(0.01), p99=pct(0.99), noise=noise)


def warnings_for(st, crop_px, gps, scale_up):
    w = []
    if scale_up > 1.05:
        w.append(f"small: the crop is {crop_px[0]}x{crop_px[1]} px, blown up {scale_up:.1f}x, will look soft")
    if st["mean"] < 70:
        w.append(f"dark: average {st['mean']:.0f}/255, shadows will merge into black (try --gamma 0.75)")
    if st["mean"] > 195:
        w.append(f"bright: average {st['mean']:.0f}/255, light areas will wash out")
    if st["p99"] - st["p1"] < 90:
        w.append(f"flat: tones only span {st['p1']}..{st['p99']}, stretched a lot (may look grainy)")
    if st["noise"] > 9:
        w.append(f"noisy: grain {st['noise']:.1f}, dithering will show it as speckles (try --paper or a cleaner photo)")
    if gps:
        w.append("GPS location in the photo's data (the uploaded BMP has none, but the JPG stays in the project)")
    return w


# ---------- 2. Fit ----------

def crop_box(grey, aspect, at):
    """Window of width/height = aspect inside grey, slid along the long side to `at` (0 = left/top,
    0.5 = centre, 1 = right/bottom). (An automatic "most detail" placement was tried and dropped: on
    real photos the edge-density differences were ~5 % and it cut off subjects.)"""
    iw, ih = grey.size
    if iw / ih > aspect:
        cw, ch, axis = round(ih * aspect), ih, 0
    else:
        cw, ch, axis = iw, round(iw / aspect), 1
    off = round(((iw - cw) if axis == 0 else (ih - ch)) * min(max(at, 0.0), 1.0))
    return (off, 0, off + cw, ch) if axis == 0 else (0, off, cw, off + ch)


def apply_blur(im, polys):
    for poly in polys:
        pts = [(poly[i], poly[i + 1]) for i in range(0, len(poly) - 1, 2)]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        r = max(8, round(max(max(xs) - min(xs), max(ys) - min(ys)) / 12))
        mask = Image.new("L", im.size, 0)
        ImageDraw.Draw(mask).polygon(pts, fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(max(3, r // 4)))
        im = Image.composite(im.filter(ImageFilter.GaussianBlur(r)), im, mask)
    return im


# ---------- 3. Adjust ----------

def adjust(im, gamma, paper, sharpen):
    if paper:
        im = ImageOps.autocontrast(im, cutoff=(0.5, 2))
        im = im.point(lambda v: 255 if v >= 200 else v)              # paper grain -> clean white
    else:
        im = ImageOps.autocontrast(im, cutoff=0.5)
    if gamma != 1:
        im = im.point(lambda v: round(255 * (v / 255) ** gamma))      # gamma < 1 lifts the mid-greys
    if sharpen:
        im = im.filter(ImageFilter.UnsharpMask(radius=1.2, percent=round(60 * sharpen), threshold=2))
    pal = Image.new("P", (1, 1))
    steps = [round(i * 255 / (GREYS - 1)) for i in range(GREYS)]
    pal.putpalette(sum(([s, s, s] for s in steps), []) + [0, 0, 0] * (256 - GREYS))
    return im.convert("RGB").quantize(palette=pal, dither=FLOYD).convert("L")


# ---------- 4. Preview ----------

def font(size):
    for f in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            pass
    return ImageFont.load_default()


def preview(photo_rgb, box, polys, final, lines, out):
    left = photo_rgb.copy(); left.thumbnail((800, 800), LANCZOS)
    s = left.width / photo_rgb.width
    d = ImageDraw.Draw(left)
    for poly in polys:
        d.polygon([(poly[i] * s, poly[i + 1] * s) for i in range(0, len(poly) - 1, 2)], outline=(255, 160, 0), width=3)
    if box:
        d.rectangle([v * s for v in box], outline=(230, 40, 40), width=4)
    f = font(17)
    text_h = 26 * len(lines) + 20
    sheet = Image.new("RGB", (left.width + W + 60, max(left.height, H) + 60 + text_h), (245, 245, 242))
    sheet.paste(left, (20, 40)); sheet.paste(final.convert("RGB"), (left.width + 40, 40))
    d = ImageDraw.Draw(sheet)
    d.text((20, 12), "photo (red = crop, orange = blurred)", fill=(60, 60, 60), font=f)
    d.text((left.width + 40, 12), "frame picture, 1:1, 16 greys", fill=(60, 60, 60), font=f)
    y = max(left.height, H) + 60
    for ln in lines:
        d.text((20, y), ln, fill=(170, 30, 30) if ln.startswith("! ") else (30, 30, 30), font=f); y += 26
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)


# ---------- options in the file name ----------

NAME_WORDS = {"left": ("at", 0.0), "top": ("at", 0.0), "right": ("at", 1.0), "bottom": ("at", 1.0),
              "center": ("at", 0.5), "centre": ("at", 0.5), "middle": ("at", 0.5),
              "fit": ("fit", True), "whole": ("fit", True), "noturn": ("turn", False), "paper": ("paper", True),
              "light": ("gamma", 0.75), "lighter": ("gamma", 0.75), "dark": ("gamma", 1.1), "darker": ("gamma", 1.1)}


def name_options(stem):
    """Words in the file name set options, so a phone upload needs no command line:
    "IMG_7900 left.jpg", "IMG_7900 at30 light.jpg" (at30 = --at 0.30), "drawing fit paper.png".
    Returns (options, name without the option words)."""
    opts, keep = {}, []
    for w in re.split(r"[ _\-+]+", stem):
        lw = w.lower()
        m = re.fullmatch(r"at(0?\.\d+|1(\.0*)?|\d{1,3})", lw)
        if lw in NAME_WORDS:
            k, v = NAME_WORDS[lw]; opts[k] = v
        elif m:
            v = m.group(1); opts["at"] = float(v) if "." in v or v == "1" else int(v) / 100
        elif w:
            keep.append(w)
    return opts, "_".join(keep).lower() or "picture"


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("photo", type=Path)
    ap.add_argument("--name", help="output name (default: photo file name)")
    ap.add_argument("--no-turn", dest="turn", action="store_false", default=None,
                    help="landscape: crop a portrait piece instead of turning the photo")
    ap.add_argument("--at", type=float, help="crop position along the free side, 0 = left/top, 1 = right/bottom")
    ap.add_argument("--fit", action="store_true", default=None, help="keep the whole photo, white bars")
    ap.add_argument("--blur", action="append", metavar="X,Y,X,Y,...", help="polygon to blur (pixels, upright photo)")
    ap.add_argument("--gamma", type=float, help="mid-grey lift, < 1 lighter (default 0.9, --paper 1.0)")
    ap.add_argument("--paper", action="store_true", default=None, help="drawing on paper: paper -> clean white")
    ap.add_argument("--sharpen", type=float, help="0 = off, 1 = normal (default), 2 = strong")
    ap.add_argument("--fresh", action="store_true", help="ignore saved settings")
    ap.add_argument("--publish", action="store_true", help="put the picture online after the preview")
    ap.add_argument("--name-options", action="store_true",
                    help="read options from words in the file name (left/right/at30/fit/light/...), as the GitHub inbox does")
    ap.add_argument("--out", type=Path, default=OUT_DIR, help="folder for the picture (preview goes to OUT/previews)")
    ap.add_argument("--no-save", action="store_true", help="don't write PHOTO.frame.json")
    a = ap.parse_args()

    if not a.photo.is_file():
        sys.exit(f"no such file: {a.photo}")
    side = a.photo.with_name(a.photo.name + ".frame.json")
    saved = {} if a.fresh or not side.exists() else json.loads(side.read_text())
    cfg = {"name": None, "turn": True, "at": 0.5, "fit": False, "blur": [], "gamma": None, "paper": False, "sharpen": 1.0}
    cfg.update({k: v for k, v in saved.items() if k in SAVED})
    for k in SAVED:
        v = getattr(a, k)
        if k == "blur" and v:
            v = [[int(float(t)) for t in b.split(",")] for b in v]
        if v is not None:
            cfg[k] = v
    if a.name_options:
        opts, clean = name_options(a.photo.stem)
        cfg.update(opts)
        cfg["name"] = a.name or clean
        print("options from the file name:", ", ".join(f"{k}={v}" for k, v in opts.items()) or "none")
    gamma_set = cfg["gamma"] is not None                               # only a chosen gamma is saved
    if not gamma_set:
        cfg["gamma"] = 1.0 if cfg["paper"] else 0.9
    name = cfg["name"] or a.photo.stem.lower()
    if saved:
        print(f"using saved settings from {side.name} (--fresh to ignore)")

    # 1. Check
    src = Image.open(a.photo)
    gps = has_gps(src)
    photo = ImageOps.exif_transpose(src).convert("RGB")
    grey = photo.convert("L")
    if cfg["blur"]:
        grey = apply_blur(grey, cfg["blur"])
        photo = apply_blur(photo, cfg["blur"])                         # the preview shows it blurred too
    st = stats(grey)

    # 2. Fit
    landscape = grey.width > grey.height
    turn = landscape and cfg["turn"]
    box = None
    if cfg["fit"]:
        work = grey.rotate(-90, expand=True) if turn else grey
        crop_px = work.size
        scale_up = min(W / work.width, H / work.height)
        img = ImageOps.contain(work, (W, H), LANCZOS)
        canvas = Image.new("L", (W, H), 255)
        canvas.paste(img, ((W - img.width) // 2, (H - img.height) // 2))
        img = canvas
    else:
        box = crop_box(grey, (H / W) if turn else (W / H), cfg["at"])
        piece = grey.crop(box)
        if turn:
            piece = piece.rotate(-90, expand=True)                     # clockwise
        crop_px = piece.size
        scale_up = W / piece.width
        img = piece.resize((W, H), LANCZOS)

    # 3. Adjust
    final = adjust(img, cfg["gamma"], cfg["paper"], cfg["sharpen"])
    a.out.mkdir(parents=True, exist_ok=True)
    bmp = a.out / f"{name}.bmp"
    final.convert("RGB").save(bmp)                                     # 24-bit BMP, what publish.py expects

    # 4. Preview + report
    warn = warnings_for(st, crop_px, gps, scale_up)
    if cfg["fit"]:
        how = "whole photo, white bars"
    else:
        how = "crop %dx%d at %.2f (--at to move: 0 = left/top, 1 = right/bottom)" % (crop_px[0], crop_px[1], cfg["at"])
    shape = "landscape, turned clockwise" if turn else "landscape, not turned" if landscape else "portrait"
    extra = (", paper" if cfg["paper"] else "") + (", %d blurred area(s)" % len(cfg["blur"]) if cfg["blur"] else "")
    lines = ["%s: %dx%d, %s; %s" % (a.photo.name, photo.width, photo.height, shape, how),
             "brightness %.0f/255, tones %d..%d, grain %.1f; gamma %s, sharpen %s%s"
             % (st["mean"], st["p1"], st["p99"], st["noise"], cfg["gamma"], cfg["sharpen"], extra)]
    lines += ["! " + w for w in warn] or ["no warnings"]
    pv = a.out / "previews" / f"{name}_preview.png"
    preview(photo, box, cfg["blur"], final, lines, pv)
    for ln in lines:
        print(ln)
    print(f"picture: {bmp}\npreview: {pv}")

    keep = {k: cfg[k] for k in SAVED if k != "gamma" or gamma_set}
    keep["name"] = name
    if not a.no_save:
        side.write_text(json.dumps(keep, indent=1))

    # 5. Publish
    if a.publish:
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "publish.py"), str(bmp)])
        sys.exit(r.returncode)
    if not a.name_options:                                             # (the GitHub inbox publishes by itself)
        print("not published. When the preview looks right:  python scripts/frame.py "
              f"{a.photo} --publish")


if __name__ == "__main__":
    main()

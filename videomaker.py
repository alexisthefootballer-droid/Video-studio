"""videomaker.py - free HeyGen-style scene composer.

Takes a presenter video (the talking avatar, with its audio) and a list of
scenes, and produces one finished video with animated cards, titles, lower
thirds and a progress bar. Pure Python + Pillow + ffmpeg. No paid services.

    from videomaker import make_video
    make_video("avatar.mp4", scenes, "final.mp4", brand="AlexisTheFootballer",
               name="Alexis", card_side="right")

Each scene is a dict:
    start     seconds from the beginning of the video (first scene = 0)
    layout    "split" | "title" | "presenter" | "image"
    kicker    small label chip, e.g. "RULE 01"
    title     big headline
    subtitle  smaller line under the headline
    bullets   list of short lines that appear one after another
    image     (layout "image" only) path to a picture
"""
import math
import os
import subprocess
import urllib.request

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1280, 720, 25

C = dict(
    bg1=(12, 20, 44), bg2=(44, 24, 96),
    accent=(255, 122, 61), accent2=(110, 98, 255),
    card=(246, 244, 239), ink=(16, 24, 40), muted=(92, 102, 124),
    white=(255, 255, 255), chip=(36, 56, 108),
)

# ----------------------------------------------------------------- helpers


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease_out(t):
    t = clamp(t)
    return 1 - (1 - t) ** 3


def ease_back(t):
    t = clamp(t)
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


# ------------------------------------------------------------------- fonts
_FD = "/tmp/vm_fonts"
_GF = "https://github.com/google/fonts/raw/main/ofl/poppins/"
_FONT_FILES = {
    "bold": ("Poppins-Bold.ttf", _GF + "Poppins-Bold.ttf"),
    "semi": ("Poppins-SemiBold.ttf", _GF + "Poppins-SemiBold.ttf"),
    "reg": ("Poppins-Regular.ttf", _GF + "Poppins-Regular.ttf"),
}
_FALLBACK = {
    "bold": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "semi": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "reg": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
}
_fc = {}


def font(kind, size):
    key = (kind, size)
    if key in _fc:
        return _fc[key]
    name, url = _FONT_FILES[kind]
    path = os.path.join(_FD, name)
    f = None
    try:
        if not os.path.exists(path):
            os.makedirs(_FD, exist_ok=True)
            urllib.request.urlretrieve(url, path)
        if os.path.getsize(path) < 20000:
            os.remove(path)
            raise OSError("bad font download")
        f = ImageFont.truetype(path, size)
    except Exception:
        try:
            f = ImageFont.truetype(_FALLBACK[kind], size)
        except Exception:
            f = ImageFont.load_default()
    _fc[key] = f
    return f


def wrap(text, f, maxw):
    lines, cur = [], ""
    for word in text.split():
        t = (cur + " " + word).strip()
        if f.getlength(t) <= maxw or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def text_img(txt, f, fill):
    l, t, r, b = f.getbbox(txt)
    img = Image.new("RGBA", (int(r) + 6, int(b) + 10), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((0, 0), txt, font=f, fill=tuple(fill) + (255,))
    return img


# ------------------------------------------------------------------ shapes
def rrect(size, radius, fill, ss=3):
    w, h = size
    big = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    ImageDraw.Draw(big).rounded_rectangle(
        (0, 0, w * ss - 1, h * ss - 1), radius * ss, fill=fill)
    return big.resize((w, h), Image.LANCZOS)


def rmask(size, radius):
    return rrect(size, radius, (255, 255, 255, 255)).getchannel("A")


def soft_shadow(size, radius, blur=26, alpha=120, pad=70, dy=18):
    w, h = size
    img = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle(
        (pad, pad + dy, pad + w, pad + h + dy), radius, fill=(0, 0, 0, alpha))
    return img.filter(ImageFilter.GaussianBlur(blur)), pad


def paste_rgba(canvas, layer, x, y, alpha=1.0):
    if alpha <= 0.003:
        return
    if alpha < 0.997:
        lut = [int(i * alpha) for i in range(256)]
        layer = layer.copy()
        layer.putalpha(layer.getchannel("A").point(lut))
    canvas.paste(layer, (int(x), int(y)), layer)


def fit_cover(img, size, top_bias=0.12):
    tw, th = size
    iw, ih = img.size
    s = max(tw / iw, th / ih)
    nw, nh = max(tw, int(round(iw * s))), max(th, int(round(ih * s)))
    img = img.resize((nw, nh), Image.BILINEAR)
    x = (nw - tw) // 2
    y = int((nh - th) * top_bias)
    return img.crop((x, y, x + tw, y + th))


# -------------------------------------------------------------- background
def make_bg():
    w, h = 1920, 1080
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    t = (x / w * 0.6 + y / h * 0.4)[..., None]
    c1 = np.array(C["bg1"], np.float32)[None, None, :]
    c2 = np.array(C["bg2"], np.float32)[None, None, :]
    img = c1 * (1 - t) + c2 * t

    def glow(cx, cy, r, col, k):
        d = ((x - cx) ** 2 + (y - cy) ** 2) / (r * r)
        return np.exp(-d)[..., None] * k * np.array(col, np.float32)[None, None, :]

    img = img + glow(1500, 260, 520, C["accent2"], 0.40) \
        + glow(260, 900, 620, C["accent"], 0.20) \
        + glow(980, 560, 380, C["accent2"], 0.12)
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))


def bottom_fade():
    a = np.zeros((H, W), np.float32)
    ys = np.arange(H, dtype=np.float32)
    a[:] = (np.clip((ys - 260) / (H - 260), 0, 1) ** 1.4 * 215)[:, None]
    img = Image.new("RGBA", (W, H), (6, 10, 24, 255))
    img.putalpha(Image.fromarray(a.astype(np.uint8)))
    return img


# ------------------------------------------------------------- text blocks
def build_text(s, x0, y0, region_h, maxw, ink, muted, chipfill, tsize,
               dur, valign="center", delay0=0.35, sub_fill=None):
    """Return a list of animated items placed in screen coordinates."""
    stack = []  # [kind, img_or_None, rel_y, delay, extra]
    y, d = 0, delay0
    if s.get("kicker"):
        f = font("semi", 20)
        txt = s["kicker"].upper()
        tw = int(f.getlength(txt))
        chip = rrect((tw + 40, 44), 22, tuple(chipfill) + (255,))
        ImageDraw.Draw(chip).text((20, 22), txt, font=f,
                                  fill=(255, 255, 255, 255), anchor="lm")
        stack.append(["img", chip, y, d, None])
        y += 44 + 20
        d += 0.12
    if s.get("title"):
        stack.append(["bar", None, y, d, (96, 6)])
        y += 6 + 22
        d += 0.1
        size = tsize
        for size in (tsize, tsize - 8, tsize - 16, tsize - 24):
            f = font("bold", size)
            lines = wrap(s["title"], f, maxw)
            if len(lines) <= 4:
                break
        lh = int(size * 1.24)
        for ln in lines:
            stack.append(["img", text_img(ln, f, ink), y, d, None])
            y += lh
            d += 0.14
        y += 6
    if s.get("subtitle"):
        f = font("reg", 26)
        for ln in wrap(s["subtitle"], f, maxw):
            stack.append(["img", text_img(ln, f, sub_fill or muted), y, d, None])
            y += 38
            d += 0.1
        y += 12
    bullets = s.get("bullets") or []
    if bullets:
        y += 18
        step = clamp((dur - 2.2 - d) / max(len(bullets), 1), 0.55, 1.7)
        bd = max(d, 1.1)
        f = font("semi", 28)
        for b in bullets:
            lines = wrap(b, f, maxw - 40)
            hh = 40 * len(lines)
            img = Image.new("RGBA", (maxw, hh + 4), (0, 0, 0, 0))
            dr = ImageDraw.Draw(img)
            dr.ellipse((0, 13, 16, 29), fill=C["accent"] + (255,))
            for i, ln in enumerate(lines):
                dr.text((38, i * 40), ln, font=f, fill=tuple(ink) + (255,))
            stack.append(["img", img, y, bd, None])
            y += hh + 14
            bd += step
    total = y
    if valign == "center":
        base = y0 + (region_h - total) // 2
    elif valign == "bottom":
        base = y0 + region_h - total
    else:
        base = y0
    items = []
    for kind, img, ry, dl, extra in stack:
        items.append(dict(kind=kind, img=img, x=x0, y=base + ry,
                          delay=dl, extra=extra, color=ink))
    return items


def draw_items(canvas, items, t, dx=0, gate=1.0):
    dr = ImageDraw.Draw(canvas)
    for it in items:
        p = ease_out((t - it["delay"]) / 0.55)
        if p <= 0:
            continue
        x = it["x"] + dx
        y = it["y"] + (1 - p) * 26
        if it["kind"] == "bar":
            w, h = it["extra"]
            dr.rounded_rectangle((x, y, x + w * ease_out((t - it["delay"]) / 0.7),
                                  y + h), 3, fill=C["accent"])
        else:
            paste_rgba(canvas, it["img"], x, y, p * gate)


# ------------------------------------------------------------ scene prep
def prep(s, dur, brand, side, name):
    layout = s.get("layout", "split")
    p = dict(layout=layout, dur=dur, name=name, brand=brand, side=side)
    if layout == "split":
        pw, ph, cw, ch, m = 520, 640, 620, 640, 48
        if side == "right":
            px, cx = m, W - m - cw
        else:
            cx, px = m, W - m - pw
        py = cy = 40
        p["panel"] = (px, py, pw, ph, 40)
        p["panel_mask"] = rmask((pw, ph), 40)
        p["panel_shadow"] = soft_shadow((pw, ph), 40)
        p["card"] = (cx, cy, cw, ch)
        p["card_img"] = rrect((cw, ch), 40, C["card"] + (255,))
        p["card_shadow"] = soft_shadow((cw, ch), 40)
        p["dir"] = 1 if side == "right" else -1
        p["items"] = build_text(s, cx + 48, cy + 20, ch - 90, cw - 96,
                                C["ink"], C["muted"], C["chip"], 54, dur)
        if brand:
            f = font("semi", 20)
            p["brand_img"] = text_img(brand, f, C["muted"])
            p["brand_pos"] = (cx + 48, cy + ch - 56)
    elif layout == "title":
        d = 210
        p["bubble"] = (W - 96 - d, H - 70 - d, d)
        p["bubble_mask"] = rmask((d, d), d // 2)
        p["bubble_shadow"] = soft_shadow((d, d), d // 2, blur=20)
        p["items"] = build_text(s, 96, 0, H - 40, W - 96 - 330, C["white"],
                                (200, 208, 232), C["accent"], 76, dur,
                                sub_fill=(200, 208, 232))
    elif layout == "presenter":
        pw, ph = 600, 640
        px, py = (W - pw) // 2, 40
        p["panel"] = (px, py, pw, ph, 40)
        p["panel_mask"] = rmask((pw, ph), 40)
        p["panel_shadow"] = soft_shadow((pw, ph), 40)
        lw, lh = 540, 118
        p["lower"] = (px + 30, py + ph - lh - 30, lw, lh)
        p["lower_img"] = rrect((lw, lh), 22, (10, 16, 36, 225))
        title = s.get("title") or name or ""
        sub = s.get("subtitle") or ""
        its = []
        its.append(dict(kind="img", img=text_img(title, font("bold", 34), C["white"]),
                        x=px + 64, y=py + ph - lh - 30 + 20, delay=0.5, extra=None))
        if sub:
            its.append(dict(kind="img", img=text_img(sub, font("reg", 22), (208, 214, 236)),
                            x=px + 64, y=py + ph - lh - 30 + 66, delay=0.7, extra=None))
        p["items"] = its
    elif layout == "image":
        path = s.get("image")
        p["photo"] = None
        if path and os.path.exists(path):
            im = Image.open(path).convert("RGB")
            p["photo"] = fit_cover(im, (int(W * 1.18), int(H * 1.18)), 0.5)
        p["fade"] = bottom_fade()
        d = 190
        p["bubble"] = (W - 64 - d, H - 64 - d, d)
        p["bubble_mask"] = rmask((d, d), d // 2)
        p["bubble_shadow"] = soft_shadow((d, d), d // 2, blur=18)
        p["items"] = build_text(s, 72, 0, H - 56, W - 72 - 330, C["white"],
                                (206, 212, 234), C["accent"], 62, dur,
                                valign="bottom" if p["photo"] is not None else "center",
                                sub_fill=(206, 212, 234))
    return p


# ------------------------------------------------------------ rendering
def circle_ring(size):
    ring = Image.new("RGBA", (size + 12, size + 12), (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse((0, 0, size + 11, size + 11), outline=(255, 255, 255, 255), width=5)
    return ring


def render(p, t, pres, bg):
    lay = p["layout"]
    ox = 320 + int(60 * math.sin(t * 0.35))
    oy = 180 + int(40 * math.cos(t * 0.27))
    if lay == "presenter":
        small = pres.resize((32, 18), Image.BILINEAR).resize((W, H), Image.BICUBIC)
        base = Image.blend(small.convert("RGB"), Image.new("RGB", (W, H), (8, 12, 28)), 0.55)
    elif lay == "image":
        if p.get("photo") is not None:
            ph = p["photo"]
            z = 1 + 0.07 * clamp(t / max(p["dur"], 1))
            cw_, ch_ = int(W * 1.18 / z), int(H * 1.18 / z)
            x = int((ph.width - cw_) / 2 + 30 * math.sin(t * 0.2))
            y = (ph.height - ch_) // 2
            base = ph.crop((x, y, x + cw_, y + ch_)).resize((W, H), Image.BILINEAR)
        else:
            bx = min(ox + 300, bg.width - W)
            base = bg.crop((bx, oy, bx + W, oy + H)).copy()
        base = base.convert("RGB")
        base.paste(p["fade"], (0, 0), p["fade"])
    else:
        base = bg.crop((ox, oy, ox + W, oy + H)).copy()

    t_in = ease_out(t / 0.7)

    def put_panel(key="panel"):
        x, y, w, h, r = p[key]
        sh, pad = p["panel_shadow"]
        paste_rgba(base, sh, x - pad, y - pad, t_in)
        fr = fit_cover(pres, (w, h)).convert("RGBA")
        fr.putalpha(p["panel_mask"])
        paste_rgba(base, fr, x, y + (1 - t_in) * 30, t_in)

    def put_bubble():
        x, y, d = p["bubble"]
        sh, pad = p["bubble_shadow"]
        k = ease_back(t / 0.8)
        paste_rgba(base, sh, x - pad, y - pad, clamp(k))
        fr = fit_cover(pres, (d, d), 0.05).convert("RGBA")
        fr.putalpha(p["bubble_mask"])
        paste_rgba(base, fr, x, y + (1 - clamp(k)) * 40, clamp(k))
        paste_rgba(base, circle_ring(d), x - 6, y - 6 + (1 - clamp(k)) * 40, clamp(k))

    if lay == "split":
        put_panel()
        cx, cy, cw, ch = p["card"]
        dx = (1 - ease_out(t / 0.75)) * 140 * p["dir"]
        a = ease_out(t / 0.5)
        sh, pad = p["card_shadow"]
        paste_rgba(base, sh, cx - pad + dx, cy - pad, a)
        paste_rgba(base, p["card_img"], cx + dx, cy, a)
        draw_items(base, p["items"], t, dx, a)
        if "brand_img" in p:
            bx, by = p["brand_pos"]
            paste_rgba(base, p["brand_img"], bx + dx, by, a)
        if p["name"]:
            f = font("semi", 22)
            tw = int(f.getlength(p["name"]))
            chip = rrect((tw + 56, 46), 23, (10, 16, 36, 215))
            dr = ImageDraw.Draw(chip)
            dr.ellipse((18, 17, 30, 29), fill=(70, 220, 130, 255))
            dr.text((40, 23), p["name"], font=f, fill=(255, 255, 255, 255), anchor="lm")
            px, py, pw, ph, _ = p["panel"]
            paste_rgba(base, chip, px + 22, py + ph - 70, ease_out((t - 0.6) / 0.4))
    elif lay == "title":
        draw_items(base, p["items"], t)
        put_bubble()
    elif lay == "presenter":
        put_panel()
        lx, ly, lw, lh = p["lower"]
        k = ease_out((t - 0.3) / 0.6)
        paste_rgba(base, p["lower_img"], lx - (1 - k) * 80, ly, k)
        ImageDraw.Draw(base).rounded_rectangle(
            (lx + 22 - (1 - k) * 80, ly + 22, lx + 28 - (1 - k) * 80, ly + lh - 22), 3, fill=C["accent"])
        draw_items(base, p["items"], t, 0, 1.0)
    elif lay == "image":
        draw_items(base, p["items"], t)
        put_bubble()
    return base


# ------------------------------------------------------------- video I/O
def _probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height:format=duration",
         "-of", "default=nw=1", path], capture_output=True, text=True).stdout
    d = dict(l.split("=") for l in out.split() if "=" in l)
    return int(d["width"]), int(d["height"]), float(d["duration"])


def make_video(presenter, scenes, out="final.mp4", brand="", name="",
               card_side="right", log=True):
    pw, ph, dur = _probe(presenter)
    rh = 720
    rw = int(round(pw * rh / ph / 2)) * 2
    scenes = sorted(scenes, key=lambda s: s.get("start", 0))
    scenes[0]["start"] = 0
    preps = []
    for i, s in enumerate(scenes):
        end = scenes[i + 1]["start"] if i + 1 < len(scenes) else dur
        preps.append((s["start"], prep(s, end - s["start"], brand, card_side, name)))
    bg = make_bg()
    n = int(dur * FPS)

    rd = subprocess.Popen(
        ["ffmpeg", "-loglevel", "error", "-i", presenter, "-vf",
         f"fps={FPS},scale={rw}:{rh}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        stdout=subprocess.PIPE)
    wr = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", presenter,
         "-map", "0:v", "-map", "1:a?", "-c:v", "libx264", "-preset", "veryfast",
         "-crf", "19", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
         "-shortest", out], stdin=subprocess.PIPE)

    last = Image.new("RGB", (rw, rh), (20, 20, 30))
    XF = 0.3
    for i in range(n):
        t = i / FPS
        raw = rd.stdout.read(rw * rh * 3)
        if len(raw) == rw * rh * 3:
            last = Image.frombytes("RGB", (rw, rh), raw)
        k = 0
        for j, (st, _) in enumerate(preps):
            if t >= st:
                k = j
        st, p = preps[k]
        frame = render(p, t - st, last, bg)
        if k > 0 and t - st < XF:
            pst, pp = preps[k - 1]
            old = render(pp, t - pst, last, bg)
            frame = Image.blend(old, frame, (t - st) / XF)
        ImageDraw.Draw(frame).rectangle((0, H - 5, int(W * t / dur), H), fill=C["accent"])
        wr.stdin.write(frame.convert("RGB").tobytes())
        if log and i % (FPS * 10) == 0:
            print(f"  rendering {t:5.1f}s / {dur:.1f}s")
    wr.stdin.close()
    wr.wait()
    rd.stdout.close()
    rd.wait()
    if log:
        print("Saved:", out)
    return out

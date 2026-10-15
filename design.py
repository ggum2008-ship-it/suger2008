"""쇼츠 카드뉴스 디자인 — 날마다 테마가 바뀌고, 표지에 큰 숫자·질문 후킹, 본문은 강조 형광펜과 천천히 다가오는 움직임.

spec 에서 쓰는 값
  title, subtitle, category, date, source, speed, comment(선택)
  kicker      표지 위쪽 질문 한 줄 (예: "규제했는데 왜?")
  big_number  표지 한가운데 큰 숫자 (예: "10.41%")
  big_label   큰 숫자가 무엇인지 (예: "서울 아파트값 상승률")
  slides[]    heading, body, highlight(본문 속 강조 구절), stat(본문 속 핵심 숫자)
  theme       테마 이름 (없으면 날짜로 자동 선택)
"""
import datetime as dt
import glob
import os
import subprocess
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1920
X0, X1 = 84, 940            # 오른쪽은 쇼츠 버튼(좋아요·댓글)이 덮어서 비워 둔다
TOP, BOTTOM = 230, 1460     # 아래쪽은 제목·설명 글자가 덮어서 비워 둔다


# ───────── 글꼴 ─────────
@lru_cache(None)
def _path(family, weight):
    fam = "Serif" if family == "serif" else "Sans"
    tries = {"Black": ["Black", "Heavy", "Bold"], "Bold": ["Bold", "SemiBold"], "Medium": ["Medium", "Regular"],
             "Regular": ["Regular"], "Light": ["Light", "Regular"]}[weight]
    for w in tries:
        hits = glob.glob(f"/usr/share/fonts/**/Noto{fam}CJK-{w}.ttc", recursive=True)
        if hits:
            return hits[0]
    if family == "serif":
        return _path("sans", weight)
    raise FileNotFoundError("Noto CJK 글꼴이 없습니다 (fonts-noto-cjk 설치 필요)")


def font(family, weight, size):
    return ImageFont.truetype(_path(family, weight), int(size), index=1)


# ───────── 테마 ─────────
THEMES = {
    "미드나잇": dict(bg="gradient", c1="#0B1026", c2="#1E2A5A", ink="#FFFFFF", sub="#AEB8D8", accent="#FFD23F",
                  mark="#FFD23F", mark_ink="#0B1026", head="sans", deco="blobs", blob="#4F6BFF", trans="smoothup"),
    "에디토리얼": dict(bg="paper", c1="#F4EFE6", c2="#E9E1D3", ink="#141414", sub="#5E5A54", accent="#D7263D",
                   mark="#FFE066", mark_ink="#141414", head="serif", deco="rules", blob=None, trans="fade"),
    "팝": dict(bg="solid", c1="#FF5A36", c2="#FF7A45", ink="#FFFFFF", sub="#FFE3D8", accent="#111111",
              mark="#111111", mark_ink="#FFFFFF", head="sans", deco="dots", blob=None, trans="slideleft"),
    "모노그리드": dict(bg="solid", c1="#111111", c2="#1A1A1A", ink="#F5F5F5", sub="#9A9A9A", accent="#C6FF3D",
                  mark="#C6FF3D", mark_ink="#111111", head="sans", deco="grid", blob=None, trans="wipeup"),
    "파스텔": dict(bg="gradient", c1="#FDE2E4", c2="#CDE7F0", ink="#1B1B2F", sub="#5A5A72", accent="#6C4CF1",
                mark="#FFE066", mark_ink="#1B1B2F", head="sans", deco="blobs", blob="#FFFFFF", trans="circleopen"),
    "딥그린": dict(bg="gradient", c1="#06302B", c2="#0E5A4E", ink="#FFFFFF", sub="#B8DCD3", accent="#FFB547",
                mark="#FFB547", mark_ink="#06302B", head="serif", deco="lines", blob="#1FA38A", trans="smoothleft"),
}
THEME_ORDER = list(THEMES)


def pick_theme(spec):
    name = spec.get("theme")
    if name in THEMES:
        return name, THEMES[name]
    try:
        d = dt.date.fromisoformat(spec.get("date", "").replace(".", "-"))
    except ValueError:
        d = dt.date.today()
    name = THEME_ORDER[d.toordinal() % len(THEME_ORDER)]
    return name, THEMES[name]


def rgb(h, a=255):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (a,)


# ───────── 배경 ─────────
def background(t, seed=0):
    if t["bg"] == "gradient":
        g = Image.new("RGB", (1, 256))
        a, b = rgb(t["c1"])[:3], rgb(t["c2"])[:3]
        for y in range(256):
            k = y / 255
            g.putpixel((0, y), tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3)))
        im = g.resize((W, H)).convert("RGBA")
    else:
        im = Image.new("RGBA", (W, H), rgb(t["c1"]))
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    deco = t["deco"]
    if deco == "blobs":
        spots = [(860, 260, 420), (120, 1500, 520), (900, 1700, 300)]
        for i, (x, y, r) in enumerate(spots):
            x += (seed * 97 + i * 53) % 160 - 80
            d.ellipse([x - r, y - r, x + r, y + r], fill=rgb(t["blob"], 90))
        layer = layer.filter(ImageFilter.GaussianBlur(120))
    elif deco == "grid":
        for x in range(0, W, 90):
            d.line([(x, 0), (x, H)], fill=(255, 255, 255, 18), width=1)
        for y in range(0, H, 90):
            d.line([(0, y), (W, y)], fill=(255, 255, 255, 18), width=1)
    elif deco == "dots":
        for y in range(40, H, 60):
            for x in range(40 + (y // 60 % 2) * 30, W, 60):
                d.ellipse([x - 4, y - 4, x + 4, y + 4], fill=(255, 255, 255, 40))
    elif deco == "rules":
        d.rectangle([0, 0, W, 24], fill=rgb(t["ink"]))
        d.line([(X0, 190), (W - X0, 190)], fill=rgb(t["ink"], 255), width=3)
        d.line([(X0, 198), (W - X0, 198)], fill=rgb(t["ink"], 255), width=1)
    elif deco == "lines":
        for i in range(-H, W, 70):
            d.line([(i, H), (i + H, 0)], fill=(255, 255, 255, 14), width=2)
    if t["bg"] == "paper":                      # 종이 질감: 가장자리 살짝 어둡게
        v = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(v).rectangle([0, 0, W, H], outline=(0, 0, 0, 40), width=60)
        layer.alpha_composite(v.filter(ImageFilter.GaussianBlur(60)))
    im.alpha_composite(layer)
    return im


# ───────── 글자 배치 ─────────
def wrap_idx(d, text, f, max_w):
    """줄바꿈하면서 각 줄이 원문 몇 번째 글자에서 시작하는지도 돌려준다 (형광펜 위치 계산용)."""
    lines, start, i, n = [], 0, 0, len(text)
    while start < n:
        end = start
        last_space = -1
        while end < n and d.textlength(text[start:end + 1], font=f) <= max_w:
            if text[end] == " ":
                last_space = end
            end += 1
        if end < n and last_space > start + (end - start) * 0.3:
            end = last_space
        lines.append((start, text[start:end].rstrip()))
        start = end
        while start < n and text[start] == " ":
            start += 1
    return lines


def fit_font(d, text, family, weight, size, max_w, max_lines, min_size=40):
    while size > min_size:
        f = font(family, weight, size)
        if len(wrap_idx(d, text, f, max_w)) <= max_lines:
            return f
        size -= 4
    return font(family, weight, min_size)


def block(d, x, y, text, f, fill, gap, max_w, mark=None, mark_color=None, mark_ink=None):
    """여러 줄 글자를 그리고, mark(강조 구절)가 있으면 형광펜을 칠한다. 마지막 y를 돌려준다."""
    span = None
    if mark and mark in text:
        s = text.index(mark)
        span = (s, s + len(mark))
    lh = f.size + gap
    for start, line in wrap_idx(d, text, f, max_w):
        if span:
            a, b = max(span[0], start), min(span[1], start + len(line))
            if a < b:
                x1 = x + d.textlength(line[:a - start], font=f)
                x2 = x + d.textlength(line[:b - start], font=f)
                d.rounded_rectangle([x1 - 8, y + f.size * 0.18, x2 + 8, y + f.size * 1.18], radius=10, fill=mark_color)
                d.text((x, y), line[:a - start], font=f, fill=fill)
                d.text((x1, y), line[a - start:b - start], font=f, fill=mark_ink)
                d.text((x2, y), line[b - start:], font=f, fill=fill)
                y += lh
                continue
        d.text((x, y), line, font=f, fill=fill)
        y += lh
    return y


def measure(d, text, f, gap, max_w):
    return len(wrap_idx(d, text, f, max_w)) * (f.size + gap)


def header(d, t, spec, idx, total):
    """맨 위: 진행 막대 + 날짜·분야."""
    seg_w = (W - 2 * X0 - (total - 1) * 10) / total
    for i in range(total):
        x = X0 + i * (seg_w + 10)
        col = rgb(t["accent"]) if i < idx else rgb(t["sub"], 90)
        d.rounded_rectangle([x, 120, x + seg_w, 128], radius=4, fill=col)
    d.text((X0, 150), f"오늘의 이슈  ·  {spec.get('category', '')}", font=font("sans", "Bold", 34), fill=rgb(t["accent"]))
    d.text((X1, 150), spec.get("date", ""), font=font("sans", "Medium", 32), fill=rgb(t["sub"]), anchor="ra")


def footer(d, t, spec):
    src = spec.get("source", "")
    if src:
        f = font("sans", "Regular", 26)
        while d.textlength(src, font=f) > X1 - X0 and len(src) > 10:
            src = src[:-2]
        d.text((X0, BOTTOM + 30), src, font=f, fill=rgb(t["sub"]))


# ───────── 카드 ─────────
def cover(spec, t, total):
    im = background(t, 0)
    d = ImageDraw.Draw(im)
    header(d, t, spec, 1, total)
    hf = t["head"]
    kicker = spec.get("kicker") or ""
    big = spec.get("big_number") or ""
    label = spec.get("big_label") or ""
    title = spec.get("title", "")
    kf = font("sans", "Black", 58)
    tf = fit_font(d, title, hf, "Black", 92, X1 - X0, 3)
    bf = None
    if big:
        size = 300
        while size > 120:
            bf = font("sans", "Black", size)
            if d.textlength(big, font=bf) <= X1 - X0:
                break
            size -= 10
    parts = []
    if kicker:
        parts.append(("kicker", measure(d, kicker, kf, 10, X1 - X0) + 30))
    if big:
        bh = d.textbbox((0, 0), big, font=bf, anchor="lt")[3]
        parts.append(("big", bh + (24 + 56 if label else 0) + 50))
    parts.append(("title", measure(d, title, tf, 18, X1 - X0) + 20))
    if spec.get("subtitle"):
        parts.append(("sub", 110))
    y = TOP + max(0, (BOTTOM - TOP - sum(h for _, h in parts)) // 2)
    for kind, h in parts:
        if kind == "kicker":
            w = min(X1 - X0, d.textlength(kicker, font=kf) + 48)
            d.rounded_rectangle([X0 - 6, y - 10, X0 - 6 + w, y + kf.size + 22], radius=16, fill=rgb(t["accent"]))
            d.text((X0 + 18, y), kicker, font=kf, fill=rgb(t["mark_ink"] if t["accent"] == t["mark"] else t["c1"]))
        elif kind == "big":
            d.text((X0 - 6, y), big, font=bf, fill=rgb(t["accent"]), anchor="lt")
            bottom = d.textbbox((X0 - 6, y), big, font=bf, anchor="lt")[3]
            if label:
                d.text((X0, bottom + 24), label, font=font("sans", "Bold", 44), fill=rgb(t["sub"]))
        elif kind == "title":
            block(d, X0, y, title, tf, rgb(t["ink"]), 18, X1 - X0)
        elif kind == "sub":
            d.line([(X0, y + 6), (X0 + 120, y + 6)], fill=rgb(t["accent"]), width=8)
            block(d, X0, y + 34, spec["subtitle"], font("sans", "Medium", 44), rgb(t["sub"]), 12, X1 - X0)
        y += h
    d.text((X0, BOTTOM - 30), "끝까지 보면 답이 나와요  →", font=font("sans", "Bold", 36), fill=rgb(t["ink"], 200))
    footer(d, t, spec)
    return im


def body_card(spec, s, k, t, total):
    im = background(t, k)
    d = ImageDraw.Draw(im)
    header(d, t, spec, k + 1, total)
    heading, text = s.get("heading", ""), s.get("body", "")
    stat = s.get("stat") if s.get("stat") and s.get("stat") in text else ""
    mark = s.get("highlight") if s.get("highlight") and s.get("highlight") in text else ""
    if not mark and stat:
        mark = stat
    nf = font("sans", "Black", 150)
    hf = fit_font(d, heading, t["head"], "Black", 84, X1 - X0, 3)
    bf = fit_font(d, text, "sans", "Medium", 56, X1 - X0, 7, 44)
    sf = None
    if stat:
        size = 200
        while size > 90:
            sf = font("sans", "Black", size)
            if d.textlength(stat, font=sf) <= X1 - X0:
                break
            size -= 10
    total_h = nf.size + 10 + measure(d, heading, hf, 14, X1 - X0) + 50 + (sf.size + 40 if sf else 0) + measure(d, text, bf, 22, X1 - X0)
    y = TOP + max(0, (BOTTOM - TOP - total_h) // 2)
    # 번호: 테두리만 있는 큰 숫자
    num = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    nd = ImageDraw.Draw(num)
    nd.text((X0 - 4, y), f"{k:02d}", font=nf, fill=rgb(t["accent"]), anchor="lt", stroke_width=5, stroke_fill=rgb(t["accent"]))
    nd.text((X0 - 4, y), f"{k:02d}", font=nf, fill=(0, 0, 0, 0), anchor="lt")
    hole = Image.new("L", (W, H), 0)
    ImageDraw.Draw(hole).text((X0 - 4, y), f"{k:02d}", font=nf, fill=255, anchor="lt")
    num.putalpha(Image.composite(Image.new("L", (W, H), 0), num.getchannel("A"), hole))
    im.alpha_composite(num)
    y = d.textbbox((X0 - 4, y), f"{k:02d}", font=nf, anchor="lt")[3] + 24
    y = block(d, X0, y, heading, hf, rgb(t["ink"]), 14, X1 - X0) + 30
    d.line([(X0, y), (X0 + 90, y)], fill=rgb(t["accent"]), width=8)
    y += 40
    if sf:
        d.text((X0 - 4, y), stat, font=sf, fill=rgb(t["accent"]), anchor="lt")
        y = d.textbbox((X0 - 4, y), stat, font=sf, anchor="lt")[3] + 36
    block(d, X0, y, text, bf, rgb(t["ink"]), 22, X1 - X0, mark, rgb(t["mark"]), rgb(t["mark_ink"]))
    footer(d, t, spec)
    return im


def outro(spec, t, total):
    im = background(t, 9)
    d = ImageDraw.Draw(im)
    header(d, t, spec, total, total)
    y = TOP + 260
    if spec.get("comment"):
        d.text((X0, y), "운영자 한마디", font=font("sans", "Bold", 40), fill=rgb(t["accent"]))
        y = block(d, X0, y + 70, spec["comment"], font("sans", "Medium", 52), rgb(t["ink"]), 16, X1 - X0) + 80
    q = spec.get("outro_question") or "여러분 생각은 어떤가요?"
    y = block(d, X0, y, q, fit_font(d, q, t["head"], "Black", 96, X1 - X0, 3), rgb(t["ink"]), 20, X1 - X0) + 50
    d.text((X0, y), "댓글로 의견을 남겨주세요", font=font("sans", "Bold", 52), fill=rgb(t["accent"]))
    y += 140
    # 구독 버튼 모양
    bw, bh = 360, 110
    d.rounded_rectangle([X0, y, X0 + bw, y + bh], radius=55, fill=rgb("#FF0033"))
    d.text((X0 + bw / 2, y + bh / 2), "구독", font=font("sans", "Black", 54), fill=(255, 255, 255, 255), anchor="mm")
    d.text((X0 + bw + 40, y + bh / 2), "매일 아침 새 이슈", font=font("sans", "Bold", 44), fill=rgb(t["sub"]), anchor="lm")
    footer(d, t, spec)
    return im


# ───────── 영상 ─────────
def render(spec, out, sec):
    """카드 이미지와 shorts.mp4, preview.png 를 만든다. 테마 이름을 돌려준다."""
    name, t = pick_theme(spec)
    slides = spec["slides"]
    total = len(slides) + 2
    cards = [cover(spec, t, total)] + [body_card(spec, s, k, t, total) for k, s in enumerate(slides, 1)] + [outro(spec, t, total)]
    paths = []
    for i, im in enumerate(cards, 1):
        p = os.path.join(out, f"card_{i:02d}.png")
        im.convert("RGB").save(p)
        paths.append(p)
    durs = [sec(3, spec)] + [sec(6, spec)] * len(slides) + [sec(4, spec)]
    fps, fade = 30, 0.5
    args = ["ffmpeg", "-y", "-loglevel", "error"]
    for p in paths:
        args += ["-i", p]
    chains = []
    for i, dur in enumerate(durs):            # 카드마다 천천히 다가오는 움직임 (켄 번스)
        n = int(dur * fps)
        chains.append(f"[{i}:v]scale=1620:-1,zoompan=z='1+0.035*on/{n}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                      f":d={n}:s={W}x{H}:fps={fps},setsar=1,format=yuv420p[c{i}]")
    prev, off = "[c0]", 0.0
    for i in range(1, len(paths)):
        off += durs[i - 1] - fade
        chains.append(f"{prev}[c{i}]xfade=transition={t['trans']}:duration={fade}:offset={off:.2f}[v{i}]")
        prev = f"[v{i}]"
    args += ["-filter_complex", ";".join(chains), "-map", prev, "-r", str(fps), "-c:v", "libx264",
             "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", os.path.join(out, "shorts.mp4")]
    subprocess.run(args, check=True)
    prev_im = Image.new("RGB", (370 * len(paths) - 10, 640), "white")
    for i, p in enumerate(paths):
        prev_im.paste(Image.open(p).resize((360, 640)), (i * 370, 0))
    prev_im.save(os.path.join(out, "preview.png"))
    return name, sum(durs) - fade * (len(durs) - 1)

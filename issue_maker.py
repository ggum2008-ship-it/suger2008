#!/usr/bin/env python3
"""오늘의 이슈 영상 생성기 (쇼츠 + 주간 정리)
  python3 issue_maker.py shorts spec.json 출력폴더   → 세로 카드뉴스 6장 + shorts.mp4 + youtube_upload.txt
  python3 issue_maker.py weekly spec.json 출력폴더   → 가로 영상 약 5분 weekly.mp4 + thumbnail.png + youtube_upload.txt
필요: Pillow, ffmpeg, Noto Sans CJK 글꼴
"""
import json, os, subprocess, sys
from PIL import Image, ImageDraw, ImageFont

import glob
from functools import lru_cache

@lru_cache(None)
def _font_path(weight):
    """설치된 Noto Sans CJK 글꼴을 찾는다. 원하는 굵기가 없으면 비슷한 굵기로 대신한다."""
    fallback = {"Black": ["Black", "Bold"], "Bold": ["Bold"], "Medium": ["Medium", "Regular"],
                "Regular": ["Regular"]}.get(weight, [weight, "Regular"])
    for w in fallback:
        hits = glob.glob(f"/usr/share/fonts/**/NotoSansCJK-{w}.ttc", recursive=True)
        if hits:
            return hits[0]
    raise FileNotFoundError("Noto Sans CJK 글꼴이 없습니다. fonts-noto-cjk 를 설치하세요.")

def F(weight, size):
    return ImageFont.truetype(_font_path(weight), size, index=1)  # index 1 = 한국어

PALETTE = {"사회·시사": "#E4572E", "교육": "#2E86AB", "AI·IT": "#7B2CBF", "생활·경제": "#F18F01", "기타": "#3D5A80"}
BG, INK, SUB, MAIN, DOT = "#F7F5F0", "#1B1B1B", "#5C5C5C", "#3D5A80", "#D9D5CC"
color = lambda cat: PALETTE.get(cat, PALETTE["기타"])
SPEED = {"느리게": 1.3, "보통": 1.0, "빠르게": 0.75}   # 카드가 화면에 머무는 시간 배율
def sec(base, spec):
    return max(2.5, round(base * SPEED.get(spec.get("speed", "보통"), 1.0) * 2) / 2)

def wrap(d, text, font, max_w):
    lines = []
    for para in text.split("\n"):
        cur = ""
        for ch in para:
            if d.textlength(cur + ch, font=font) <= max_w:
                cur += ch
            else:
                cut = cur.rfind(" ")
                if cut > len(cur) * 0.6:
                    lines.append(cur[:cut]); cur = cur[cut + 1:] + ch
                else:
                    lines.append(cur); cur = ch
        lines.append(cur)
    return lines

def fit(d, text, font, max_w):
    """한 줄에 안 들어가면 말줄임"""
    if d.textlength(text, font=font) <= max_w:
        return text
    while text and d.textlength(text + "…", font=font) > max_w:
        text = text[:-1]
    return text.rstrip() + "…"

def lines_at(d, x, y, lines, font, fill, gap):
    for ln in lines:
        d.text((x, y), ln, font=font, fill=fill); y += font.size + gap
    return y

def mmss(sec):
    return f"{int(sec) // 60}:{int(sec) % 60:02d}"

# ───────────── 업로드 글 (제목 후보·설명·고정 댓글) ─────────────
def write_upload(spec, out, kind, chapters=None):
    titles = spec.get("yt_titles") or [spec.get("title", "")]
    tag = " #shorts" if kind == "shorts" else ""
    if kind == "shorts":
        points = [f"· {s['heading']}" for s in spec.get("slides", [])]
        sources = [spec.get("source", "")]
    else:
        points = [f"{i}. {it['title']}" for i, it in enumerate(spec.get("issues", []), 1)]
        sources = [it.get("source", "") for it in spec.get("issues", [])]
    desc = [spec.get("yt_hook", ""), "", "✍️ 운영자 한마디: (여기에 내 생각 한 줄을 적어 주세요)", "",
            "📌 핵심 정리" if kind == "shorts" else "📌 이번 주 다룬 이슈"] + points
    if chapters:
        desc += ["", "⏱ 목차"] + [f"{a} {b}" for a, b in chapters]
    desc += ["", "📰 출처"] + [s.replace("출처: ", "") for s in sources if s]
    desc += ["", "이 영상은 AI로 자료를 정리하고 운영자가 사실을 확인한 뒤 올립니다.",
             "매일 아침 1분 이슈 쇼츠, 주말에는 주간 정리 영상이 올라옵니다.", "",
             " ".join(spec.get("hashtags", []))]
    with open(os.path.join(out, "youtube_upload.txt"), "w", encoding="utf-8") as f:
        f.write("━━━━ ① 제목 (하나만 골라 복사) ━━━━\n")
        for i, t in enumerate(titles, 1):
            f.write(f"{'추천' if i == 1 else '후보'} {i}: {t}{tag}\n")
        f.write("\n━━━━ ② 설명 (아래 전부 복사) ━━━━\n" + "\n".join(desc).strip() + "\n")
        if spec.get("pinned_comment"):
            f.write("\n━━━━ ③ 고정 댓글 (올린 뒤 내 댓글로 달고 '고정') ━━━━\n" + spec["pinned_comment"] + "\n")

# ───────────── 쇼츠 (세로 1080×1920) ─────────────
SW, SH = 1080, 1920

def s_frame(c, idx, total, spec):
    im = Image.new("RGB", (SW, SH), BG); d = ImageDraw.Draw(im)
    d.rectangle([0, 0, SW, 18], fill=c)
    d.text((80, 90), f"{spec['date']} · {spec['category']}", font=F("Medium", 34), fill=c)
    d.text((SW - 80, 90), f"{idx}/{total}", font=F("Medium", 34), fill=SUB, anchor="ra")
    d.text((80, SH - 140), spec.get("source", ""), font=F("Regular", 28), fill=SUB)
    return im, d

def shorts(spec, out):
    c = color(spec.get("category")); n = len(spec["slides"]); total = n + 2
    imgs = []
    im, d = s_frame(c, 1, total, spec)
    d.text((80, 520), "오늘의 이슈", font=F("Bold", 44), fill=c)
    y = lines_at(d, 80, 600, wrap(d, spec["title"], F("Black", 96), SW - 160), F("Black", 96), INK, 22)
    d.rectangle([80, y + 40, 220, y + 52], fill=c)
    lines_at(d, 80, y + 100, wrap(d, spec.get("subtitle", ""), F("Medium", 46), SW - 160), F("Medium", 46), SUB, 18)
    imgs.append(im)
    for i, s in enumerate(spec["slides"], 2):
        im, d = s_frame(c, i, total, spec)
        d.text((80, 420), f"{i - 1:02d}", font=F("Black", 120), fill=c)
        y = lines_at(d, 80, 600, wrap(d, s["heading"], F("Bold", 72), SW - 160), F("Bold", 72), INK, 18)
        lines_at(d, 80, y + 70, wrap(d, s["body"], F("Regular", 50), SW - 160), F("Regular", 50), INK, 30)
        imgs.append(im)
    im, d = s_frame(c, total, total, spec)
    y = 700
    if spec.get("comment"):
        d.text((80, 520), "운영자 한마디", font=F("Bold", 44), fill=c)
        y = lines_at(d, 80, 600, wrap(d, spec["comment"], F("Medium", 52), SW - 160), F("Medium", 52), INK, 20) + 120
    y = lines_at(d, 80, y, ["오늘의 이슈,", "어떻게 보셨나요?"], F("Black", 88), INK, 24)
    d.text((80, y + 40), "댓글로 의견을 남겨주세요", font=F("Medium", 48), fill=c)
    d.text((80, y + 120), "구독하고 매일 이슈를 받아보세요", font=F("Regular", 44), fill=SUB)
    imgs.append(im)

    paths = []
    for i, im in enumerate(imgs, 1):
        p = os.path.join(out, f"card_{i:02d}.png"); im.save(p); paths.append(p)
    durs = [sec(3, spec)] + [sec(6, spec)] * n + [sec(4, spec)]
    args = ["ffmpeg", "-y", "-loglevel", "error"]
    for p, t in zip(paths, durs):
        args += ["-loop", "1", "-t", str(t), "-i", p]
    fade, chain, off, prev = 0.5, [], 0, "[0:v]"
    for i in range(1, len(paths)):
        off += durs[i - 1] - fade; tag = f"[v{i}]"
        chain.append(f"{prev}[{i}:v]xfade=transition=slideleft:duration={fade}:offset={off}{tag}"); prev = tag
    args += ["-filter_complex", ";".join(chain), "-map", prev, "-r", "30",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", os.path.join(out, "shorts.mp4")]
    subprocess.run(args, check=True)
    prev_im = Image.new("RGB", (370 * len(paths) - 10, 640), "white")
    for i, p in enumerate(paths):
        prev_im.paste(Image.open(p).resize((360, 640)), (i * 370, 0))
    prev_im.save(os.path.join(out, "preview.png"))
    write_upload(spec, out, "shorts")
    print("완료:", out)

# ───────────── 주간 정리 (가로 1920×1080, 약 5분) ─────────────
WW, WH = 1920, 1080

def w_base(c, spec, label=""):
    im = Image.new("RGB", (WW, WH), BG); d = ImageDraw.Draw(im)
    d.rectangle([0, 0, WW, 14], fill=c)
    d.text((120, 70), f"주간 이슈 정리 · {spec['week']}", font=F("Medium", 34), fill=c)
    if label:
        d.text((WW - 120, 70), label, font=F("Medium", 34), fill=SUB, anchor="ra")
    return im, d

def weekly(spec, out):
    issues = spec["issues"]; total = len(issues); frames = []
    T_COVER, T_TOC, T_ISSUE, T_POINT, T_OUTRO = (sec(b, spec) for b in (6, 10, 5, 10, 8))
    # 표지 (썸네일 겸용)
    im, d = w_base(MAIN, spec)
    d.text((120, 300), spec["range"], font=F("Medium", 48), fill=MAIN)
    lines_at(d, 120, 380, wrap(d, spec.get("cover_title", f"{spec['week']} 이슈 한 번에 정리"), F("Black", 130), WW - 240), F("Black", 130), INK, 30)
    d.text((120, 820), f"이번 주 꼭 알아야 할 소식 {total}가지", font=F("Regular", 50), fill=SUB)
    frames.append((im, T_COVER))
    # 목차
    im, d = w_base(MAIN, spec, "오늘 다룰 이야기")
    y, gap = 200, min(110, 720 // total)
    for i, it in enumerate(issues, 1):
        c = color(it["category"])
        d.text((120, y), f"{i:02d}", font=F("Black", 60), fill=c)
        d.text((260, y + 6), fit(d, it["title"], F("Bold", 52), WW - 260 - 120 - 260), font=F("Bold", 52), fill=INK)
        d.text((WW - 120, y + 16), it["category"], font=F("Medium", 36), fill=c, anchor="ra")
        y += gap
    frames.append((im, T_TOC))
    chapters, t = [("0:00", "오프닝"), (mmss(T_COVER), "이번 주 목차")], T_COVER + T_TOC
    for n, it in enumerate(issues, 1):
        c = color(it["category"]); label = f"{n} / {total}"
        chapters.append((mmss(t), f"{n}. {it['title']}"))
        im, d = w_base(c, spec, label)
        d.text((120, 300), f"{n:02d}", font=F("Black", 200), fill=c)
        d.text((420, 340), it["category"], font=F("Bold", 56), fill=c)
        lines_at(d, 120, 560, wrap(d, it["title"], F("Black", 96), WW - 240), F("Black", 96), INK, 24)
        d.text((120, WH - 110), it.get("source", ""), font=F("Regular", 30), fill=SUB)
        frames.append((im, T_ISSUE)); t += T_ISSUE
        for k, pt in enumerate(it["points"]):
            im, d = w_base(c, spec, label)
            d.text((120, 170), fit(d, it["title"], F("Bold", 46), WW - 240), font=F("Bold", 46), fill=SUB)
            for j in range(len(it["points"])):
                x = 120 + j * 44
                d.ellipse([x, 260, x + 22, 282], fill=c if j <= k else DOT)
            lines_at(d, 120, 400, wrap(d, pt, F("Bold", 76), WW - 240), F("Bold", 76), INK, 34)
            d.text((120, WH - 110), it.get("source", ""), font=F("Regular", 30), fill=SUB)
            frames.append((im, T_POINT)); t += T_POINT
    chapters.append((mmss(t), "마무리"))
    im, d = w_base(MAIN, spec)
    y = 300
    if spec.get("comment"):
        d.text((120, y), "운영자 한마디", font=F("Bold", 44), fill=MAIN)
        y = lines_at(d, 120, y + 80, wrap(d, spec["comment"], F("Medium", 60), WW - 240), F("Medium", 60), INK, 24) + 80
    d.text((120, y), "다음 주에 또 만나요", font=F("Black", 96), fill=INK)
    d.text((120, y + 150), "구독하면 매일 아침 1분 이슈 쇼츠도 받아볼 수 있어요", font=F("Regular", 46), fill=SUB)
    frames.append((im, T_OUTRO)); t += T_OUTRO

    lst = os.path.join(out, "frames.txt")
    with open(lst, "w") as f:
        for i, (im, dur) in enumerate(frames, 1):
            p = os.path.abspath(os.path.join(out, f"frame_{i:03d}.png")); im.save(p)
            f.write(f"file '{p}'\nduration {dur}\n")
        f.write(f"file '{p}'\n")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst,
                    "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-tune", "stillimage",
                    os.path.join(out, "weekly.mp4")], check=True)
    frames[0][0].resize((1280, 720)).save(os.path.join(out, "thumbnail.png"))
    picks = [0, 1, 2, 3, len(frames) - 1]
    grid = Image.new("RGB", (1300, 375 * 3), "white")
    for i, k in enumerate(picks):
        grid.paste(frames[k][0].resize((640, 360)), ((i % 2) * 660, (i // 2) * 375))
    grid.save(os.path.join(out, "preview.png"))
    write_upload(spec, out, "weekly", chapters)
    print(f"완료: {out} (길이 {mmss(t)})")

if __name__ == "__main__":
    mode, spec_path, out = sys.argv[1], sys.argv[2], sys.argv[3]
    spec = json.load(open(spec_path, encoding="utf-8")); os.makedirs(out, exist_ok=True)
    {"shorts": shorts, "weekly": weekly}[mode](spec, out)

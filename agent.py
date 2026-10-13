#!/usr/bin/env python3
"""오늘의 이슈 에이전트
  python3 agent.py daily    → 오늘의 이슈 쇼츠를 만들어 Gmail로 보낸다
  python3 agent.py weekly   → 지난주 이슈 6개 주간 영상을 만들어 Gmail로 보낸다

필요한 비밀값(환경변수)
  ANTHROPIC_API_KEY   Claude API 키
  GMAIL_ADDRESS       보내는(받는) Gmail 주소
  GMAIL_APP_PASSWORD  Gmail 앱 비밀번호 16자리
시험 모드: USE_SAMPLE=1 이면 API를 부르지 않고 sample/ 의 예시 원고로 영상을 만들어 메일로 보낸다.
          (DRY_RUN=1 을 함께 주면 메일도 보내지 않고 out/mail_preview.eml 로 저장한다.)
"""
import datetime as dt
import json, os, re, smtplib, sys, traceback
from email.message import EmailMessage
from pathlib import Path

import issue_maker

ROOT = Path(__file__).resolve().parent
KST = dt.timezone(dt.timedelta(hours=9))
DAYS = "월화수목금토일"
CATEGORIES = ["사회·시사", "교육", "AI·IT", "생활·경제"]
DRY_RUN = os.environ.get("DRY_RUN") == "1"          # 메일을 보내지 않고 파일로 저장
USE_SAMPLE = DRY_RUN or os.environ.get("USE_SAMPLE") == "1"   # API 대신 예시 원고 사용


# ───────────────────────── 기록 ─────────────────────────
def load_json(name, default):
    p = ROOT / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default

def save_history(history, entry):
    history.append(entry)
    (ROOT / "history.json").write_text(json.dumps(history[-60:], ensure_ascii=False, indent=1), encoding="utf-8")


# ───────────────────────── 지시문 ─────────────────────────
COMMON_RULES = """
[정확성 규칙 — 가장 중요]
- web_search로 기사를 찾고, 쓰는 모든 수치·날짜·기관명은 서로 다른 언론사·기관 2곳 이상에서 확인된 것만 쓴다.
- 확인되지 않은 수치는 쓰지 않는다. 추측을 사실처럼 쓰지 않는다.
- 검색 결과가 영어로 나오면 한국어 키워드, korea.kr, 연합뉴스, 주요 일간지, 분야 전문지로 다시 찾는다.
- 다루지 않는 주제: 특정 정당·정치인 평가, 진행 중인 형사사건의 개인 신상, 자살·자해, 확인 안 된 루머, 연예인 사생활.

[문장 규칙]
- 기사체 '~다'로 쓴다. 기사 문장을 그대로 베끼지 말고 새로 쓴다. 같은 어미와 문장 구조를 반복하지 않는다.

[눈길 끄는 제목 규칙]
- yt_titles는 3개, 서로 다른 기법으로 쓴다: 가장 놀라운 숫자를 맨 앞에 / 영향받는 사람을 밝힘 / 대비(A는 줄고 B는 늘었다) / 시청자가 궁금해할 짧은 물음 / 날짜·기한 / 개수 제시.
- 금지: 영상에 답이 없는 약속('이유', '방법'을 실제로 설명하지 않으면 쓰지 않음), '충격', '경악', '실화', '역대급', '난리', 사실보다 부풀린 표현, 특정인 비방.
- 제목의 숫자와 표현은 모두 원고와 일치해야 한다.
- yt_hook: 검색될 핵심 낱말 2~3개가 자연스럽게 들어간 2문장. 첫 문장에 가장 중요한 사실.
- pinned_comment: 누구나 번호로 쉽게 답할 수 있는 질문 하나 (예: ① … ② …).
- hashtags: 모두 합쳐 5개 이내.

[출력 형식]
조사를 마치면, 마지막 답변에 아래 JSON 하나만 <json>와 </json> 사이에 넣어 출력한다. JSON 밖에는 아무것도 쓰지 않는다.
"""

DAILY_FORMAT = """{"category":"%s","title":"표지 제목 28자 이내","subtitle":"부제 30자 이내",
"slides":[{"heading":"소제목 16자 이내","body":"본문 2~3문장 %d자 이내"}, … 4개],
"source":"출처: 기관·언론사명(발표 연월)",
"source_urls":["실제로 확인한 기사 주소", "두 번째 기사 주소"],
"yt_titles":["추천 제목 35자 이내","후보 2","후보 3"],
"yt_hook":"…","pinned_comment":"…","hashtags":["#오늘의이슈","#카드뉴스","…"]}
slides 4장 순서: ①핵심 사실 ②배경·수치 ③쟁점 또는 영향 ④시청자가 생각해볼 점."""

WEEKLY_FORMAT = """{"week":"%s","range":"%s","cover_title":"썸네일 큰 글씨 18자 이내",
"issues":[{"category":"교육","title":"이슈 제목 26자 이내","points":["핵심1","핵심2","핵심3","핵심4"],
"source":"출처: 기관·언론사명(발표 연월)","source_urls":["기사 주소1","기사 주소2"]}, … 6개],
"yt_titles":["추천 제목 40자 이내","후보 2","후보 3"],"yt_hook":"…","pinned_comment":"…","hashtags":["#주간이슈","#이슈정리","…"]}
- 이슈마다 points 4개, 각 1~2문장 %d자 이내. 순서: ①무슨 일 ②핵심 숫자·배경 ③누구에게 어떤 영향 ④앞으로 지켜볼 점.
- 분야는 %s 중에서 고르고, 한 분야가 3개를 넘지 않게 한다."""


def daily_prompt(now, settings, history):
    cat = settings["요일별_분야"][DAYS[now.weekday()]]
    recent = [h["title"] for h in history if h.get("mode") == "daily"][-14:]
    fast = settings.get("쇼츠_재생속도") == "빠르게"
    return f"""오늘은 {now:%Y년 %m월 %d일}({DAYS[now.weekday()]}) 한국 시간 아침이다.
유튜브 쇼츠용 카드뉴스 원고를 만든다. 오늘의 분야는 '{cat}'이다.
최근 24~48시간 사이에 나온 한국 국내 '{cat}' 이슈 중 많은 사람에게 영향을 주는 것 1건을 고른다.
(다른 분야에 훨씬 큰 국내 이슈가 있으면 그 분야로 바꿔도 되며, category는 {CATEGORIES} 중 하나로 쓴다.)
48시간 안에 마땅한 이슈가 없으면 1주일 이내로 넓힌다.
최근에 이미 다룬 이슈(겹치지 않게 피할 것): {recent if recent else '없음'}
{COMMON_RULES}
{DAILY_FORMAT % (cat, 80 if fast else 110)}"""


def weekly_prompt(now, settings, history):
    start = (now - dt.timedelta(days=6)).date()
    end = (now - dt.timedelta(days=1)).date()
    week_no = (end.day - 1) // 7 + 1
    week = f"{end.month}월 {['첫째','둘째','셋째','넷째','다섯째'][week_no-1]} 주"
    rng = f"{start:%Y.%-m.%-d} ~ {end:%-m.%-d}"
    this_week = [f"{h['date']} {h['category']}: {h['title']}" for h in history
                 if h.get("mode") == "daily" and h["date"] >= str(start)]
    fast = settings.get("주간영상_재생속도") == "빠르게"
    return f"""오늘은 {now:%Y년 %m월 %d일} 일요일 한국 시간 아침이다.
지난 한 주({start} ~ {end})의 한국 국내 주요 이슈 6개를 골라 약 5분짜리 주간 정리 영상 원고를 만든다.
이번 주 매일 쇼츠로 다룬 이슈(우선 후보로 쓰되, 최신 기사로 다시 확인할 것): {this_week if this_week else '기록 없음'}
{COMMON_RULES}
{WEEKLY_FORMAT % (week, rng, 45 if fast else 60, CATEGORIES)}"""


VERIFY_PROMPT = """너는 깐깐한 사실 확인 담당 편집자다. 아래 원고(JSON)는 유튜브에 그대로 나갈 내용이다.
web_search로 기사 원문을 다시 찾아, 원고의 문장 하나하나(제목·부제·본문·yt_titles·yt_hook 포함)를 확인한다.
- 수치·날짜·기관명·사람 이름·발언은 기사 2곳 이상에서 확인되면 그대로 둔다.
- 따옴표로 옮긴 발언은 기사에 실린 표현과 같아야 한다. 다르면 기사 표현으로 고치거나 따옴표를 뺀다.
- 기사에서 확인되지 않는 내용은 확인된 사실로 바꾸거나 지운다. 지워서 문장이 짧아지면 확인된 다른 사실로 채운다.
- 기관의 입장을 부풀리지 않는다 (예: '여러 방안을 검토'를 '전환을 결정'처럼 바꾸지 않는다).
- 형식과 글자 수 제한은 원래 규칙을 그대로 지킨다. source_urls에는 실제로 확인한 기사 주소를 넣는다.
- 마지막에 같은 형식의 JSON 하나만 <json></json> 사이에 출력하고, JSON 안에 "fact_notes" 항목으로 고친 점을 짧은 문장 목록으로 적는다 (고친 것이 없으면 빈 목록).

[원고]
"""


# ───────────────────────── Claude API ─────────────────────────
def ask_claude(prompt, model, max_searches):
    import anthropic
    key = "".join(os.environ.get("ANTHROPIC_API_KEY", "").split())   # 붙여넣을 때 섞인 빈칸·줄바꿈 제거
    if not key.startswith("sk-ant-"):
        raise RuntimeError("ANTHROPIC_API_KEY가 'sk-ant-'로 시작하지 않습니다. 키를 다시 확인하세요.")
    client = anthropic.Anthropic(api_key=key, timeout=900, max_retries=4)
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": max_searches,
              "user_location": {"type": "approximate", "city": "Seoul", "country": "KR", "timezone": "Asia/Seoul"}}]
    messages = [{"role": "user", "content": prompt}]
    cited = []
    for attempt in range(3):              # JSON이 잘못되면 최대 2번 다시 요청
        for _ in range(8):                # 긴 검색은 pause_turn으로 나뉘어 올 수 있다
            with client.messages.stream(model=model, max_tokens=8000, tools=tools, messages=messages) as st:
                resp = st.get_final_message()     # 스트리밍: 검색이 길어져도 연결이 끊기지 않게
            messages.append({"role": "assistant", "content": resp.content})
            if resp.stop_reason != "pause_turn":   # 멈춘 경우 받은 응답을 그대로 붙여 다시 보내면 이어서 한다
                break
        text = ""
        for block in resp.content:
            if block.type == "text":
                text += block.text
                for c in getattr(block, "citations", None) or []:
                    url = getattr(c, "url", None)
                    if url and url not in cited:
                        cited.append(url)
        try:
            return parse_json(text), cited
        except ValueError as e:
            messages.append({"role": "user", "content": f"출력에 문제가 있다: {e}\n같은 내용을 규칙에 맞게 고쳐 <json></json> 안에 JSON 하나만 다시 출력하라."})
    raise RuntimeError("Claude가 올바른 원고(JSON)를 만들지 못했습니다.")


def parse_json(text):
    m = re.search(r"<json>(.*?)</json>", text, re.S)
    raw = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON 형식 오류 ({e})")


def check(spec, mode):
    """원고가 영상으로 만들 수 있는 모양인지 확인한다. 문제가 있으면 ValueError."""
    need = ["yt_titles", "yt_hook", "pinned_comment", "hashtags"]
    need += ["category", "title", "slides", "source"] if mode == "daily" else ["week", "range", "cover_title", "issues"]
    miss = [k for k in need if not spec.get(k)]
    if miss:
        raise ValueError(f"빠진 항목: {miss}")
    if len(spec["yt_titles"]) < 3:
        raise ValueError("yt_titles는 3개여야 한다")
    if mode == "daily":
        if spec["category"] not in CATEGORIES:
            raise ValueError(f"category는 {CATEGORIES} 중 하나여야 한다")
        if len(spec["slides"]) != 4:
            raise ValueError("slides는 4개여야 한다")
        for s in spec["slides"]:
            if len(s.get("body", "")) > 140 or len(s.get("heading", "")) > 22:
                raise ValueError(f"슬라이드 글이 너무 길다: {s.get('heading')}")
    else:
        if len(spec["issues"]) != 6:
            raise ValueError("issues는 6개여야 한다")
        for it in spec["issues"]:
            if len(it.get("points", [])) != 4:
                raise ValueError(f"'{it.get('title')}'의 points는 4개여야 한다")
            if any(len(p) > 80 for p in it["points"]):
                raise ValueError(f"'{it.get('title')}'의 point가 너무 길다")


# ───────────────────────── Gmail ─────────────────────────
def send_mail(subject, body, files, settings):
    sender = os.environ.get("GMAIL_ADDRESS", "").strip()
    to = [sender] + settings.get("추가로_받을_메일", [])
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, sender, ", ".join(t for t in to if t)
    msg.set_content(body)
    types = {".mp4": ("video", "mp4"), ".png": ("image", "png"), ".txt": ("text", "plain")}
    for f in files:
        f = Path(f)
        main, sub = types.get(f.suffix, ("application", "octet-stream"))
        msg.add_attachment(f.read_bytes(), maintype=main, subtype=sub, filename=f.name)
    if DRY_RUN:
        out = ROOT / "out" / "mail_preview.eml"
        out.write_bytes(bytes(msg))
        print("시험 모드: 메일을 보내지 않고 저장했습니다 →", out)
        return
    password = "".join(os.environ.get("GMAIL_APP_PASSWORD", "").split())
    missing = [n for n in ("ANTHROPIC_API_KEY", "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD") if not os.environ.get(n)]
    if not sender or not password:
        raise RuntimeError(f"비어 있는 비밀값: {missing}")
    errors = []
    for port in (465, 587):                      # 한쪽 길이 막히면 다른 길로 다시 시도
        stage = "연결"
        try:
            if port == 465:
                s = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=60)
            else:
                s = smtplib.SMTP("smtp.gmail.com", 587, timeout=60)
                s.ehlo(); s.starttls(); s.ehlo()
            with s:
                stage = "로그인"
                s.login(sender, password)
                stage = "보내기"
                s.send_message(msg)
            print("메일 보냄 →", msg["To"])
            return
        except smtplib.SMTPAuthenticationError as e:
            raise RuntimeError(f"Gmail 로그인 거절: 앱 비밀번호 또는 주소를 확인하세요 ({e.smtp_code})")
        except (smtplib.SMTPException, OSError) as e:
            errors.append(f"{port}번 {stage} 단계: {type(e).__name__} {e}")
    raise RuntimeError("메일 보내기 실패 — " + " / ".join(errors))


def mail_body(spec, upload_txt, urls, mode, length):
    guide = ("[올리는 법]\n1. 첨부한 영상을 휴대폰에 저장\n2. 유튜브 앱 '+' → 영상 선택\n"
             "3. 아래 ① 제목 하나, ② 설명 전체를 복사해 붙여넣기 (설명의 '운영자 한마디' 칸에 내 생각 한 줄 쓰기)\n")
    guide += "4. 썸네일 수정에서 첨부한 thumbnail.png 선택\n5. 공개로 올리기\n6. 올린 뒤 ③을 댓글로 달고 '고정'\n" if mode == "weekly" \
        else "4. 공개로 올리기\n5. 올린 뒤 ③을 댓글로 달고 '고정'\n"
    check_txt = "\n[올리기 전 확인]\n· 영상에서 틀린 글자가 없는지\n· 아래 기사 링크 하나를 열어 숫자가 같은지\n"
    notes = spec.get("fact_notes") or []
    if notes:
        check_txt += "\n[사실 확인 중 고친 점]\n" + "\n".join(f"· {n}" for n in notes) + "\n"
    src = "\n[참고한 기사]\n" + "\n".join(f"· {u}" for u in urls) + "\n" if urls else ""
    return f"영상 길이 {length} · 재생 속도 {spec.get('speed', '보통')}\n\n{guide}{check_txt}{src}\n\n{upload_txt}"


# ───────────────────────── 실행 ─────────────────────────
def run(mode):
    settings = load_json("settings.json", {})
    history = load_json("history.json", [])
    now = dt.datetime.now(KST)
    out = ROOT / "out"
    out.mkdir(exist_ok=True)

    if USE_SAMPLE:
        spec = load_json(f"sample/{mode}.json", None)
        urls = spec.get("source_urls", [])
    else:
        prompt = daily_prompt(now, settings, history) if mode == "daily" else weekly_prompt(now, settings, history)
        for attempt in range(2):
            spec, cited = ask_claude(prompt, settings.get("AI_모델", "claude-sonnet-5-5"), 10 if mode == "daily" else 25)
            try:
                check(spec, mode)
                break
            except ValueError as e:
                if attempt:
                    raise
                prompt += f"\n\n(이전 시도에서 '{e}' 문제가 있었다. 이번에는 형식을 정확히 지킨다.)"
        # 사실 재확인: 다른 눈으로 한 번 더 기사와 대조해 확인 안 된 문장을 고친다
        try:
            checked, cited2 = ask_claude(VERIFY_PROMPT + json.dumps(spec, ensure_ascii=False, indent=1),
                                         settings.get("AI_모델", "claude-sonnet-5-5"), 8 if mode == "daily" else 15)
            check(checked, mode)
            spec, cited = checked, cited + cited2
        except Exception as e:
            print("::warning title=사실 재확인 건너뜀::", str(e)[:300])
            spec.setdefault("fact_notes", []).append("사실 재확인 단계를 마치지 못했습니다. 올리기 전에 기사와 꼭 대조해 주세요.")
        urls = list(dict.fromkeys(
            spec.get("source_urls", []) + [u for it in spec.get("issues", []) for u in it.get("source_urls", [])] + cited))[:12]

    if mode == "daily":
        spec["date"] = f"{now:%Y.%m.%d}"
        spec["speed"] = settings.get("쇼츠_재생속도", "보통")
        issue_maker.shorts(spec, str(out))
        video, picture = out / "shorts.mp4", out / "preview.png"
        n = len(spec["slides"])
        secs = issue_maker.sec(3, spec) + issue_maker.sec(6, spec) * n + issue_maker.sec(4, spec) - 0.5 * (n + 1)
        length = f"{secs:.0f}초"
        subject = f"[오늘의 이슈] {now:%m/%d} {spec['yt_titles'][0]}"
        if USE_SAMPLE:
            subject = "[시험] " + subject
        entries = [{"date": f"{now:%Y-%m-%d}", "mode": "daily", "category": spec["category"], "title": spec["title"]}]
    else:
        spec["speed"] = settings.get("주간영상_재생속도", "보통")
        issue_maker.weekly(spec, str(out))
        video, picture = out / "weekly.mp4", out / "thumbnail.png"
        secs = sum(float(x) for x in re.findall(r"duration ([\d.]+)", (out / "frames.txt").read_text()))
        length = f"{int(secs)//60}분 {int(secs)%60}초"
        subject = f"[주간 이슈] {spec['week']} {spec['yt_titles'][0]}"
        if USE_SAMPLE:
            subject = "[시험] " + subject
        entries = [{"date": f"{now:%Y-%m-%d}", "mode": "weekly", "category": "주간", "title": spec["cover_title"]}]

    upload_txt = (out / "youtube_upload.txt").read_text(encoding="utf-8")
    send_mail(subject, mail_body(spec, upload_txt, urls, mode, length),
              [video, picture, out / "youtube_upload.txt"], settings)
    if not USE_SAMPLE:
        for e in entries:
            save_history(history, e)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "daily"
    try:
        run(mode)
    except Exception:
        err = traceback.format_exc()
        print(err)
        last = err.strip().splitlines()[-1].replace("%", "%25").replace("\r", "").replace("\n", " ")
        print(f"::error title=만들기 실패::{last[:400]}")   # GitHub 실행 기록 맨 위에 원인 한 줄을 띄운다
        try:
            send_mail(f"[오늘의 이슈] 만들기 실패 ({mode})",
                      "오늘 영상을 만들지 못했습니다. 아래 내용을 Claude에게 보여 주면 고쳐 줍니다.\n\n" + err[-3000:],
                      [], load_json("settings.json", {}))
        except Exception:
            e2 = traceback.format_exc().strip().splitlines()[-1]
            print("실패 알림 메일도 보내지 못했습니다:", e2)
            print(f"::error title=메일 보내기 실패::{e2[:400]}")
        sys.exit(1)


if __name__ == "__main__":
    main()

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

import factcheck
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
SAFETY = "다루지 않는 주제: 특정 정당·정치인 평가, 진행 중인 형사사건의 개인 신상, 자살·자해, 확인 안 된 루머, 연예인 사생활."

RESEARCH_RULES = """
[취재 규칙 — 반드시 지킨다]
- web_search로 한국 언론사·정부 기관의 기사와 보도자료를 찾는다. 영어 결과가 섞이면 한국어 키워드와 korea.kr, 연합뉴스, 주요 일간지, 분야 전문지로 다시 찾는다.
- 맨 첫 줄에 '선정 이슈: (이슈 한 줄 요약)'을 쓴다.
- 그 아래에 사실을 한 줄에 하나씩 적는다. 모든 줄은 반드시 검색 결과를 인용해야 한다. 인용이 없는 줄은 프로그램이 버린다.
- 숫자·날짜·사람 이름·기관명·발언은 기사에 쓰인 그대로 옮긴다. 계산하거나 반올림하거나 바꿔 말하지 않는다.
- 숫자가 들어간 사실은 서로 다른 언론사 2곳 이상을 함께 인용한다. 한 곳에서만 나온 숫자는 영상에 쓸 수 없다.
- 발언은 기사에 따옴표로 실린 표현만 옮기고, 누가 언제 말했는지 함께 적는다.
- 전망·의견·주장은 '누가' 그렇게 말했는지 붙인다. 기관이 '검토' '논의'한 것을 '결정'처럼 쓰지 않는다.
- 이 단계에서는 원고를 쓰지 않는다. 사실 목록만 적는다.
""" + SAFETY

HOOK_RULES = """
[후킹 원칙 — 끝까지 보고 싶게, 그러나 사실 그대로]
- 궁금증 → 답 → 반전 → 나와의 관계 순서로 짠다.
  · 표지(title): 3초 안에 '왜?' '얼마나?' '나도?'가 떠오르게 한다. 가장 의외인 숫자·대비·변화를 앞에 둔다.
  · subtitle: 궁금증을 반쯤만 풀어 끝까지 보게 한다.
  · 1번 카드: 표지가 던진 궁금증의 핵심 답.
  · 2번 카드: 그 숫자가 왜 중요한지(비교·전과 후·규모).
  · 3번 카드: 사람들이 잘 모르는 의외의 사실이나 반전.
  · 4번 카드: 시청자 생활에 미치는 영향과 생각해 볼 질문.
- 소제목(heading)은 다음 장을 넘기고 싶게 질문형이나 미완결형을 써도 된다. 단, 그 답은 같은 카드 본문에 반드시 있다.
- 영상이 답하지 않는 궁금증은 만들지 않는다. 낚시·과장·공포 조장 금지. 금지어: 충격, 경악, 실화, 역대급, 난리, 소름, 대박, 무조건, 절대.
- title_pool: 유튜브 제목 후보 8개를 서로 다른 기법으로 만든다. 기법 예시
  · 숫자 반전형: "○○은 줄었는데 △△은 늘었다"
  · 나와의 관계형: "수험생이라면 꼭 알아야 할 ○○"
  · 질문형: "○○, 정말 괜찮을까?"
  · 규모 강조형: "○○명 중 ○○명만…"
  · 시점형: "다음 달부터 바뀌는 ○○"
  각 후보에 "호기심"(1~5, 클릭하고 싶은 정도)과 "정확성"(1~5, 5=영상 내용·사실과 한 글자도 어긋나지 않음)을 스스로 매긴다. 프로그램은 정확성 5점 중 호기심이 높은 3개만 쓴다.
"""

WRITE_RULES = """
[집필 규칙 — 반드시 지킨다]
- 아래 [확인된 사실 목록]에 있는 내용만 쓴다. 목록에 없는 사실·숫자·이름·발언·추측을 더하지 않는다.
- 숫자는 [쓸 수 있는 숫자] 목록에 있는 것만, 기사와 같은 단위로 쓴다. 숫자를 계산해 새 숫자를 만들지 않는다.
- 따옴표는 원문 조각에 그대로 있는 표현에만 쓴다. 바꿔 말할 때는 따옴표를 쓰지 않는다.
- 기사체 '~다'로 쓰고, 기사 문장을 통째로 베끼지 않는다. 같은 어미·구조를 반복하지 않는다.
- evidence: 각 카드(주간은 각 핵심)가 근거로 삼은 사실 번호를 적는다. 예: {"1번 카드": ["F2","F5"]}
- yt_hook: 검색될 핵심 낱말 2~3개가 자연스럽게 들어간 2문장. pinned_comment: 번호로 쉽게 답하는 질문 하나(① ②).
- hashtags: 모두 합쳐 5개 이내.
- 마지막에 JSON 하나만 <json></json> 사이에 출력한다.
"""

DAILY_FORMAT = """{"category":"%s","title":"표지 제목 28자 이내","subtitle":"부제 30자 이내",
"slides":[{"heading":"소제목 16자 이내","body":"본문 2~3문장 %d자 이내"}, … 4개],
"source":"출처: 언론사·기관명(발표 연월)",
"evidence":{"1번 카드":["F1"],"2번 카드":["F3"],"3번 카드":["F4"],"4번 카드":["F6"]},
"title_pool":[{"title":"…","기법":"…","호기심":5,"정확성":5}, … 8개],
"yt_hook":"…","pinned_comment":"…","hashtags":["#오늘의이슈","#카드뉴스","…"]}"""

WEEKLY_FORMAT = """{"week":"%s","range":"%s","cover_title":"썸네일 큰 글씨 18자 이내 (이번 주 가장 의외인 숫자나 변화)",
"issues":[{"category":"교육","title":"이슈 제목 26자 이내 (궁금증이 생기게)","points":["핵심1","핵심2","핵심3","핵심4"],"source":"출처: 언론사·기관명(발표 연월)"}, … 6개],
"evidence":{"이슈1 핵심1":["F1"], … 이슈1~6 × 핵심1~4 모두},
"title_pool":[{"title":"… 40자 이내","기법":"…","호기심":5,"정확성":5}, … 8개],
"yt_hook":"…","pinned_comment":"…","hashtags":["#주간이슈","#이슈정리","…"]}
- 이슈마다 points 4개, 각 1~2문장 %d자 이내. 순서: ①무슨 일(궁금증의 답) ②숫자·배경 ③의외의 사실 ④나에게 미치는 영향.
- 분야는 %s 중에서, 한 분야가 3개를 넘지 않게."""

REVIEW_RULES = """너는 깐깐한 편집장이다. 아래 원고를 [확인된 사실 목록]과 한 문장씩 대조한다.
(가) 사실: 각 문장이 목록의 사실로 뒷받침되는지 본다. 뒷받침되지 않는 내용, 부풀린 표현(검토→결정, 일부→전부 등),
    원문과 다른 따옴표는 목록 범위 안에서 고치거나 지운다. evidence 번호도 맞게 고친다.
(나) 후킹: 표지만 보고 끝까지 넘기고 싶은지 10점 만점으로 매긴다. 7점 미만이면 사실 범위 안에서 표지·소제목·title_pool을 더 날카롭게 고친다.
같은 형식의 JSON 하나만 <json></json> 사이에 출력하고, "fact_notes"(고친 점 짧은 목록, 없으면 빈 목록)와 "hook_score"(숫자)를 넣는다.
"""


def research_prompt(mode, now, settings, history):
    if mode == "daily":
        cat = settings["요일별_분야"][DAYS[now.weekday()]]
        recent = [h["title"] for h in history if h.get("mode") == "daily"][-14:]
        task = f"""오늘은 {now:%Y년 %m월 %d일}({DAYS[now.weekday()]}) 한국 시간 아침이다. 유튜브 쇼츠 카드뉴스를 만들기 위한 취재를 한다.
오늘의 분야는 '{cat}'이다. 최근 24~48시간 사이 한국 국내 '{cat}' 이슈 중 많은 사람에게 영향을 주고, 사람들이 '왜?'라고 궁금해할 만한 것 1건을 고른다.
(다른 분야에 훨씬 큰 국내 이슈가 있으면 바꿔도 된다: {CATEGORIES}) 48시간 안에 마땅한 이슈가 없으면 1주일 이내로 넓힌다.
최근에 이미 다룬 이슈(피할 것): {recent if recent else '없음'}
고른 이슈에 대해 사실을 12개 이상 적는다."""
        return task + RESEARCH_RULES, cat
    start = (now - dt.timedelta(days=6)).date()
    end = (now - dt.timedelta(days=1)).date()
    this_week = [f"{h['date']} {h['category']}: {h['title']}" for h in history
                 if h.get("mode") == "daily" and h["date"] >= str(start)]
    task = f"""오늘은 {now:%Y년 %m월 %d일} 일요일 한국 시간 아침이다. 주간 정리 영상을 위한 취재를 한다.
지난 한 주({start} ~ {end}) 한국 국내 주요 이슈 6개를 고른다. 분야는 {CATEGORIES}에서, 한 분야가 3개를 넘지 않게.
이번 주 쇼츠로 다룬 이슈(우선 후보, 최신 기사로 다시 확인): {this_week if this_week else '기록 없음'}
'선정 이슈:' 줄에 6개를 한꺼번에 쓰고, 각 사실 앞에 [이슈1]~[이슈6] 표시를 붙여 이슈마다 사실을 6개 이상 적는다."""
    return task + RESEARCH_RULES, None


def write_prompt(mode, now, settings, cat, ev, issue):
    sheet = ev.fact_sheet()
    nums = ", ".join(ev.verified_numbers()) or "(없음 — 숫자를 쓰지 않는다)"
    if mode == "daily":
        fast = settings.get("쇼츠_재생속도") == "빠르게"
        fmt = DAILY_FORMAT % (cat, 80 if fast else 110)
        head = f"오늘({now:%Y-%m-%d})의 이슈 '{issue}'로 유튜브 쇼츠 카드뉴스 원고를 쓴다. category는 {CATEGORIES} 중 하나."
    else:
        end = (now - dt.timedelta(days=1)).date()
        start = (now - dt.timedelta(days=6)).date()
        week = f"{end.month}월 {['첫째','둘째','셋째','넷째','다섯째'][(end.day - 1) // 7]} 주"
        rng = f"{start:%Y.%-m.%-d} ~ {end:%-m.%-d}"
        fast = settings.get("주간영상_재생속도") == "빠르게"
        fmt = WEEKLY_FORMAT % (week, rng, 45 if fast else 60, CATEGORIES)
        head = f"지난 한 주 이슈 6개({issue})로 약 5분짜리 주간 정리 영상 원고를 쓴다."
    return f"""{head}
{WRITE_RULES}
{HOOK_RULES}
[쓸 수 있는 숫자] {nums}

[확인된 사실 목록]
{sheet}

[출력 형식]
{fmt}"""


# ───────────────────────── Claude API ─────────────────────────
def _client():
    import anthropic
    key = "".join(os.environ.get("ANTHROPIC_API_KEY", "").split())   # 붙여넣을 때 섞인 빈칸·줄바꿈 제거
    if not key.startswith("sk-ant-"):
        raise RuntimeError("ANTHROPIC_API_KEY가 'sk-ant-'로 시작하지 않습니다. 키를 다시 확인하세요.")
    return anthropic.Anthropic(api_key=key, timeout=900, max_retries=4)


def _call(client, model, messages, tools=None, max_tokens=8000):
    """스트리밍으로 부르고, 긴 검색이 pause_turn으로 멈추면 이어서 부른다. 마지막 응답과 모든 블록을 돌려준다."""
    blocks = []
    for _ in range(8):
        kw = {"model": model, "max_tokens": max_tokens, "messages": messages}
        if tools:
            kw["tools"] = tools
        with client.messages.stream(**kw) as st:
            resp = st.get_final_message()
        blocks += list(resp.content)
        messages.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason != "pause_turn":
            break
    return resp, blocks


def research(mode, now, settings, history, model):
    client = _client()
    prompt, cat = research_prompt(mode, now, settings, history)
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 12 if mode == "daily" else 30,
              "user_location": {"type": "approximate", "city": "Seoul", "country": "KR", "timezone": "Asia/Seoul"}}]
    messages = [{"role": "user", "content": prompt}]
    _, blocks = _call(client, model, messages, tools, max_tokens=12000)
    facts, issue = factcheck.collect_facts(blocks)
    need = 8 if mode == "daily" else 24
    if len(facts) < need:      # 인용 붙은 사실이 모자라면 한 번 더 취재
        messages.append({"role": "user", "content": f"인용이 붙은 사실이 {len(facts)}개뿐이다. 같은 이슈로 검색을 더 해서, "
                                                     f"검색 결과를 인용한 사실을 한 줄에 하나씩 {need}개 이상 다시 적어라."})
        _, more = _call(client, model, messages, tools, max_tokens=12000)
        facts, issue2 = factcheck.collect_facts(blocks + more)
        issue = issue or issue2
    if len(facts) < need // 2:
        raise RuntimeError(f"기사로 확인된 사실이 {len(facts)}개뿐이라 오늘은 영상을 만들지 않았습니다.")
    return facts, issue, cat


def write_and_verify(mode, now, settings, facts, issue, cat, model):
    """확인된 사실만으로 원고를 쓰게 하고(검색 없음), 기계 검사를 통과할 때까지 고친다."""
    client = _client()
    ev = factcheck.Evidence(facts)
    ids = {f["id"] for f in facts}
    messages = [{"role": "user", "content": write_prompt(mode, now, settings, cat, ev, issue)}]
    spec, reviewed, problems = None, False, []
    for attempt in range(5):
        resp, _ = _call(client, model, messages)
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        try:
            spec = parse_json(text)
            check(spec, mode, titles_required=False)
        except ValueError as e:
            problems = [f"형식: {e}"]
            messages.append({"role": "user", "content": f"형식 문제: {e}\n고쳐서 <json></json> 안에 JSON 하나만 다시 출력하라."})
            continue
        problems = ev.problems(factcheck.script_texts(spec, mode)) + factcheck.evidence_problems(spec, mode, ids)
        titles = factcheck.pick_titles(spec, ev)
        if len(titles) < 3:
            problems.append(f"정확성 5점이면서 검사를 통과한 제목 후보가 {len(titles)}개뿐이다. title_pool을 사실 범위 안에서 다시 만들어라")
        if problems:
            messages.append({"role": "user", "content": "프로그램 검사에서 아래 문제가 나왔다. [확인된 사실 목록] 범위 안에서 고치고 "
                                                         "JSON 하나만 다시 출력하라.\n- " + "\n- ".join(problems[:30])})
            continue
        if not reviewed:            # 기계 검사 통과 후, 편집장 검토 1회 (뜻이 부풀려졌는지·후킹이 약한지)
            reviewed = True
            messages.append({"role": "user", "content": REVIEW_RULES})
            continue
        spec["yt_titles"] = titles
        spec["_check"] = (f"숫자 {len(set().union(*[factcheck.numbers(t) for t in factcheck.script_texts(spec, mode).values()]))}개 · "
                          f"인용 사실 {len(facts)}개 · 출처 {len({c['domain'] for f in facts for c in f['cites']})}곳 대조 통과")
        return spec
    raise RuntimeError("기사로 확인되지 않는 내용을 끝까지 고치지 못해 오늘은 영상을 만들지 않았습니다. "
                       "(마지막 문제: " + "; ".join(problems[:3] or ["형식 오류"]) + ")")


def parse_json(text):
    m = re.search(r"<json>(.*?)</json>", text, re.S)
    raw = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON 형식 오류 ({e})")


def check(spec, mode, titles_required=True):
    """원고가 영상으로 만들 수 있는 모양인지 확인한다. 문제가 있으면 ValueError."""
    need = ["yt_hook", "pinned_comment", "hashtags"] + (["yt_titles"] if titles_required else ["title_pool"])
    need += ["category", "title", "slides", "source"] if mode == "daily" else ["week", "range", "cover_title", "issues"]
    miss = [k for k in need if not spec.get(k)]
    if miss:
        raise ValueError(f"빠진 항목: {miss}")
    if titles_required and len(spec["yt_titles"]) < 3:
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
    if spec.get("_check"):
        check_txt += f"· 자동 사실 검사: {spec['_check']}\n"
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
        model = settings.get("AI_모델", "claude-sonnet-5-5")
        facts, issue, cat = research(mode, now, settings, history, model)
        spec = write_and_verify(mode, now, settings, facts, issue, cat, model)
        check(spec, mode)
        urls = list(dict.fromkeys(c["url"] for f in facts for c in f["cites"]))[:12]

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


def already_done(mode):
    """예약 실행이 여러 번 잡혀 있어도 하루(주간은 그날) 한 번만 보내도록 기록을 확인한다."""
    today = dt.datetime.now(KST).strftime("%Y-%m-%d")
    return any(h.get("mode") == mode and h.get("date") == today for h in load_json("history.json", []))


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "daily"
    if os.environ.get("GITHUB_EVENT_NAME") == "schedule" and already_done(mode):
        print(f"오늘 {mode} 메일은 이미 보냈습니다. 이번 예약 실행은 건너뜁니다.")
        return
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

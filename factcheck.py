"""사실 확인 장치 — AI의 말이 아니라 '검색 결과 원문 조각'을 기준으로 기계적으로 검사한다.

1) 취재: web_search 결과를 인용(citation)한 문장만 사실로 인정한다.
   인용에는 API가 실제 기사에서 잘라 온 원문 조각(cited_text)이 붙어 오므로 AI가 꾸며낼 수 없다.
2) 숫자: 원고에 나오는 모든 숫자는 서로 다른 언론사·기관 2곳 이상(정부 사이트는 1곳)의
   원문 조각에 들어 있어야 쓸 수 있다.
3) 인용 발언: 따옴표 안 표현은 원문 조각에 글자 그대로 있어야 한다.
4) 과장 단어: 금지어가 있으면 탈락.
"""
import re
from urllib.parse import urlparse

BANNED = ["충격", "경악", "실화", "역대급", "난리", "소름", "대박", "미쳤", "100%", "무조건", "절대"]
OFFICIAL = (".go.kr", "korea.kr")
NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
QUOTE_RE = re.compile(r"[\"“”‘’'「」]([^\"“”‘’'「」]{1,40})[\"“”‘’'「」]")
EXEMPT = [r"1분"]          # '1분 정리'처럼 형식에 쓰는 숫자


def domain(url):
    d = urlparse(url or "").netloc.lower()
    for p in ("www.", "m.", "mobile.", "n."):
        if d.startswith(p):
            d = d[len(p):]
    return d


def numbers(text):
    for pat in EXEMPT:
        text = re.sub(pat, "", text)
    return {n.replace(",", "").rstrip(".") for n in NUM_RE.findall(text)}


def number_kinds(text):
    """숫자마다 날짜·시각(○월 ○일 ○시 ○분)인지 표시한다. 날짜·시각은 1곳 확인으로 충분, 나머지 수치는 2곳."""
    for pat in EXEMPT:
        text = re.sub(pat, "", text)
    out = {}
    for m in NUM_RE.finditer(text):
        n = m.group().replace(",", "").rstrip(".")
        is_time = bool(re.match(r"\s*(월|일|시|분)", text[m.end():m.end() + 2]))
        out[n] = out.get(n, True) and is_time
    return out


def squash(text):
    return re.sub(r"[\s\"“”‘’'「」.,·…!?()\[\]~-]", "", text or "")


# ───────── 1) 취재 결과에서 인용 붙은 사실만 모으기 ─────────
def collect_facts(content):
    """API 응답 블록에서 (사실 문장, 인용 목록)을 뽑는다. 인용 없는 문장은 버린다."""
    facts, issue = [], ""
    for b in content:
        if getattr(b, "type", "") != "text":
            continue
        text = (b.text or "").strip()
        m = re.search(r"선정 이슈\s*[:：]\s*(.+)", text)
        if m:
            issue = m.group(1).strip()
        cites = []
        for c in getattr(b, "citations", None) or []:
            url, ct = getattr(c, "url", None), getattr(c, "cited_text", None)
            if url and ct:
                cites.append({"url": url, "domain": domain(url), "title": getattr(c, "title", "") or "", "text": ct})
        if cites and len(text) >= 8:
            facts.append({"text": text, "cites": cites})
    # 같은 문장이 여러 블록으로 나뉘어 오면 합친다
    merged = {}
    for f in facts:
        k = squash(f["text"])
        if k in merged:
            merged[k]["cites"] += f["cites"]
        else:
            merged[k] = f
    out = list(merged.values())
    for i, f in enumerate(out, 1):
        f["id"] = f"F{i}"
    return out, issue


class Evidence:
    """원문 조각 전체를 모아 두고 숫자·인용을 검사한다."""
    def __init__(self, facts):
        self.facts = facts
        self.snippets = [(c["domain"], c["text"]) for f in facts for c in f["cites"]]
        self.flat = [(d, squash(t)) for d, t in self.snippets]

    def number_ok(self, n, is_time=False):
        doms = {d for d, t in self.snippets if n in numbers(t)}
        return len(doms) >= (1 if is_time else 2) or any(d.endswith(OFFICIAL) for d in doms)

    def verified_numbers(self):
        alln = set().union(*[numbers(t) for _, t in self.snippets]) if self.snippets else set()
        return sorted(n for n in alln if self.number_ok(n))

    def quote_ok(self, q):
        sq = squash(q)
        return any(sq in t for _, t in self.flat)

    def sentence_support(self, sentence):
        """문장의 낱말(앞 두 글자)이 기사 원문 조각에 얼마나 들어 있는지 비율로 돌려준다."""
        stems = [w[:2] for w in re.findall(r"[0-9A-Za-z가-힣]+", sentence) if len(w) >= 2]
        if len(stems) < 3:
            return 1.0
        pool = "".join(t for _, t in self.flat)
        return sum(1 for st in stems if st in pool) / len(stems)

    def problems(self, texts):
        """texts: {위치: 문장}. 규칙 위반 목록을 돌려준다."""
        bad = []
        for where, t in texts.items():
            if not t:
                continue
            for n, is_time in number_kinds(t).items():
                if not self.number_ok(n, is_time):
                    bad.append(f"{where}: 숫자 '{n}'은(는) 두 곳 이상의 기사 원문에서 확인되지 않았다")
            for q in QUOTE_RE.findall(t):
                if not self.quote_ok(q):
                    bad.append(f"{where}: 따옴표 표현 '{q}'은(는) 기사 원문에 그대로 있지 않다 (따옴표를 빼거나 원문 표현으로)")
            for w in BANNED:
                if w in t:
                    bad.append(f"{where}: 금지어 '{w}' 사용")
            if "본문" in where or "핵심" in where:      # 사실을 말하는 문장은 원문 낱말과 대조
                for sent in re.split(r"(?<=[.!?。])\s+", t.strip()):
                    if sent.endswith("?") or len(sent) < 8:
                        continue          # 시청자에게 던지는 질문은 사실 주장이 아니다
                    if self.sentence_support(sent) < 0.5:
                        bad.append(f"{where}: '{sent[:40]}…' 문장은 기사 원문에서 근거를 찾을 수 없다 (사실 목록의 내용으로 바꾸거나 지운다)")
        return bad

    def fact_sheet(self):
        lines = []
        for f in self.facts:
            srcs = ", ".join(sorted({c["domain"] for c in f["cites"]}))
            lines.append(f"{f['id']} [{srcs}] {f['text']}")
            for c in f["cites"][:3]:
                lines.append(f"    └ 원문: {c['text'][:150]}")
        return "\n".join(lines)


def script_texts(spec, mode):
    """검사할 원고 문장들을 위치 이름과 함께 꺼낸다."""
    t = {"yt_hook": spec.get("yt_hook", "")}
    for i, x in enumerate(spec.get("yt_titles", []), 1):
        t[f"제목후보{i}"] = x
    if mode == "daily":
        t["표지 제목"] = spec.get("title", "")
        t["부제"] = spec.get("subtitle", "")
        for i, s in enumerate(spec.get("slides", []), 1):
            t[f"{i}번 카드 소제목"] = s.get("heading", "")
            t[f"{i}번 카드 본문"] = s.get("body", "")
    else:
        t["썸네일 문구"] = spec.get("cover_title", "")
        for i, it in enumerate(spec.get("issues", []), 1):
            t[f"이슈{i} 제목"] = it.get("title", "")
            for k, p in enumerate(it.get("points", []), 1):
                t[f"이슈{i} 핵심{k}"] = p
    return t


def evidence_problems(spec, mode, fact_ids):
    """모든 카드(주간은 모든 핵심)에 근거 사실 번호가 달렸는지, 없는 번호를 쓰지 않았는지."""
    ev = spec.get("evidence") or {}
    need = [f"{i}번 카드" for i in range(1, 5)] if mode == "daily" else \
        [f"이슈{i} 핵심{k}" for i in range(1, 7) for k in range(1, 5)]
    bad = []
    for key in need:
        ids = ev.get(key) or []
        if not ids:
            bad.append(f"{key}: evidence에 근거 사실 번호가 없다")
        for x in ids:
            if x not in fact_ids:
                bad.append(f"{key}: 없는 사실 번호 {x}")
    return bad


def pick_titles(spec, evidence):
    """제목 후보 중 정확성 5점이고 기계 검사를 통과한 것을 호기심 점수 순으로 3개 고른다."""
    pool = spec.get("title_pool") or []
    good = []
    for c in pool:
        t = (c.get("title") or "").strip()
        if not t or c.get("정확성", 0) < 5 or len(t) > 45:
            continue
        if evidence.problems({"제목": t}):
            continue
        good.append((c.get("호기심", 0), t))
    good.sort(key=lambda x: -x[0])
    titles = list(dict.fromkeys(t for _, t in good))[:3]
    return titles

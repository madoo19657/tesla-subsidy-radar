"""madoo — 테슬라 전기차 보조금 현황 수집기

ev.or.kr 에서 두 가지를 읽어 data.json / index.html 을 다시 만듭니다.
  1) 지자체별 보조금 현황(전기승용): 공고·접수·선정·출고·잔여, 접수기간, 신청마감
  2) 지자체별 차종·모델 보조금: 테슬라 모델의 국비·지방비·전환지원금

ev.or.kr 은 응답 HTML 이 암호화되어 requests/BeautifulSoup 로는 파싱할 수 없어서
브라우저(Playwright)로 렌더링된 표(ag-Grid)를 읽습니다.

  pip install playwright && playwright install chromium
  python scrape_ev.py
"""
import json, re, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

HERE = Path(__file__).parent
STATUS_URL = "https://www.ev.or.kr/nportal/buySupprt/initSubsidyPaymentCheckAction.do"
MODEL_URL = "https://www.ev.or.kr/nportal/buySupprt/initPsLocalCarPirceAction.do"
YEAR = 2026
BRAND_KEYWORD = "테슬라"
# 테슬라 코리아 공식 사이트(2026-10-21 확인)에서 판매 중인 트림만 남긴다. 이름은 ev.or.kr 표기 그대로
SELLING = {
    "Model 3 Performance", "Model 3 RWD", "Model 3 Premium Long Range RWD(5999만원)",
    "Model Y Premium RWD", "Model Y Premium Long Range", "Model Y L AWD", "Model Y premium L AWD",
}
KST = timezone(timedelta(hours=9))

ROWS_JS = """(sel) => [...document.querySelectorAll(sel + ' .ag-row')]
  .sort((a,b)=>a.getAttribute('row-index')-b.getAttribute('row-index'))
  .map(r=>{const o={};r.querySelectorAll('[role=gridcell]').forEach(c=>o[c.getAttribute('col-id')]=c.innerText.replace(/\\s+/g,' ').trim());return o})"""

DISMISS_JS = """() => {
  document.querySelectorAll('.modal-container.is-active').forEach(m => {
    const b = [...m.querySelectorAll('button')].find(x => /닫기|확인|오늘|close/i.test(x.innerText + (x.getAttribute('aria-label') || '')));
    if (b) b.click();
    m.classList.remove('is-active'); m.setAttribute('aria-hidden', 'true'); m.style.display = 'none';
  });
  document.body.classList.remove('modal-open');
}"""


def dismiss(pg):
    """접속 시 자동으로 뜨는 안내 팝업(예: #alertCalcNotice)이 클릭을 가로채므로 닫는다"""
    pg.evaluate(DISMISS_JS)
    time.sleep(0.2)


def open_page(pg, url, ready_selector):
    """해외(GitHub 서버)에서는 ev.or.kr 이 느려 networkidle 이 오지 않는다 → DOM 로드 후 필요한 요소만 기다리고 3회 재시도"""
    last = None
    for attempt in range(1, 4):
        try:
            pg.goto(url, wait_until="domcontentloaded", timeout=90000)
            pg.wait_for_selector(ready_selector, timeout=90000)
            dismiss(pg)
            return
        except PWTimeout as e:
            last = e
            print(f"  접속 재시도 {attempt}/3: {url.split('/')[-1]}")
            time.sleep(5)
    raise last


num = lambda s: int(re.sub(r"[^\d]", "", s or "") or 0)


# ---------- 1) 지자체별 보조금 현황 ----------
def scrape_status(pg):
    open_page(pg, STATUS_URL, "select[name=year1]")
    pg.select_option("select[name=year1]", str(YEAR))
    pg.wait_for_selector(".ag-row", timeout=90000)
    rows, seen = [], set()
    for _ in range(80):
        cur = pg.inner_text(".pagination__link--selected").strip()
        if cur in seen:
            break
        seen.add(cur)
        dismiss(pg)
        rows += pg.evaluate(ROWS_JS, "body")
        links = pg.query_selector_all(".pagination__link")
        idx = next((i for i, l in enumerate(links) if "selected" in (l.get_attribute("class") or "")), -1)
        nxt = pg.query_selector(".pagination__button[data-page=next]")
        if 0 <= idx < len(links) - 1:
            links[idx + 1].click()
        elif nxt and not nxt.is_disabled():
            nxt.click()
        else:
            break
        time.sleep(0.9)
    return rows


def _period(s):
    t = re.findall(r"\d{4}\.\d\d\.\d\d \d\d:\d\d", s or "")
    return [x.replace(".", "-").replace(" ", "T") for x in t] if len(t) == 2 else None


def aggregate(rows):
    """지역별 1행으로 합침(합계가 공고 차수마다 반복 표시됨). 마지막 값 = 끝나지 않은 접수기간 [시작, 끝] 또는 None"""
    m, wins = {}, {}
    now = datetime.now(KST).strftime("%Y-%m-%dT%H:%M")
    for r in rows:
        key = r["sido"]
        pr = _period(r.get("period"))
        if pr and pr[1] >= now and (key not in wins or pr[0] < wins[key][0]):
            wins[key] = pr
        if key in m:
            continue
        t = key.replace("즐겨찾기", "").strip()
        closed = "마감" in t
        parts = t.replace("마감", "").split()
        m[key] = [parts[0], " ".join(parts[1:]), int(closed), num(r["stepCnt"]), num(r["recei"]),
                  num(r["choice"]), num(r["relea"]), num(r["choiceRemain"]), num(r["resi"]), r["deadline"]]
    return [v + [wins.get(k)] for k, v in m.items()]


# ---------- 2) 테슬라 모델별 보조금 ----------
def scrape_models(pg):
    """return (models, {"시도|지역": {모델index: [국비, 지방비, 전환국비, 전환지방비]}})"""
    open_page(pg, MODEL_URL, "#btnSearch")
    pg.select_option("#carTypeFilter", "11")
    pg.fill("#modelKeyword", BRAND_KEYWORD)
    dismiss(pg)
    pg.click("#btnSearch")
    pg.wait_for_selector(".accordion-button", timeout=90000)
    heads = pg.query_selector_all(".accordion-button")
    models, out = [], {}
    for h in heads:
        rid = h.get_attribute("id").replace("accHeader_", "")
        lines = [x.strip() for x in h.inner_text().split("\n") if x.strip()]
        name, sido = lines[0], lines[1]
        sel = f"#carGrid_{rid}"
        rows = []
        for _ in range(2):  # 표가 늦게 그려지는 지역이 있어 한 번 더 시도
            dismiss(pg)
            if h.get_attribute("aria-expanded") != "true":
                h.evaluate("e => e.click()")
            try:
                pg.wait_for_function(
                    "(s)=>{const g=document.querySelector(s);return g&&(g.querySelector('.ag-row')||g.textContent.includes('조회된 내용이 없습니다'))}",
                    arg=sel, timeout=6000)
            except PWTimeout:
                pass
            rows = pg.evaluate(ROWS_JS, sel)
            if rows:
                break
            h.evaluate("e => e.click()")
            time.sleep(0.3)  # 접었다 다시 펼침
        pol = {}
        for x in rows:
            if " ".join(x.get("model", "").split()) not in SELLING:  # 판매 중인 트림만
                continue
            if BRAND_KEYWORD not in x.get("maker", "") and "Tesla" not in x.get("maker", "") and "Model" not in x.get("model", ""):
                continue
            if x["model"] not in models:
                models.append(x["model"])
            pol[str(models.index(x["model"]))] = [num(x["gov"]), num(x["local"]), num(x["exGov"]), num(x["exLocal"])]
        out[f"{sido}|{name}"] = pol
    return models, out


# ---------- 합치기 ----------
KEYS = ["sido", "name", "closed", "notice", "recv", "sel", "rel", "selRemain", "relRemain", "deadline", "win"]


def build(rows_compact, as_of=None, pol=None, models=None):
    data = {"asOf": as_of or datetime.now(timezone.utc).isoformat(), "year": YEAR, "type": "전기승용",
            "models": models or [],
            "regions": [dict(zip(KEYS, r), closed=bool(r[2]), pol=(pol or {}).get(f"{r[0]}|{r[1]}", {}))
                        for r in rows_compact]}
    (HERE / "data.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tpl = (HERE / "template.html").read_text(encoding="utf-8")
    (HERE / "index.html").write_text(tpl.replace("/*DATA*/null", json.dumps(data, ensure_ascii=False)), encoding="utf-8")
    return data


def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(locale="ko-KR", viewport={"width": 1400, "height": 1000})
        pg = ctx.new_page()
        pg.set_default_timeout(45000)
        try:
            agg = aggregate(scrape_status(pg))
            print(f"[1/2] 보조금 현황 {len(agg)}곳 수집")
            models, pol = scrape_models(pg)
            print(f"[2/2] 테슬라 모델 {len(models)}개, 금액 있는 지역 {sum(1 for v in pol.values() if v)}곳")
        except Exception:
            # 실패 시점의 화면을 남겨 원인을 볼 수 있게 한다 (Actions 아티팩트로 업로드됨)
            try:
                pg.screenshot(path=str(HERE / "debug.png"), full_page=False)
                (HERE / "debug.html.txt").write_text(pg.content()[:200000], encoding="utf-8")
                print("현재 주소:", pg.url)
            except Exception:
                pass
            raise
        finally:
            b.close()
    # 수집 결과가 비정상이면 기존 파일을 유지한다 (사이트 개편·차단 대비)
    if len(agg) < 100:
        sys.exit(f"보조금 현황 수집 이상({len(agg)}곳). 기존 파일 유지.")
    n_pol = sum(1 for v in pol.values() if v)
    if not models or n_pol < 50:
        sys.exit(f"테슬라 금액 수집 이상(모델 {len(models)}개, 지역 {n_pol}곳). 기존 파일 유지.")
    old = HERE / "data.json"
    if old.exists():  # 내용이 같고 6시간 이내면 다시 쓰지 않음 (불필요한 커밋 방지)
        try:
            o = json.loads(old.read_text(encoding="utf-8"))
            fresh = datetime.now(timezone.utc) - datetime.fromisoformat(o["asOf"]) < timedelta(hours=6)
            new_regions = [dict(zip(KEYS, r), closed=bool(r[2]), pol=pol.get(f"{r[0]}|{r[1]}", {})) for r in agg]
            if fresh and o.get("models") == models and o.get("regions") == new_regions:
                print("변경 없음 — 파일을 갱신하지 않습니다.")
                return
        except Exception:
            pass
    d = build(agg, pol=pol, models=models)
    print(f"완료: 지역 {len(d['regions'])}곳, 테슬라 모델 {len(models)}개 ({', '.join(models)})")


if __name__ == "__main__":
    main()

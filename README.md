# madoo · 테슬라 전기차 보조금 레이더

내 지역에서 테슬라 보조금을 얼마 받는지(국비+지방비), 접수가 열려 있는지, 잔여가 얼마인지 보여주는 정적 대시보드.
데이터 출처는 환경부 무공해차 통합누리집(ev.or.kr)이며, GitHub Actions 가 하루 3회(한국시간 09:07 · 13:07 · 18:07 경) 갱신합니다.

| 파일 | 역할 |
|---|---|
| `index.html` | 대시보드 (data.json 을 읽고, 실패하면 내장 데이터 사용) |
| `data.json` | 지역 160곳 상태 + 테슬라 모델별 금액 |
| `scrape_ev.py` | ev.or.kr 수집 → data.json / index.html 재생성 |
| `template.html` | 디자인 원본 (수정은 여기서, 수집기가 index.html 로 합침) |
| `.github/workflows/update.yml` | 하루 3회 자동 수집·커밋 |
| `run_local.bat` | 내 PC 에서 수집·푸시 (Actions 접속이 막힐 때 대안) |

## GitHub 호스팅 + 자동 갱신 (1회 설정)
1. 저장소: https://github.com/madoo19657/tesla-subsidy-radar (**Public**, 비어 있는 상태로 생성)
2. 이 저장소에 이미 올라가 있습니다
   ```
   git init && git add . && git commit -m "init"
   git branch -M main && git remote add origin https://github.com/madoo19657/tesla-subsidy-radar.git
   git push -u origin main
   ```
3. 저장소 Settings → **Pages** → Source: *Deploy from a branch* → `main` / `(root)` → Save
   → 주소: `https://madoo19657.github.io/tesla-subsidy-radar/`
4. Settings → Actions → General → Workflow permissions → **Read and write permissions** → Save
5. Actions 탭 → `update-data` → **Run workflow** 로 첫 수집을 직접 실행해 성공 여부 확인

### 꼭 확인할 것
- ev.or.kr 이 해외(GitHub 서버) 접속을 막거나 느리게 할 수 있습니다. 5번 수동 실행이 실패하면:
  - `run_local.bat` 을 Windows 작업 스케줄러에 등록(예: 하루 3회)하거나
  - 집 PC 를 self-hosted runner 로 등록하세요.
- 수집 결과가 비정상(지역 100곳 미만 등)이면 기존 파일을 그대로 둡니다. 화면 상단의 조회 시각으로 신선도를 확인할 수 있습니다.

## 네이버 블로그에 넣는 법
스마트에디터 본문은 iframe/스크립트를 허용하지 않습니다.
1. Pages 주소를 글에 붙여넣어 링크 카드로 삽입 (제목·설명은 `template.html` 의 `<title>`, og 태그가 사용됨)
2. 핵심 수치 캡처 + 텍스트 요약을 같이 넣으면 검색 노출에 유리
3. 블로그 사이드바 위젯(위젯 직접등록)의 iframe 허용 여부는 네이버 정책에 따라 다르므로 직접 확인

## 로컬에서 수집
```
pip install -r requirements.txt
playwright install chromium
python scrape_ev.py
```

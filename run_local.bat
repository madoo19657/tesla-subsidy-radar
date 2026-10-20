@echo off
REM madoo — 내 PC에서 수집하고 GitHub 에 올리기 (Windows 작업 스케줄러용)
REM GitHub Actions 에서 ev.or.kr 접속이 막힐 때 대신 사용합니다.
cd /d "%~dp0"
python scrape_ev.py || exit /b 1
git add data.json index.html
git diff --cached --quiet && (echo no changes & exit /b 0)
git commit -m "data: update %date% %time%"
git push

@echo off
chcp 65001 >nul
rem ▼ GitHub Pages 주소를 여기에 넣으세요 (예: https://아이디.github.io/저장소이름/)
set PAGE_URL=https://YOUR-ID.github.io/donghae-office/
rem 시장실 TV에 전체화면(키오스크)으로 액자모드부터 띄웁니다. 크롬이 없으면 엣지를 씁니다.
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
  start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --kiosk --noerrdialogs --disable-session-crashed-bubble "%PAGE_URL%#frame"
) else (
  start "" "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --kiosk "%PAGE_URL%#frame" --edge-kiosk-type=fullscreen --no-first-run
)

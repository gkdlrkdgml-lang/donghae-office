@echo off
chcp 65001 >nul
rem 관리자 권한으로 한 번만 실행합니다. 로그인하면 TV 화면이 자동으로 뜹니다.
schtasks /Create /F /TN "DonghaeOffice_Screen" /SC ONLOGON /DELAY 0000:30 /TR "\"%~dp0start_tv.bat\""
echo.
echo 등록 완료. 작업 스케줄러에서 DonghaeOffice_Screen 을 확인하세요.
pause

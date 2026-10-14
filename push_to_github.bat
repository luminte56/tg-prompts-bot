@echo off
title Push to GitHub - White Lord IntelLab
cd /d "%~dp0"
echo ========================================================
echo  Push repository to GitHub
echo ========================================================
set /p REPO_URL="Enter GitHub repo URL (e.g. https://github.com/user/repo.git): "
if "%REPO_URL%"=="" (
    echo [!] URL cannot be empty.
    pause
    exit /b
)
git remote remove origin 2>nul
git remote add origin %REPO_URL%
git branch -M main
git push -u origin main
echo.
echo [OK] Completed!
pause

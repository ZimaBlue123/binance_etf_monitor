@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM ============================================================
REM   fix-remote-tracking.bat
REM
REM   修复 PortableGit + Windows 偶发问题:
REM   git fetch 之后 refs/remotes/origin/main 写入失败，
REM   导致 git status 提示 [origin/main: gone]。
REM
REM   流程: fetch -> 校验 -> 必要时从 ls-remote 提取 HEAD SHA
REM   -> 重建 loose ref -> 最终验证
REM
REM   用法: 双击或在终端运行 fix-remote-tracking.bat
REM ============================================================

cd /d "%~dp0"

echo ========================================================
echo   修复 remote-tracking ref
echo ========================================================
echo.

REM 1. fetch
echo [1/3] git fetch origin...
git fetch origin 2>nul
echo.

REM 2. 检查 origin/main 是否可解析 + 文件是否存在
git rev-parse origin/main 2>nul 1>"%TEMP%\_wa_sha.txt"
set "ORIGIN_SHA="
for /f "usebackq delims=" %%i in ("%TEMP%\_wa_sha.txt") do set "ORIGIN_SHA=%%i"
if defined ORIGIN_SHA if exist ".git\refs\remotes\origin\main" goto :VerifyOk

REM 3. 异常回退 -> 从 ls-remote 获取 HEAD SHA 并重建
echo [2/3] 重建 loose refs/remotes/origin/main...
git ls-remote origin HEAD 1>"%TEMP%\_wa_lr.txt" 2>nul
set "HEAD_SHA="
for /f "tokens=1" %%h in ('type "%TEMP%\_wa_lr.txt" 2^>nul') do set "HEAD_SHA=%%h"
if not defined HEAD_SHA (
    echo   [FAIL] 无法获取 HEAD SHA
    goto :End
)
if exist ".git\packed-refs" (
    findstr /v "refs/remotes/origin/main" ".git\packed-refs" 1>"%TEMP%\_wa_p.txt" 2>nul
    move /y "%TEMP%\_wa_p.txt" ".git\packed-refs" >nul 2>&1
)
if exist ".git\refs\remotes\origin\main" del /f /q ".git\refs\remotes\origin\main"
if not exist .git\refs\remotes\origin mkdir .git\refs\remotes\origin
echo %HEAD_SHA%> .git\refs\remotes\origin\main
echo ref: refs/remotes/origin/main> .git\refs\remotes\origin\HEAD
echo.

REM 4. 验证
:VerifyOk
echo [3/3] 验证...
git status -sb 1>"%TEMP%\_wa_st.txt" 2>nul
findstr /b "##" "%TEMP%\_wa_st.txt" 1>"%TEMP%\_wa_st2.txt" 2>nul
findstr /c:"[gone]" "%TEMP%\_wa_st2.txt" >nul 2>&1 && (
    echo   [WARN] status 仍包含 [gone]:
    type "%TEMP%\_wa_st2.txt"
) || (
    echo   [OK] remote-tracking ref 已就绪:
    type "%TEMP%\_wa_st2.txt"
)

:End
del /f /q "%TEMP%\_wa_sha.txt" "%TEMP%\_wa_lr.txt" "%TEMP%\_wa_st.txt" "%TEMP%\_wa_st2.txt" 2>nul
echo.
echo 完成。
endlocal
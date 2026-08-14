@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"

rem ============================================================
rem  rebuild_apk.bat - Binance ETF Monitor APK Builder
rem
rem  Usage:
rem    rebuild_apk.bat            Auto bump version (Default)
rem    rebuild_apk.bat same       Keep current version
rem    rebuild_apk.bat check      Check environment and asset sync
rem    Append nopause to not pause (e.g. rebuild_apk.bat same nopause)
rem ============================================================

set "MODE=auto"
set "NOPAUSE="

if /i "%~1"=="nopause" set "NOPAUSE=1"
if /i "%~2"=="nopause" set "NOPAUSE=1"
if /i "%~1"=="same"  set "MODE=same"
if /i "%~1"=="check" set "MODE=check"

set "ROOT=%~dp0"
set "ANDROID=%ROOT%android"
set "APP=%ANDROID%\app"
set "ASSETS=%APP%\src\main\assets\project"

rem ---------- Environment Check ----------
if not defined JAVA_HOME     set "JAVA_HOME=C:\Users\Administrator\jdk17\jdk-17"
if not defined ANDROID_HOME  set "ANDROID_HOME=C:\Users\Administrator\android-sdk"
set "GRADLE=C:\Gradle\gradle-8.7\bin\gradle.bat"

echo [1/7] Checking build environment...
if not exist "%JAVA_HOME%\bin\java.exe" (
    echo [!] Error: JDK not found at %JAVA_HOME%
    echo     Please install JDK 17 and configure JAVA_HOME.
    goto :fail
)
if not exist "%ANDROID_HOME%\platform-tools" (
    echo [!] Error: Android SDK not found at %ANDROID_HOME%
    echo     Please configure ANDROID_HOME.
    goto :fail
)
if not exist "%GRADLE%" (
    echo [!] Error: Gradle not found at %GRADLE%
    echo     Please install Gradle 8.7 or adjust GRADLE path.
    goto :fail
)
if not exist "%ANDROID%\keystore\keystore.properties" (
    echo [!] Error: Missing signing config at android\keystore\keystore.properties
    echo     Please refer to android\BUILD.md.
    goto :fail
)
echo [OK] JAVA_HOME     = %JAVA_HOME%
echo [OK] ANDROID_HOME  = %ANDROID_HOME%
echo [OK] Gradle        = %GRADLE%
echo [OK] Keystore config ready (android\keystore\)

if /i "%MODE%"=="check" (
    echo.
    echo [*] Mode=check: Environment verified. No build executed.
    echo     Source config: %ROOT%config\
    echo     APK assets:    %ASSETS%
    goto :end
)

rem ---------- 1. Sync Assets ----------
echo.
echo [2/7] Syncing project files to APK assets directory...
xcopy /y /q "%ROOT%binance_etf_configurable.py" "%ASSETS%\" >nul
if errorlevel 4 goto :fail
xcopy /y /q /e /i "%ROOT%config" "%ASSETS%\config\" >nul
if errorlevel 4 goto :fail
xcopy /y /q "%ROOT%scripts\validate_strategy_assets.py" "%ASSETS%\scripts\" >nul
if errorlevel 4 goto :fail
xcopy /y /q "%ROOT%requirements.txt" "%ASSETS%\" >nul
if errorlevel 4 goto :fail
echo [OK] Assets synced (binance_etf_configurable.py / config / scripts / requirements.txt)

rem ---------- 2. Verify Asset MD5 ----------
echo.
echo [3/7] Verifying etf_products.json hash consistency...
for /f "tokens=*" %%h in ('certutil -hashfile "%ROOT%config\etf_products.json" MD5 ^| findstr /i /r "^[0-9a-f]*$"') do set "SRC_MD5=%%h"
for /f "tokens=*" %%h in ('certutil -hashfile "%ASSETS%\config\etf_products.json" MD5 ^| findstr /i /r "^[0-9a-f]*$"') do set "ASSET_MD5=%%h"
if not "!SRC_MD5!"=="!ASSET_MD5!" (
    echo [!] Error: etf_products.json hash mismatch!
    echo     Source MD5: !SRC_MD5!
    echo     Asset MD5:  !ASSET_MD5!
    goto :fail
)
echo [OK] MD5 verified: !SRC_MD5!

rem ---------- 3. Version Bump ----------
echo.
if "%MODE%"=="same" (
    echo [4/7] Mode=same: Keeping current version...
    for /f "usebackq tokens=1,2" %%a in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%ANDROID%\bump_version.ps1" -GradleFile "%APP%\build.gradle" -Same`) do (
        set "VC=%%a"
        set "VN=%%b"
    )
) else (
    echo [4/7] Auto-bumping version...
    for /f "usebackq tokens=1,2" %%a in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%ANDROID%\bump_version.ps1" -GradleFile "%APP%\build.gradle"`) do (
        set "VC=%%a"
        set "VN=%%b"
    )
)
if not defined VN (
    echo [!] Error: Failed to resolve version from android\app\build.gradle
    goto :fail
)
echo [OK] Target version: v%VN% (versionCode %VC%)

rem ---------- 4. Clean ----------
echo.
echo [5/7] Stopping Gradle daemon and cleaning cache...
call "%GRADLE%" --stop >nul 2>&1
if exist "%APP%\build\python\pip" (
    rmdir /s /q "%APP%\build\python\pip"
    echo [OK] Cleaned build\python\pip
) else (
    echo [OK] No stale pip cache
)

rem ---------- 5. Gradle Assemble ----------
echo.
echo [6/7] Running Gradle assembleRelease (please wait)...
call "%GRADLE%" -p "%ANDROID%" :app:assembleRelease --console=plain
if errorlevel 1 (
    echo [!] Build failed! Check output above.
    goto :fail
)

rem ---------- 6. Output APK ----------
echo.
echo [7/7] Copying APK to project root...
set "APK_SRC=%APP%\build\outputs\apk\release\app-release.apk"
if not exist "%APK_SRC%" (
    echo [!] Error: APK output not found at %APK_SRC%
    goto :fail
)
del /q "%ROOT%BinanceETFMonitor-v*.apk" 2>nul
copy /y "%APK_SRC%" "%ROOT%BinanceETFMonitor-v%VN%-release.apk" >nul
if errorlevel 1 goto :fail
echo.
echo ============================================================
echo   [SUCCESS] APK build completed!
echo   Version: v%VN% (versionCode %VC%)
echo   File:    %ROOT%BinanceETFMonitor-v%VN%-release.apk
echo ============================================================
goto :end

:fail
echo.
echo [!] Build failed. No APK generated.
if not defined NOPAUSE pause
exit /b 1

:end
echo.
if not defined NOPAUSE pause
endlocal
exit /b 0

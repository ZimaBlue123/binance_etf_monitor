@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"

rem ============================================================
rem  rebuild_apk.bat — Binance ETF Monitor APK 一键构建
rem
rem  用法:
rem    rebuild_apk.bat            自动版本号构建 (默认, 推荐)
rem    rebuild_apk.bat same       保持当前版本号构建
rem    rebuild_apk.bat check      仅检查环境与资产同步状态
rem    任意模式追加 nopause       构建后不暂停 (例: rebuild_apk.bat same nopause)
rem
rem  流程: 检查环境 -> 同步 assets -> MD5 校验 -> 版本号处理
rem        -> 清理缓存 -> Gradle 构建 -> 拷贝 APK 至根目录
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

rem ---------- 环境检查 ----------
if not defined JAVA_HOME     set "JAVA_HOME=C:\Users\Administrator\jdk17\jdk-17"
if not defined ANDROID_HOME  set "ANDROID_HOME=C:\Users\Administrator\android-sdk"
set "GRADLE=C:\Gradle\gradle-8.7\bin\gradle.bat"

echo [1/7] 检查构建环境...
if not exist "%JAVA_HOME%\bin\java.exe" (
    echo [!] 错误: 未找到 JDK: %JAVA_HOME%
    echo     请安装 JDK 17 并配置 JAVA_HOME 环境变量
    goto :fail
)
if not exist "%ANDROID_HOME%\platform-tools" (
    echo [!] 错误: 未找到 Android SDK: %ANDROID_HOME%
    echo     请配置 ANDROID_HOME 环境变量
    goto :fail
)
if not exist "%GRADLE%" (
    echo [!] 错误: 未找到 Gradle: %GRADLE%
    echo     请安装 Gradle 8.7 至 C:\Gradle\gradle-8.7 或修改本脚本 GRADLE 路径
    goto :fail
)
if not exist "%ANDROID%\keystore\keystore.properties" (
    echo [!] 错误: 缺少签名配置 android\keystore\keystore.properties
    echo     请参考 android\BUILD.md 生成 keystore 并在本地配置
    goto :fail
)
echo [OK] JAVA_HOME     = %JAVA_HOME%
echo [OK] ANDROID_HOME  = %ANDROID_HOME%
echo [OK] Gradle        = %GRADLE%
echo [OK] 签名配置已就绪 (android\keystore\)

if /i "%MODE%"=="check" (
    echo.
    echo [*] 模式=check: 环境校验通过，未执行实际构建。
    echo     源码根目录 : %ROOT%config\
    echo     APK 资产目录 : %ASSETS%
    goto :end
)

rem ---------- 1. 同步资产 ----------
echo.
echo [2/7] 同步项目核心文件至 APK 资产目录...
xcopy /y /q "%ROOT%binance_etf_configurable.py" "%ASSETS%\" >nul
if errorlevel 4 goto :fail
xcopy /y /q /e /i "%ROOT%config" "%ASSETS%\config\" >nul
if errorlevel 4 goto :fail
xcopy /y /q "%ROOT%scripts\validate_strategy_assets.py" "%ASSETS%\scripts\" >nul
if errorlevel 4 goto :fail
xcopy /y /q "%ROOT%requirements.txt" "%ASSETS%\" >nul
if errorlevel 4 goto :fail
echo [OK] 资产同步完成 (binance_etf_configurable.py / config\ / scripts\ / requirements.txt)

rem ---------- 2. 校验资产同步 ----------
echo.
echo [3/7] 校验 etf_products.json 同步一致性...
for /f "tokens=*" %%h in ('certutil -hashfile "%ROOT%config\etf_products.json" MD5 ^| findstr /i /r "^[0-9a-f]*$"') do set "SRC_MD5=%%h"
for /f "tokens=*" %%h in ('certutil -hashfile "%ASSETS%\config\etf_products.json" MD5 ^| findstr /i /r "^[0-9a-f]*$"') do set "ASSET_MD5=%%h"
if not "!SRC_MD5!"=="!ASSET_MD5!" (
    echo [!] 错误: etf_products.json 同步不一致，终止构建
    echo     源文件 MD5   : !SRC_MD5!
    echo     APK 资产 MD5 : !ASSET_MD5!
    goto :fail
)
echo [OK] MD5 一致: !SRC_MD5!

rem ---------- 3. 版本号处理 ----------
echo.
if "%MODE%"=="same" (
    echo [4/7] 模式=same: 保持当前版本号不变...
    for /f "usebackq tokens=1,2" %%a in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%ANDROID%\bump_version.ps1" -GradleFile "%APP%\build.gradle" -Same`) do (
        set "VC=%%a"
        set "VN=%%b"
    )
) else (
    echo [4/7] 自动递增版本号，确保手机可覆盖安装...
    for /f "usebackq tokens=1,2" %%a in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%ANDROID%\bump_version.ps1" -GradleFile "%APP%\build.gradle"`) do (
        set "VC=%%a"
        set "VN=%%b"
    )
)
if not defined VN (
    echo [!] 错误: 获取版本号失败，请检查 android\app\build.gradle
    goto :fail
)
echo [OK] 目标版本: v%VN% (versionCode %VC%)

rem ---------- 4. 清理 ----------
echo.
echo [5/7] 停止 Gradle daemon 并清理缓存...
call "%GRADLE%" --stop >nul 2>&1
if exist "%APP%\build\python\pip" (
    rmdir /s /q "%APP%\build\python\pip"
    echo [OK] 已清理 build\python\pip
) else (
    echo [OK] 无残留 pip 缓存，跳过
)

rem ---------- 5. 构建 ----------
echo.
echo [6/7] 开始 Gradle 构建 (请耐心等待)...
call "%GRADLE%" -p "%ANDROID%" :app:assembleRelease --console=plain
if errorlevel 1 (
    echo [!] 构建失败，请查看上方错误输出
    goto :fail
)

rem ---------- 6. 输出 ----------
echo.
echo [7/7] 拷贝 APK 至根目录...
set "APK_SRC=%APP%\build\outputs\apk\release\app-release.apk"
if not exist "%APK_SRC%" (
    echo [!] 错误: 未找到产物 %APK_SRC%
    goto :fail
)
del /q "%ROOT%BinanceETFMonitor-v*.apk" 2>nul
copy /y "%APK_SRC%" "%ROOT%BinanceETFMonitor-v%VN%-release.apk" >nul
if errorlevel 1 goto :fail
echo.
echo ============================================================
echo   [SUCCESS] APK 构建完成!
echo   版本 : v%VN% (versionCode %VC%)
echo   产物 : %ROOT%BinanceETFMonitor-v%VN%-release.apk
echo ============================================================
goto :end

:fail
echo.
echo [!] 构建失败，未生成有效 APK。
if not defined NOPAUSE pause
exit /b 1

:end
echo.
if not defined NOPAUSE pause
endlocal
exit /b 0

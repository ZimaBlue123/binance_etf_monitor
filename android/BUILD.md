# Binance ETF Monitor — Android APK 构建说明

把 Python CLI 监控脚本封装为 Android APK(走 Termux 路线)。

## 目录结构

```
android/
├── app/
│   ├── build.gradle
│   └── src/main/
│       ├── AndroidManifest.xml
│       ├── java/com/Mavis/binanceetfmonitor/MainActivity.kt
│       ├── res/  (layout/launcher icon/colors/strings)
│       └── assets/project/        # 整个项目源码 + 启动脚本
│           ├── binance_etf_configurable.py
│           ├── config/{strategy_config.yaml, crypto_products.json, etf_products.json}
│           ├── scripts/validate_strategy_assets.py
│           ├── requirements.txt
│           ├── run_monitor.sh
│           ├── validate_assets.sh
│           └── setup-termux.sh   # Termux 一键初始化
├── build.gradle / settings.gradle / gradle.properties
├── gradle/wrapper/gradle-wrapper.properties
├── keystore/                       # release 签名 (不入 git)
│   ├── binance-etf-monitor.keystore
│   └── keystore.properties
└── regen-icons.ps1                 # 重生成启动图标的工具脚本
```

## 前置依赖

| 组件 | 路径 | 备注 |
|------|------|------|
| JDK 17 | `C:\Users\Administrator\jdk17\jdk-17` | Temurin 17 即可 |
| Android SDK | `C:\Users\Administrator\android-sdk` | platforms;android-34 + build-tools;34.0.0 + platform-tools |
| Gradle 8.7 | `C:\gradle\gradle-8.7\bin` | 也可走 wrapper |

环境变量(每次新开 shell 都要设):

```powershell
$env:JAVA_HOME = 'C:\Users\Administrator\jdk17\jdk-17'
$env:ANDROID_HOME = 'C:\Users\Administrator\android-sdk'
$env:Path = "$env:JAVA_HOME\bin;$env:ANDROID_HOME\platform-tools;$env:ANDROID_HOME\build-tools\34.0.0;C:\gradle\gradle-8.7\bin;$env:Path"
```

## 一次性:生成 keystore

```powershell
keytool -genkey -v -keystore keystore/binance-etf-monitor.keystore `
    -keyalg RSA -keysize 2048 -validity 10000 -alias upload `
    -storepass changeit_2026 -keypass changeit_2026 `
    -dname "CN=Binance ETF Monitor, OU=Personal, O=Independent, L=NA, ST=NA, C=CN"
```

同步生成 `keystore/keystore.properties`(build.gradle 会读):

```properties
storeFile=keystore/binance-etf-monitor.keystore
storePassword=changeit_2026
keyAlias=upload
keyPassword=changeit_2026
```

## 构建

```bash
# Debug
gradle assembleDebug
# 产物:app/build/outputs/apk/debug/app-debug.apk

# Release (自动用 keystore/keystore.properties 签名)
gradle assembleRelease
# 产物:app/build/outputs/apk/release/app-release.apk
```

## 升级图标

```bash
powershell -ExecutionPolicy Bypass -File regen-icons.ps1
```

`mipmap-anydpi-v26/ic_launcher.xml` 是 Android 8+ 的自适应图标,各 mipmap-*/ic_launcher.png 是低版本的位图 fallback。

## 更新 assets/project/

把改动同步拷到 `android/app/src/main/assets/project/` 后重新 build,否则 APK 里的还是老代码。

```powershell
Copy-Item -Recurse -Force ..\binance_etf_configurable.py  app\src\main\assets\project\
Copy-Item -Recurse -Force ..\config                       app\src\main\assets\project\
Copy-Item -Force       ..\scripts\validate_strategy_assets.py   app\src\main\assets\project\scripts\
Copy-Item -Force       ..\requirements.txt               app\src\main\assets\project\
```

## 在手机上跑

1. 装 APK(从 F-Droid 装 Termux,**不要装 Play 版**)
2. 启动 App, 点"① 一键安装 Termux"
3. 在 Termux 内执行 App 复制的命令:
   ```bash
   bash /data/data/com.Mavis.binanceetfmonitor/files/project/setup-termux.sh
   ```
4. 回到 App 点"③ 启动监控"

可选每日 06:00 自动跑:`setup-termux.sh` 输出末尾有 Termux:Tasker / crond 的配置示例。

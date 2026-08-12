# bump_version.ps1 — 递增 Android 版本号 (rebuild_apk.bat 内部调用)
#
# 用法:
#   powershell -File bump_version.ps1 -GradleFile <path> [-Same]
#
# 行为:
#   默认: versionCode +1, versionName 末位 +1 (如 1.2.3 -> 1.2.4),写回 build.gradle
#   -Same: 不修改文件,仅读取并输出当前版本号
#
# 输出: "<versionCode> <versionName>" (空格分隔,供批处理捕获)

param(
    [Parameter(Mandatory = $true)]
    [string]$GradleFile,
    [switch]$Same
)

$c = [System.IO.File]::ReadAllText($GradleFile)
$vcMatch = [regex]::Match($c, 'versionCode\s+(\d+)')
$vnMatch = [regex]::Match($c, "versionName\s+'([^']+)'")

if (-not $vcMatch.Success -or -not $vnMatch.Success) {
    Write-Error "无法从 build.gradle 解析 versionCode/versionName: $GradleFile"
    exit 1
}

$vc = [int]$vcMatch.Groups[1].Value
$vn = $vnMatch.Groups[1].Value

if (-not $Same) {
    # 版本号末位 +1 (如 1.2.3 -> 1.2.4), versionCode +1
    $parts = $vn.Split('.')
    $parts[$parts.Length - 1] = ([int]$parts[$parts.Length - 1] + 1).ToString()
    $newVn = $parts -join '.'
    $newVc = $vc + 1

    $c = $c -replace 'versionCode\s+\d+', ('versionCode ' + $newVc)
    $c = $c -replace "versionName\s+'[^']+'", ("versionName '" + $newVn + "'")
    # UTF-8 无 BOM 写回,避免 Gradle 解析 BOM 问题
    [System.IO.File]::WriteAllText($GradleFile, $c, (New-Object System.Text.UTF8Encoding($false)))
} else {
    $newVc = $vc
    $newVn = $vn
}

Write-Output ("{0} {1}" -f $newVc, $newVn)

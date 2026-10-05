# 打包成 Windows 可执行程序（onedir）。
# 用法: powershell -ExecutionPolicy Bypass -File build_exe.ps1 [-DistPath <目录>]
param(
    [string]$Python = "python",
    [string]$Name = "RainWorldSlugcatSimulation",
    [string]$DistPath
)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
if (-not $DistPath) { $DistPath = Join-Path $root "dist" }

# Ship layouts and the small UI icon set used by the sidebar. Rain World
# atlases, game audio, Workshop audio, and other copyrighted media are always
# read or extracted from the user's own local installation at runtime.
& $Python -m PyInstaller --noconfirm --clean --windowed --onedir --name $Name `
    --icon (Join-Path $root "slugcatpet\resources\icons\app_icon.ico") `
    --collect-submodules UnityPy `
    --distpath $DistPath `
    --workpath (Join-Path $root "build\work") `
    --specpath (Join-Path $root "build") `
    --add-data "$root\slugcatpet\resources\layouts;slugcatpet/resources/layouts" `
    --add-data "$root\slugcatpet\resources\icons;slugcatpet/resources/icons" `
    (Join-Path $root "run_slugcatpet.py")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }

# PyInstaller 会顺着 PATH 把某个 icuuc.dll（以及它依赖的 icudt78.dll）收进 _internal，
# 但这份 icuuc 的导出符号和 Qt6Core.dll 期望的不一致，会让 Qt 加载失败：
#   ImportError: DLL load failed while importing QtWidgets: 找不到指定的程序。
# 删掉这两个文件让 Qt 改用 Windows 自带的 icuuc.dll，程序即可正常启动。
$internal = Join-Path $DistPath "$Name\_internal"
Remove-Item -LiteralPath (Join-Path $internal "icuuc.dll") -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $internal "icudt78.dll") -ErrorAction SilentlyContinue

Write-Host "built: $(Join-Path $DistPath "$Name\$Name.exe")"

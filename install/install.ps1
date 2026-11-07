# doc-check 安装器
# 用法：pwsh install/install.ps1  或  powershell -ExecutionPolicy Bypass -File install/install.ps1
# 本文件保存为带 BOM 的 UTF-8：Windows PowerShell 5.1 读无 BOM 的文件时按系统 ANSI 码页解码，
# 脚本里的中文会变成乱码甚至解析失败。
$ErrorActionPreference = "Stop"

# 原生命令（python / pip）返回非零退出码时只设置 $LASTEXITCODE，
# 不直接抛 PowerShell 异常，这样下面的显式检查与中文提示才能生效。
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

$RepoRoot = Split-Path -Parent $PSScriptRoot
$InstallDir = Join-Path $RepoRoot "install"
$VenvDir = Join-Path $RepoRoot ".venv"

function Write-ErrLine([string]$Message) {
    [Console]::Error.WriteLine($Message)
}

function Write-TextNoBom([string]$Path, [string]$Text) {
    $Utf8 = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($Path, $Text, $Utf8)
}

Write-Host "== doc-check 安装器 ==" -ForegroundColor Cyan
Write-Host "仓库目录：$RepoRoot"

# --- 1. 选择解释器 ---
$Candidates = @(
    @{ Exe = "py";      Args = @("-3.12") },
    @{ Exe = "py";      Args = @("-3.11") },
    @{ Exe = "py";      Args = @("-3.13") },
    @{ Exe = "python3"; Args = @() },
    @{ Exe = "python";  Args = @() },
    @{ Exe = "py";      Args = @("-3") }
)

$PyExe = $null
foreach ($c in $Candidates) {
    $cmd = Get-Command $c.Exe -ErrorAction SilentlyContinue
    if (-not $cmd) { continue }
    $ver = ""
    try {
        $ver = & $c.Exe @($c.Args) -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
    } catch { continue }
    if ($LASTEXITCODE -ne 0 -or -not $ver) { continue }
    $ver = "$ver".Trim()
    if ($ver -notmatch '^\d+\.\d+$') { continue }
    $parts = $ver.Split('.')
    if ([int]$parts[0] -lt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -lt 9)) { continue }
    Write-Host "使用解释器：$($c.Exe) $($c.Args -join ' ')  (Python $ver)"
    $PyExe = @{ Exe = $c.Exe; Args = $c.Args; Ver = $ver }
    break
}

if (-not $PyExe) {
    Write-ErrLine "未找到 Python 3.9 及以上解释器。请安装 Python 3.11 或 3.12 后重试。"
    exit 1
}

# --- 2. 创建虚拟环境 ---
if (-not (Test-Path $VenvDir)) {
    Write-Host "创建虚拟环境 .venv ..."
    & $PyExe.Exe @($PyExe.Args) -m venv $VenvDir
}
$VenvPy = Join-Path $VenvDir "Scripts/python.exe"
if (-not (Test-Path $VenvPy)) {
    Write-ErrLine "虚拟环境创建失败：$VenvPy 不存在"
    exit 1
}

# --- 3. 安装依赖 ---
Write-Host "安装依赖 ..."
& $VenvPy -m pip install --upgrade pip | Out-Null
& $VenvPy -m pip install -r (Join-Path $RepoRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    Write-ErrLine "依赖安装失败。Python $($PyExe.Ver) 可能缺少预编译轮子，请改用 Python 3.11 或 3.12。"
    exit 1
}

# --- 4. 依赖自检 ---
& $VenvPy -c "import docx, openpyxl, pdfplumber, lxml"
if ($LASTEXITCODE -ne 0) {
    Write-ErrLine "依赖导入自检失败，请换用 Python 3.11 或 3.12 重建虚拟环境。"
    exit 1
}
Write-Host "依赖自检通过。"

# --- 5. 安装到各智能体 ---
$Adapters = Get-Content (Join-Path $InstallDir "adapters.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$Installed = @()
$Skipped = @()

foreach ($a in $Adapters.agents) {
    if ($a.mode -eq "manual") { $Skipped += $a.name; continue }

    $found = $false
    foreach ($p in $a.detect_paths) {
        $expanded = [Environment]::ExpandEnvironmentVariables(
            $p.Replace("~", $env:USERPROFILE))
        if (Test-Path $expanded) { $found = $true; break }
    }
    if (-not $found) {
        foreach ($cmdName in $a.detect_commands) {
            if (Get-Command $cmdName -ErrorAction SilentlyContinue) { $found = $true; break }
        }
    }
    if (-not $found) { $Skipped += $a.name; continue }

    $target = [Environment]::ExpandEnvironmentVariables(
        $a.skill_dir.Replace("~", $env:USERPROFILE))
    New-Item -ItemType Directory -Force -Path $target | Out-Null

    # 入口文件取仓库原件：SKILL.md 里有完整的三阶段流程，
    # 智能体真正读的是它，不能被下面的适配模板覆盖。
    foreach ($item in @($a.entry, "references", "scripts", "requirements.txt")) {
        $src = Join-Path $RepoRoot $item
        if (Test-Path $src) {
            Copy-Item $src -Destination $target -Recurse -Force
        }
    }
    Get-ChildItem -Path $target -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

    Write-TextNoBom (Join-Path $target "python-path.txt") $VenvPy

    $templatePath = Join-Path (Join-Path $InstallDir "adapters") "$($a.id).md"
    if (Test-Path $templatePath) {
        $template = (Get-Content $templatePath -Raw -Encoding UTF8).Replace("{{REPO_ROOT}}", $RepoRoot.Replace("\", "/"))
        Write-TextNoBom (Join-Path $target "AGENT.md") $template
    }

    $Installed += [pscustomobject]@{ Name = $a.name; Path = $target; Usage = $a.usage }
}

# --- 6. 输出结果 ---
Write-Host ""
Write-Host "== 安装完成 ==" -ForegroundColor Green
foreach ($i in $Installed) {
    Write-Host "[已安装] $($i.Name) -> $($i.Path)" -ForegroundColor Green
    Write-Host "          用法：$($i.Usage)"
}
if ($Skipped.Count -gt 0) {
    Write-Host ""
    Write-Host "未检测到（已跳过）：$($Skipped -join '、')" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "通用接入方式见 install/adapters/generic.md"
Write-Host "仓库目录：$RepoRoot"

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

function Show-Usage([switch]$ToError) {
    $lines = @(
        "用法：doc-check 安装器 [选项]",
        "  --update      覆盖已安装的副本，并清理已从仓库删除的文件",
        "  -h, --help    显示本帮助并退出"
    )
    foreach ($line in $lines) {
        if ($ToError) { Write-ErrLine $line } else { Write-Host $line }
    }
}

function Get-PythonVersion([string]$Exe, [string[]]$ExeArgs) {
    # 取解释器版本。判定只看两样：退出码必须是 0，标准输出里必须有一行正好是「主.次」。
    #
    # Windows PowerShell 5.1 有个坑：原生命令只要往 stderr 写一行，
    # $ErrorActionPreference="Stop" 就会把它变成终止性的 NativeCommandError，
    # 整个探测被当成失败——一个只是「启动时提醒一句」的 Python 就被判成没装 Python。
    # 这里临时把 ErrorActionPreference 降为 Continue：stderr 被 2>$null 丢掉，
    # 不参与判断；成不成只看退出码与标准输出里的版本号。
    $prev = $ErrorActionPreference
    $out = $null
    $code = 1
    try {
        $ErrorActionPreference = "Continue"
        $out = & $Exe @ExeArgs -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prev
    }
    if ($code -ne 0) { return "" }
    foreach ($line in @($out)) {
        $text = "$line".Trim()
        if ($text -match '^\d+\.\d+$') { return $text }
    }
    return ""
}

# 参数是显式的：--update 有明确含义，拼错的参数直接报错退出，
# 不会被静默当成「正常安装」。
$Update = $false
foreach ($arg in $args) {
    if ($arg -eq "--update") { $Update = $true; continue }
    if ($arg -eq "-h" -or $arg -eq "--help") { Show-Usage; exit 0 }
    Write-ErrLine "未知参数：$arg"
    Write-ErrLine "可用参数：--update、-h/--help"
    Show-Usage -ToError
    exit 2
}

Write-Host "== doc-check 安装器 ==" -ForegroundColor Cyan
Write-Host "仓库目录：$RepoRoot"
if ($Update) {
    Write-Host "模式：更新（覆盖已安装的副本，并清理已从仓库删除的文件）"
} else {
    Write-Host "模式：安装（写入技能目录，已存在的同名文件会被覆盖）"
}

# --- 1. 选择解释器 ---
#
# 候选顺序与 install.sh 完全一致：先用启动器指定版本，再试带版本号的可执行名，
# 最后才是通用的 python3 / python / py -3。优先 3.11 与 3.12，
# 因为 lxml 与 pdfplumber 在这些版本上的预编译轮子最完整。
$Candidates = @(
    @{ Exe = "py";         Args = @("-3.12") },
    @{ Exe = "py";         Args = @("-3.11") },
    @{ Exe = "py";         Args = @("-3.13") },
    @{ Exe = "python3.12"; Args = @() },
    @{ Exe = "python3.11"; Args = @() },
    @{ Exe = "python3.13"; Args = @() },
    @{ Exe = "python3";    Args = @() },
    @{ Exe = "python";     Args = @() },
    @{ Exe = "py";         Args = @("-3") }
)

$PyExe = $null
foreach ($c in $Candidates) {
    if (-not (Get-Command $c.Exe -ErrorAction SilentlyContinue)) { continue }
    $ver = Get-PythonVersion $c.Exe $c.Args
    if (-not $ver) { continue }
    $parts = $ver.Split('.')
    if ([int]$parts[0] -lt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -lt 9)) { continue }
    $label = $c.Exe
    if ($c.Args.Count -gt 0) { $label = "$($c.Exe) $($c.Args -join ' ')" }
    Write-Host "使用解释器：$label  (Python $ver)"
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
    $prev = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $PyExe.Exe @($PyExe.Args) -m venv $VenvDir
    } finally {
        $ErrorActionPreference = $prev
    }
}
$VenvPy = Join-Path $VenvDir "Scripts/python.exe"
if (-not (Test-Path $VenvPy)) {
    Write-ErrLine "虚拟环境创建失败：$VenvPy 不存在"
    exit 1
}

# --- 3. 安装依赖 ---
Write-Host "安装依赖 ..."
$prev = $ErrorActionPreference
try {
    $ErrorActionPreference = "Continue"
    & $VenvPy -m pip install --upgrade pip | Out-Null
    & $VenvPy -m pip install -r (Join-Path $RepoRoot "requirements.txt")
    $pipCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $prev
}
if ($pipCode -ne 0) {
    Write-ErrLine "依赖安装失败。Python $($PyExe.Ver) 可能缺少预编译轮子，请改用 Python 3.11 或 3.12。"
    exit 1
}

# --- 4. 依赖自检 ---
$prev = $ErrorActionPreference
try {
    $ErrorActionPreference = "Continue"
    & $VenvPy -c "import docx, openpyxl, pdfplumber, lxml"
    $importCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $prev
}
if ($importCode -ne 0) {
    Write-ErrLine "依赖导入自检失败，请换用 Python 3.11 或 3.12 重建虚拟环境。"
    exit 1
}
Write-Host "依赖自检通过。"

# --- 5. 安装到各智能体 ---
#
# 装到智能体目录这一步由 install/install_skill.py 完成：
# install.sh 调用的是同一个文件，两个安装器的行为因此一致。
$updateArgs = @()
if ($Update) { $updateArgs = @("--update") }
$prev = $ErrorActionPreference
try {
    $ErrorActionPreference = "Continue"
    & $VenvPy (Join-Path $InstallDir "install_skill.py") --repo-root $RepoRoot --venv-py $VenvPy @updateArgs
    $installCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $prev
}
if ($installCode -ne 0) {
    Write-ErrLine "安装到智能体目录失败。"
    exit 1
}

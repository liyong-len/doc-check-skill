# doc-check 一键安装引导脚本（Windows）
#
# 用法（PowerShell 5.1 或 pwsh 7）：
#   irm https://raw.githubusercontent.com/liyong-len/doc-check-skill/main/install/bootstrap.ps1 | iex
#
# 带参数（先把脚本存下来再跑，管道里传不了参数）：
#   irm -OutFile bootstrap.ps1 https://raw.githubusercontent.com/liyong-len/doc-check-skill/main/install/bootstrap.ps1
#   powershell -ExecutionPolicy Bypass -File bootstrap.ps1 --target-root C:\scratch-home
#
# 这个脚本只做两件事：
#   1. 把仓库取到 ~\.doc-check\repo（更新时保留已有的 .venv）
#   2. 调用仓库里的 install/install.ps1 完成真正的安装
#
# 参数原样转交给 install/install.ps1：--update、--dry-run、--status、--target-root。
#
# 环境变量：
#   DOC_CHECK_HOME         仓库存放目录的父目录，默认 ~\.doc-check
#   DOC_CHECK_REPO_URL     仓库压缩包的下载地址，默认 GitHub 上的 main 分支
#
# 注意：虚拟环境建在 ~\.doc-check\repo\.venv 里，技能目录里的 python-path.txt
# 指向它。删掉 ~\.doc-check 会让已装的技能失效——要换机器就重跑一次本脚本。
$ErrorActionPreference = "Stop"

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$RepoSlug = "liyong-len/doc-check-skill"
$DefaultBranch = "main"
$DefaultUrl = "https://codeload.github.com/$RepoSlug/zip/refs/heads/$DefaultBranch"

function Write-ErrLine([string]$Message) {
    [Console]::Error.WriteLine($Message)
}

function Get-HomeDir {
    if ($env:USERPROFILE) { return $env:USERPROFILE }
    if ($env:HOME) { return $env:HOME }
    return $HOME
}

$InstallRoot = if ($env:DOC_CHECK_HOME) { $env:DOC_CHECK_HOME } else { Join-Path (Get-HomeDir) ".doc-check" }
$RepoDir = Join-Path $InstallRoot "repo"
$RepoUrl = if ($env:DOC_CHECK_REPO_URL) { $env:DOC_CHECK_REPO_URL } else { $DefaultUrl }

function Show-Usage {
    $lines = @(
        "用法：doc-check 引导安装 [选项]",
        "  --update      覆盖已安装的副本，并清理已从仓库删除的文件",
        "  --dry-run     只打印将写入的目录，不写任何文件",
        "  --status      打印家目录根、各智能体目录与残留情况",
        "  --target-root <路径>  改「~ 展开到哪个根目录」，不改 HOME/USERPROFILE",
        "  -h, --help    显示本帮助并退出",
        "",
        "本脚本会先把仓库下载到：",
        "  $RepoDir",
        "然后调用仓库里的 install/install.ps1 完成安装。"
    )
    foreach ($line in $lines) { Write-Host $line }
}

$PassArgs = @()
$argList = @($args)
for ($i = 0; $i -lt $argList.Count; $i++) {
    $arg = $argList[$i]
    if ($arg -eq "--update" -or $arg -eq "--dry-run" -or $arg -eq "--status") {
        $PassArgs += $arg; continue
    }
    if ($arg -eq "--target-root") {
        if ($i + 1 -ge $argList.Count) {
            Write-ErrLine "缺少 --target-root 的路径参数"
            Show-Usage
            exit 2
        }
        $i++
        $PassArgs += "--target-root"
        $PassArgs += $argList[$i]
        continue
    }
    if ($arg -eq "-h" -or $arg -eq "--help") { Show-Usage; exit 0 }
    Write-ErrLine "未知参数：$arg"
    Write-ErrLine "可用参数：--update、--dry-run、--status、--target-root"
    Show-Usage
    exit 2
}

Write-Host "== doc-check 引导安装 =="
Write-Host "仓库目录：$RepoDir"
Write-Host "下载地址：$RepoUrl"

$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("doc-check-bootstrap-" + [System.Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tmp -Force | Out-Null
try {
    $zipPath = Join-Path $tmp "repo.zip"
    Write-Host "下载仓库 ..."
    try {
        Invoke-WebRequest -Uri $RepoUrl -OutFile $zipPath -UseBasicParsing
    } catch {
        Write-ErrLine "下载失败：$RepoUrl"
        Write-ErrLine $_.Exception.Message
        Write-ErrLine "网络不通就重试几次；国内网络访问 GitHub 不稳时尤其常见。"
        exit 1
    }

    Write-Host "解压 ..."
    $extractDir = Join-Path $tmp "extract"
    Expand-Archive -Path $zipPath -DestinationPath $extractDir -Force

    # 压缩包里的顶层目录名带分支名，不写死，找唯一的那个目录。
    $src = Get-ChildItem -Path $extractDir -Directory | Select-Object -First 1
    if (-not $src) {
        Write-ErrLine "压缩包结构不对：解压后没找到目录。"
        exit 1
    }
    if (-not (Test-Path (Join-Path $src.FullName "install\install.ps1"))) {
        Write-ErrLine "压缩包内容不对：找不到 install\install.ps1。"
        exit 1
    }

    # 更新时保留已有的 .venv：虚拟环境里的脚本记着它自己的绝对路径，
    # 而这个路径（~\.doc-check\repo\.venv）前后不变，所以搬回去还能用。
    # 换句话说：先搬走，再换掉仓库目录，再搬回来。
    $venvStash = Join-Path $tmp "venv"
    $venvDir = Join-Path $RepoDir ".venv"
    $hadVenv = $false
    if (Test-Path $venvDir) {
        Move-Item -Path $venvDir -Destination $venvStash -Force
        $hadVenv = $true
    }

    if (Test-Path $RepoDir) { Remove-Item -Path $RepoDir -Recurse -Force }
    New-Item -ItemType Directory -Path (Split-Path -Parent $RepoDir) -Force | Out-Null
    Move-Item -Path $src.FullName -Destination $RepoDir -Force

    if ($hadVenv) {
        Move-Item -Path $venvStash -Destination $venvDir -Force
        Write-Host "已保留原有虚拟环境。"
    }

    Write-Host ""
    & (Join-Path $RepoDir "install\install.ps1") @PassArgs

    Write-Host ""
    Write-Host "仓库位置：$RepoDir"
    Write-Host "技能依赖该目录下的虚拟环境，请勿删除。"
} finally {
    Remove-Item -Path $tmp -Recurse -Force -ErrorAction SilentlyContinue
}

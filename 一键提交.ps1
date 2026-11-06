[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Message
)

$ErrorActionPreference = 'Stop'
$repoRoot = $PSScriptRoot
Set-Location -LiteralPath $repoRoot

function Write-Step {
    param([string]$Text)
    Write-Host ""
    Write-Host $Text -ForegroundColor Cyan
}

function Fail {
    param([string]$Text)
    Write-Host ""
    Write-Host "[错误] $Text" -ForegroundColor Red
    exit 1
}

function Get-SystemProxy {
    try {
        $settings = Get-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -ErrorAction Stop
    }
    catch {
        return $null
    }

    if ($settings.ProxyEnable -ne 1 -or [string]::IsNullOrWhiteSpace($settings.ProxyServer)) {
        return $null
    }

    $server = [string]$settings.ProxyServer

    if ($server -match '=') {
        # 兼容 http=host:port;https=host:port 这种写法。
        $httpPart = $server -split ';' | Where-Object { $_ -match '^\s*http=' } | Select-Object -First 1
        if ($httpPart) {
            $server = ($httpPart -split '=', 2)[1]
        }
        else {
            $httpsPart = $server -split ';' | Where-Object { $_ -match '^\s*https=' } | Select-Object -First 1
            if ($httpsPart) {
                $server = ($httpsPart -split '=', 2)[1]
            }
            else {
                return $null
            }
        }
    }

    $server = $server.Trim()
    if ($server -notmatch '^https?://') {
        $server = "http://$server"
    }
    return $server
}

function Show-Success {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Green
    Write-Host "  已同步到 GitHub" -ForegroundColor Green
    Write-Host "============================================" -ForegroundColor Green
    Write-Host "  仓库: https://github.com/loktindyi/autoscrcpy"
    Write-Host ""
}

# 优先使用 PATH 中的 Git；winget 安装的 Git 可能还没进入当前终端环境。
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    $gitDirs = @(
        (Join-Path $env:ProgramFiles 'Git\cmd'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Git\cmd')
    )
    foreach ($dir in $gitDirs) {
        if (Test-Path -LiteralPath (Join-Path $dir 'git.exe')) {
            $env:Path = "$dir;$env:Path"
            break
        }
    }
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Fail '没有找到 Git，请先安装 Git for Windows。'
}

& git rev-parse --is-inside-work-tree *> $null
if ($LASTEXITCODE -ne 0) {
    Fail "当前目录不是 Git 仓库：$repoRoot"
}

Write-Host ""
Write-Host "============================================" -ForegroundColor DarkGray
Write-Host "  AutoScrcpy 一键提交" -ForegroundColor White
Write-Host "============================================" -ForegroundColor DarkGray
Write-Host ""

Write-Step "[1/3] 暂存所有更改..."
& git add -A
if ($LASTEXITCODE -ne 0) {
    Fail 'git add 失败。'
}

& git diff --cached --quiet
if ($LASTEXITCODE -eq 0) {
    $hasChanges = $false
}
elseif ($LASTEXITCODE -eq 1) {
    $hasChanges = $true
}
else {
    Fail '无法检查暂存区变更。'
}

if ($hasChanges) {
    Write-Host ""
    Write-Host "将要提交的文件："
    & git diff --cached --stat
    if ($LASTEXITCODE -ne 0) {
        Fail '无法读取暂存区变更。'
    }

    if ([string]::IsNullOrWhiteSpace($Message)) {
        Write-Host ""
        $Message = Read-Host "请输入提交说明（直接回车自动生成）"
    }
    if ([string]::IsNullOrWhiteSpace($Message)) {
        $Message = "自动提交 $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    }

    Write-Step "[2/3] 提交..."
    & git commit -m $Message
    if ($LASTEXITCODE -ne 0) {
        Fail 'git commit 失败。'
    }
}
else {
    Write-Host ""
    Write-Host "没有需要提交的更改，检查是否有未推送的提交..."
}

$branch = (& git symbolic-ref --short HEAD 2>$null | Select-Object -First 1)
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($branch)) {
    Fail '当前不在任何分支上，无法自动推送。'
}
$branch = $branch.Trim()

Write-Step "[3/3] 推送到 origin/$branch ..."
& git push -u origin $branch
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "直接推送失败，尝试通过系统代理重试..." -ForegroundColor Yellow

    $proxy = Get-SystemProxy
    if ([string]::IsNullOrWhiteSpace($proxy)) {
        Fail '推送失败，且没有检测到可用的系统代理。请检查网络，或确认远程仓库地址是否正确。'
    }

    Write-Host "使用系统代理：$proxy" -ForegroundColor Yellow
    & git -c "http.proxy=$proxy" push -u origin $branch
    if ($LASTEXITCODE -ne 0) {
        Fail '通过代理推送仍然失败。如果提示 rejected，请先执行 git pull --rebase 后再试。'
    }
}

Show-Success
exit 0

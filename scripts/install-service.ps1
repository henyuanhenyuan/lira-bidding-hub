# 用 NSSM 把 LIRA 注册为 Windows 服务（需先安装 nssm 并加入 PATH）
# 用法（管理员 PowerShell）：
#   .\scripts\install-service.ps1
#   .\scripts\install-service.ps1 -Name lira-test -Port 8011

param(
    [string]$Name = "lira",
    [int]$Port = 8010
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = (Get-Command python).Source

if (-not (Get-Command nssm -ErrorAction SilentlyContinue)) {
    throw "未找到 nssm。请先下载 nssm.exe 并加入 PATH。"
}

Write-Host "注册服务 $Name -> $root (port $Port)"

nssm install $Name $python "-m uvicorn app.main:app --host 127.0.0.1 --port $Port"
nssm set $Name AppDirectory $root
nssm set $Name AppStdout "$root\data\service-out.log"
nssm set $Name AppStderr "$root\data\service-err.log"
nssm set $Name AppRotateFiles 1
nssm set $Name AppRotateBytes 10485760
nssm set $Name Start SERVICE_DELAYED_AUTO_START
nssm set $Name AppExit Default Restart
nssm set $Name AppRestartDelay 5000

Write-Host "完成。启动： nssm start $Name"
Write-Host "注意：data 目录不要放在 OneDrive/坚果云同步目录下，会锁库。"

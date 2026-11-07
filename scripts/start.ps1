param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $projectPython)) {
    throw '缺少虚拟环境，请先按照 README.md 安装依赖。'
}
Push-Location -LiteralPath (Join-Path $projectRoot 'frontend')
try {
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw '前端构建失败。' }
} finally { Pop-Location }
Write-Host "订单工作台：http://127.0.0.1:$Port"
& $projectPython -m uvicorn backend.app.main:app --host 127.0.0.1 --port $Port
exit $LASTEXITCODE

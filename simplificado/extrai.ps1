$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$appHtmlPath = Join-Path $scriptDir "app.html"
$cifrasDir = Join-Path $scriptDir "cifras"

if (-not (Test-Path $appHtmlPath)) {
    Write-Error "Arquivo app.html nao encontrado em: $appHtmlPath"
    exit 1
}

if (-not (Test-Path $cifrasDir)) {
    New-Item -ItemType Directory -Path $cifrasDir | Out-Null
}

$content = Get-Content -Path $appHtmlPath -Raw -Encoding UTF8

$match = [regex]::Match($content, '(?s)<musicas>.*?</musicas>')
if (-not $match.Success) {
    Write-Error "Tag <musicas> nao encontrada em app.html"
    exit 1
}

[xml]$xml = $match.Value

$invalidChars = [System.IO.Path]::GetInvalidFileNameChars()
$totalGerado = 0

foreach ($musica in $xml.musicas.musica) {
    $titulo = "$($musica.titulo)".Trim()
    $tom = "$($musica.tom)".Trim()
    $cifra = $musica.cifra.InnerText.Trim()

    if ([string]::IsNullOrWhiteSpace($titulo)) { continue }

    $nomeArquivo = $titulo
    foreach ($c in $invalidChars) {
        $nomeArquivo = $nomeArquivo.Replace([string]$c, "_")
    }

    $caminhoArquivo = Join-Path $cifrasDir ($nomeArquivo + ".txt")

    $linhas = @($titulo, "TOM:$tom", "", "", $cifra)

    Set-Content -Path $caminhoArquivo -Value ($linhas -join "`r`n") -Encoding UTF8
    $totalGerado++
    Write-Host "Gerado: $caminhoArquivo"
}

Write-Host ""
Write-Host "Concluido. $totalGerado arquivo(s) gerado(s) em: $cifrasDir"

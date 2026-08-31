$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$cifrasDir = Join-Path $scriptDir "cifras"
$telaCelPath = Join-Path $scriptDir "telaCel.html"

if (-not (Test-Path $cifrasDir)) {
    Write-Error "Pasta cifras nao encontrada em: $cifrasDir"
    exit 1
}

if (-not (Test-Path $telaCelPath)) {
    Write-Error "Arquivo telaCel.html nao encontrado em: $telaCelPath"
    exit 1
}

$arquivos = Get-ChildItem -Path $cifrasDir -Filter "*.txt" | Sort-Object Name

$sb = New-Object System.Text.StringBuilder
[void]$sb.AppendLine("<musicas>")

foreach ($arquivo in $arquivos) {
    $conteudo = (Get-Content -Path $arquivo.FullName -Raw -Encoding UTF8).TrimEnd("`r", "`n")
    $conteudoSeguro = $conteudo -replace '\]\]>', ']]]]><![CDATA[>'

    [void]$sb.AppendLine("<musica>")
    [void]$sb.AppendLine("<![CDATA[")
    [void]$sb.AppendLine($conteudoSeguro)
    [void]$sb.AppendLine("]]>")
    [void]$sb.AppendLine("</musica>")
    [void]$sb.AppendLine("")
}

[void]$sb.AppendLine("</musicas>")

$novoBloco = $sb.ToString().TrimEnd()

$htmlContent = Get-Content -Path $telaCelPath -Raw -Encoding UTF8

$pattern = '(?s)<musicas>.*?</musicas>'
if (-not [regex]::IsMatch($htmlContent, $pattern)) {
    Write-Error "Tag <musicas> nao encontrada em telaCel.html"
    exit 1
}

$evaluator = [System.Text.RegularExpressions.MatchEvaluator]{ param($match) $novoBloco }
$htmlContent = [regex]::Replace($htmlContent, $pattern, $evaluator, 1)

Set-Content -Path $telaCelPath -Value $htmlContent -Encoding UTF8 -NoNewline

Write-Host "Concluido. $($arquivos.Count) musica(s) incluida(s) em: $telaCelPath"

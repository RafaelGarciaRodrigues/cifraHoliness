# Fonte: simplificado/cifras/*.txt (mesma pasta usada por inclui.ps1)
# Destino: simplificado/nodeMCU/data/musicas.json
#
# Gera o dataset de letras consumido pelo firmware do NodeMCU ESP8266/ESP-12 (ver
# simplificado/spec_esp32.md,
# secao 4.2 e 5.1). Cada musica vira { titulo, linhas: [{tipo, texto}, ...] }, com "linhas"
# cobrindo o corpo ORIGINAL (nao quebrado) do .txt, na mesma ordem/indice que telaCel.html usa
# internamente (musica.conteudo.split(/\r?\n/)) - isso e o que garante que o indice de linha
# enviado pelo celular bata com o indice usado aqui.
#
# A classificacao acorde/letra de cada linha reimplementa fielmente CHORD_TOKEN_RE/isChordToken/
# isChordLine de telaCel.html. Qualquer mudanca nessa logica em telaCel.html precisa ser
# replicada aqui tambem, senao a classificacao diverge entre celular e ESP32.

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$cifrasDir = Join-Path $scriptDir "cifras"
$outDir = Join-Path $scriptDir "nodeMCU\data"
$outPath = Join-Path $outDir "musicas.json"

if (-not (Test-Path $cifrasDir)) {
    Write-Error "Pasta cifras nao encontrada em: $cifrasDir"
    exit 1
}

if (-not (Test-Path $outDir)) {
    New-Item -ItemType Directory -Path $outDir -Force | Out-Null
}

# ===== Identificacao de cifras (porta fiel de telaCel.html) =====

# Os codigos Unicode de "º" (U+00BA) e "°" (U+00B0) sao usados via [char] em vez do
# caractere literal para nao depender do encoding com que o proprio .ps1 for lido.
$MASC_ORD = [char]0x00BA  # º
$DEGREE = [char]0x00B0    # °

$ROOT = '(?:[A-G](?:#|b)?)'
$SUF = '(?:m|maj7|M7|7M|maj|dim7|dim|' + $MASC_ORD + '7|' + $MASC_ORD + '|' + $DEGREE + '7|' + $DEGREE + '|aug|\+|sus2|sus4|add9|add11|add13|2|4|5|6|7|9|11|13)'
$ALT_UNIT = '(?:b5|#5|5\+|\+5|5-|b6|#6|6|b7|#7|7|b9|#9|9\+|\+9|9-|#11|11\+|\+11|b13|13\+|\+13|13-|9|11|13)'
$ALT_GROUP = '\(\s*' + $ALT_UNIT + '(?:\s*[/,]\s*' + $ALT_UNIT + ')*\s*\)'
$ALT = '(?:' + $ALT_GROUP + '|' + $ALT_UNIT + ')*'
$BASS = '(?:/' + $ROOT + ')?'
$CHORD_TOKEN_RE = '^(?:N\.C\.|' + $ROOT + '(?:' + $SUF + '|' + $ALT + ')*' + $BASS + ')$'

function Test-ChordToken {
    param([string]$tok)
    if ([string]::IsNullOrEmpty($tok)) { return $false }
    $t = $tok.Trim()
    $t = $t.Replace([char]0x00A0, ' ')
    if ($t.Length -gt 0 -and $t[0] -eq '[' -and $t[$t.Length - 1] -eq ']') {
        $t = $t.Substring(1, $t.Length - 2).Trim()
    } else {
        $t = $t -replace '^\[', ''
        $t = $t -replace '\]$', ''
    }
    $t = $t -replace '^[,.;:!?]+', ''
    $t = $t -replace '[,.;:!?]+$', ''
    return [regex]::IsMatch($t, $CHORD_TOKEN_RE)
}

function Test-ChordLine {
    param([string]$line)
    $norm = $line.Replace([char]0x00A0, ' ').Trim()
    $tokens = @([regex]::Split($norm, '\s+') | Where-Object { $_ -ne '' })
    if ($tokens.Count -eq 0) { return $false }
    $valid = 0
    foreach ($tok in $tokens) { if (Test-ChordToken $tok) { $valid++ } }
    if ($valid -eq 0) { return $false }
    if ($valid -eq $tokens.Count) { return $true }
    return (($valid -ge 2) -and (($valid / $tokens.Count) -ge 0.5))
}

# ===== Leitura das musicas (mesma logica de indexacao de telaCel.html) =====

$arquivos = Get-ChildItem -Path $cifrasDir -Filter "*.txt" | Sort-Object Name
$musicas = @()

foreach ($arquivo in $arquivos) {
    $conteudo = (Get-Content -Path $arquivo.FullName -Raw -Encoding UTF8).Trim()
    $linhas = [regex]::Split($conteudo, '\r?\n')
    $titulo = $linhas[0].Trim()

    if ($linhas.Count -gt 1) {
        $corpo = ($linhas[1..($linhas.Count - 1)] -join "`n").Trim()
    } else {
        $corpo = ""
    }

    $linhasOriginais = [regex]::Split($corpo, '\r?\n')

    $linhasClassificadas = @()
    foreach ($l in $linhasOriginais) {
        $tipo = if (Test-ChordLine $l) { "acorde" } else { "letra" }
        $linhasClassificadas += [PSCustomObject]@{ tipo = $tipo; texto = $l }
    }

    $musicas += [PSCustomObject]@{ titulo = $titulo; linhas = $linhasClassificadas }
}

$json = $musicas | ConvertTo-Json -Depth 6 -Compress
$utf8SemBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($outPath, $json, $utf8SemBom)

Write-Host "Concluido. $($musicas.Count) musica(s) gravada(s) em: $outPath"

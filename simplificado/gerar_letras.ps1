# Fonte: simplificado/cifras/*.txt (mesma pasta usada por inclui.ps1)
# Destino: simplificado/nodeMCU/data/musicas.json + simplificado/nodeMCU/data/index.html
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
#
# Tambem gera simplificado/telaCel.html como nodeMCU/data/index.html: o NodeMCU passa a servir
# o proprio telaCel.html em GET / (ver spec_esp32.md) - abrir via http://192.168.4.1/ em vez de um
# arquivo local resolve o navigator.wakeLock, que o Chrome recusa em paginas file://. Rode
# inclui.ps1 ANTES deste script se \cifras mudou, senao o index.html sai com o conteudo antigo.
# Nao e uma copia 1:1: insere um fallback CSS pros icones (bootstrap-icons vem de CDN, que nao
# carrega offline - ver rc.md secao ICONES), so nesse arquivo, sem alterar telaCel.html.

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$cifrasDir = Join-Path $scriptDir "cifras"
$telaCelPath = Join-Path $scriptDir "telaCel.html"
$outDir = Join-Path $scriptDir "nodeMCU\data"
$outPath = Join-Path $outDir "musicas.json"
$indexPath = Join-Path $outDir "index.html"

if (-not (Test-Path $cifrasDir)) {
    Write-Error "Pasta cifras nao encontrada em: $cifrasDir"
    exit 1
}

if (-not (Test-Path $telaCelPath)) {
    Write-Error "Arquivo telaCel.html nao encontrado em: $telaCelPath"
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

# -Recurse: \cifras agora pode ter subpastas de grupo (ver rc.md secao GRUPOS / inclui.ps1). Sem
# isso, musicas dentro de uma subpasta ficariam fora do musicas.json e a sincronia com letras.html
# quebraria pra elas especificamente (letras.html nao acharia o titulo no dataset).
$arquivos = Get-ChildItem -Path $cifrasDir -Filter "*.txt" -Recurse | Sort-Object FullName
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

    # <intro>/</intro> ficam em linhas proprias (ver simplificado/spec_esp32.md). As linhas ENTRE
    # os marcadores (exclusive) recebem intro=true; os marcadores em si nunca aparecem em
    # letras.html (telaCel.html.js confere pelo texto literal "<intro>"/"</intro>").
    $linhasClassificadas = @()
    $dentroIntro = $false
    foreach ($l in $linhasOriginais) {
        $tTrim = $l.Trim()
        if ($tTrim -eq '<intro>') {
            $dentroIntro = $true
            $introFlag = $false
        } elseif ($tTrim -eq '</intro>') {
            $dentroIntro = $false
            $introFlag = $false
        } else {
            $introFlag = $dentroIntro
        }
        $tipo = if (Test-ChordLine $l) { "acorde" } else { "letra" }
        $linhasClassificadas += [PSCustomObject]@{ tipo = $tipo; texto = $l; intro = $introFlag }
    }

    $musicas += [PSCustomObject]@{ titulo = $titulo; linhas = $linhasClassificadas }
}

$json = $musicas | ConvertTo-Json -Depth 6 -Compress
$utf8SemBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($outPath, $json, $utf8SemBom)

# index.html nao e uma copia 1:1 de telaCel.html: os icones (<i class="bi bi-...">) vem do
# Bootstrap Icons via CDN, que nao carrega na rede do NodeMCU (sem internet - ver rc.md secao
# ICONES). Insere um fallback em CSS puro *antes* do <link> do CDN: se o CDN carregar, suas regras
# (que vem depois no documento) ganham a cascata e os icones bonitos aparecem normalmente; se nao
# carregar (uso real via NodeMCU), so o fallback fica valendo e mostra os caracteres Unicode no
# lugar. Cobre os 9 icones listados no rc.md (secao ICONES) + bi-x (limpar selecao), bi-check2
# (feedback de "link copiado" do botao compartilhar) e bi-node-plus-fill (icone de grupos, secao
# GRUPOS), que usam o mesmo tipo de fallback. bi-share NAO esta aqui: foi pedido pros dois
# arquivos (telaCel.html e index.html), entao o fallback dele vive direto em telaCel.html (ver
# <style> antes do <link> do CDN la) e chega em index.html automaticamente por ja estar no
# conteudo copiado - duplicar aqui so arriscaria os dois valores divergirem no futuro.
$telaCelConteudo = Get-Content -Path $telaCelPath -Raw -Encoding UTF8

$fallbackIcones = @'
<style>
/* Fallback offline dos icones (ver rc.md secao ICONES): bootstrap-icons.min.css vem de CDN e nao
   carrega sem internet. Fica ANTES do <link> do CDN de proposito - se o CDN carregar, suas regras
   (que vem depois) ganham a cascata; senao, essas ficam valendo. */
.bi-music-note::before { content: "\266A"; }
.bi-music-note-beamed::before { content: "\266B"; }
.bi-play::before { content: "\25B7"; }
.bi-pause::before { content: "\23F8"; }
.bi-plus::before { content: "\29FE"; }
.bi-dash::before { content: "\29FF"; }
.bi-cloud-download::before { content: "\1F863"; }
.bi-funnel::before { content: "\2730"; }
.bi-x::before { content: "\2715"; }
.bi-check2::before { content: "\2713"; }
.bi-node-plus-fill::before { content: "\2630"; }
</style>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css">
'@

$marcadorCdn = '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css">'
if (-not $telaCelConteudo.Contains($marcadorCdn)) {
    Write-Error "Link do bootstrap-icons nao encontrado em telaCel.html (verifique se a versao/URL mudou) - ajuste `$marcadorCdn` em gerar_letras.ps1"
    exit 1
}
$indexConteudo = $telaCelConteudo.Replace($marcadorCdn, $fallbackIcones)

$utf8SemBomIndex = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($indexPath, $indexConteudo, $utf8SemBomIndex)

Write-Host "Concluido. $($musicas.Count) musica(s) gravada(s) em: $outPath"
Write-Host "Gerado telaCel.html (com fallback de icones offline) para: $indexPath"

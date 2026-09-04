# Ferramenta interativa: percorre \cifras (e subpastas), descobre qual arquivo esta aberto no
# Bloco de Notas / Notepad++ (ou similar) no momento, e quebra cada linha de letra que contenha
# ";" em duas linhas - quebrando a linha de cifra logo acima na MESMA coluna, pra manter o
# alinhamento acorde/letra (ver rc.md secao AJUSTE DAS Cifras). So processa a PRIMEIRA ";" de cada
# linha por execucao: se sobrar mais de uma ";" na mesma linha, a proxima fica pra rodada seguinte
# do loop - por isso o script fica perguntando se quer rodar de novo em vez de rodar uma unica vez.

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$cifrasDir = Join-Path $scriptDir "cifras"

if (-not (Test-Path $cifrasDir)) {
    Write-Error "Pasta cifras nao encontrada em: $cifrasDir"
    exit 1
}

# ===== Identificacao de cifras (mesma logica de gerar_letras.ps1 - se mudar a classificacao de
# acorde/letra em telaCel.html, replique tambem aqui e em gerar_letras.ps1) =====

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

# ===== Quebra das linhas no ";" =====

function Quebrar-LinhasComPontoEVirgula {
    param([string[]]$linhas)

    $resultado = New-Object System.Collections.Generic.List[string]
    $quebras = 0

    foreach ($linhaAtual in $linhas) {
        $idx = $linhaAtual.IndexOf(';')

        if ($idx -ge 0 -and -not (Test-ChordLine $linhaAtual)) {
            $letraParte1 = $linhaAtual.Substring(0, $idx)
            $letraParte2 = $linhaAtual.Substring($idx + 1)

            $temCifraAnterior = ($resultado.Count -gt 0) -and (Test-ChordLine $resultado[$resultado.Count - 1])

            if ($temCifraAnterior) {
                $linhaCifraAnterior = $resultado[$resultado.Count - 1]

                # mesma coluna (idx) usada pra quebrar a letra tambem quebra a cifra - substring
                # puro, sem reindentar, igual ao quebrarLinhasLongas de telaCel.html. A coluna do
                # ";" some dos dois lados (na letra o ";" e removido; na cifra descarta-se a mesma
                # coluna), por isso a segunda parte comeca em idx+1 nos dois casos.
                $corteCifra1 = [Math]::Min($idx, $linhaCifraAnterior.Length)
                $cifraParte1 = $linhaCifraAnterior.Substring(0, $corteCifra1)
                if ($idx + 1 -le $linhaCifraAnterior.Length) {
                    $cifraParte2 = $linhaCifraAnterior.Substring($idx + 1)
                } else {
                    $cifraParte2 = ""
                }

                $resultado[$resultado.Count - 1] = $cifraParte1
                $resultado.Add($letraParte1)
                if ($cifraParte2.Trim() -ne "") {
                    $resultado.Add($cifraParte2)
                }
                $resultado.Add($letraParte2)
            } else {
                $resultado.Add($letraParte1)
                $resultado.Add($letraParte2)
            }

            $quebras++
        } else {
            $resultado.Add($linhaAtual)
        }
    }

    return [PSCustomObject]@{ Linhas = $resultado; Quebras = $quebras }
}

function Processar-Arquivo {
    param([string]$caminho)

    $conteudo = (Get-Content -Path $caminho -Raw -Encoding UTF8).TrimEnd("`r", "`n")
    $linhas = [regex]::Split($conteudo, '\r?\n')

    $resultadoObj = Quebrar-LinhasComPontoEVirgula -linhas $linhas

    if ($resultadoObj.Quebras -gt 0) {
        Set-Content -Path $caminho -Value ($resultadoObj.Linhas -join "`r`n") -Encoding UTF8
    }

    return $resultadoObj.Quebras
}

# ===== Descobre qual arquivo de \cifras esta aberto no Bloco de Notas / Notepad++ =====

function Encontrar-ArquivosAbertos {
    param([string[]]$candidatos)

    $processos = Get-Process -ErrorAction SilentlyContinue | Where-Object {
        $_.MainWindowTitle -ne "" -and $_.ProcessName -match 'notepad'
    }

    if (-not $processos) { return @() }

    $encontrados = New-Object System.Collections.Generic.List[string]
    foreach ($caminho in $candidatos) {
        $nomeArquivo = Split-Path -Path $caminho -Leaf
        foreach ($proc in $processos) {
            if ($proc.MainWindowTitle -like "*$nomeArquivo*") {
                $encontrados.Add($caminho)
                break
            }
        }
    }

    return $encontrados
}

# ===== Loop principal =====

Write-Host "===================================================="
Write-Host " AjustaCifra - quebra letra+cifra no ';'"
Write-Host "===================================================="

while ($true) {
    Write-Host ""
    try {
        $candidatos = Get-ChildItem -Path $cifrasDir -Filter "*.txt" -Recurse | Select-Object -ExpandProperty FullName
        $abertos = Encontrar-ArquivosAbertos -candidatos $candidatos

        if ($abertos.Count -eq 0) {
            Write-Host "Nenhum arquivo de \cifras parece estar aberto no Bloco de Notas / Notepad++ agora."
        } else {
            foreach ($arquivo in $abertos) {
                $quebras = Processar-Arquivo -caminho $arquivo
                if ($quebras -gt 0) {
                    Write-Host "Ajustado ($quebras quebra(s)): $arquivo"
                    Write-Host "  -> se o arquivo estiver aberto no editor, feche SEM salvar e reabra pra ver o resultado (senao salvar por cima desfaz o ajuste)."
                } else {
                    Write-Host "Sem ';' pendente: $arquivo"
                }
            }
        }
    } catch {
        Write-Host "Erro ao processar: $($_.Exception.Message)"
    }

    Write-Host ""
    Write-Host "Pressione qualquer tecla para executar de novo (feche esta janela para sair)..."
    try {
        $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    } catch {
        Read-Host "ENTER para continuar" | Out-Null
    }
}

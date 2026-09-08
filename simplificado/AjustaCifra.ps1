# Ferramenta interativa: percorre \cifras (e subpastas), descobre qual arquivo esta aberto no
# Bloco de Notas / Notepad++ (ou similar) no momento, e ajusta as linhas de letra que tenham ";"
# (ver rc.md secoes AJUSTE DAS Cifras e AJUSTE INVERSO):
#   - ";" NO MEIO de uma linha de letra -> quebra ela em duas, quebrando a linha de cifra logo
#     acima na MESMA coluna, pra manter o alinhamento acorde/letra.
#   - ";" NO FINAL de uma linha de letra -> operacao inversa: junta essa linha com o PROXIMO par
#     cifra+letra (a cifra ganha um espaco entre as duas metades pra preservar a posicao dos
#     acordes sobre a letra; a letra e concatenada direto, sem separador, ja que o ";" so marcava
#     onde juntar).
# So processa UMA ocorrencia de ";" por linha por execucao (a primeira ";" no meio, ou a juncao com
# o proximo par se terminar em ";") - o que sobrar fica pra rodada seguinte do loop, por isso o
# script fica perguntando se quer rodar de novo em vez de rodar uma unica vez.
# Tambem remove qualquer `">` encontrado em qualquer linha (artefato de copia/cola de outros sites
# de cifra - ver rc.md secao AjustaCifra) - essa limpeza roda ANTES do ajuste do ";", pra classificar
# corretamente cifra/letra mesmo em linhas que ainda tem esse lixo.

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

# ===== Remove ">"" (artefato de copia/cola de outros sites de cifra - ver rc.md secao AjustaCifra) =====

function Remover-AspasMaiorQue {
    param([string[]]$linhas)

    $resultado = New-Object System.Collections.Generic.List[string]
    $remocoes = 0

    foreach ($linha in $linhas) {
        if ($linha.Contains('">')) {
            $resultado.Add($linha.Replace('">', ''))
            $remocoes += ([regex]::Matches($linha, '">')).Count
        } else {
            $resultado.Add($linha)
        }
    }

    return [PSCustomObject]@{ Linhas = $resultado; Remocoes = $remocoes }
}

# ===== Ajuste das linhas no ";" (quebra no meio / junta no final) =====

function Ajustar-LinhasComPontoEVirgula {
    param([string[]]$linhas)

    $resultado = New-Object System.Collections.Generic.List[string]
    $quebras = 0
    $juncoes = 0
    $i = 0

    while ($i -lt $linhas.Count) {
        $linhaAtual = $linhas[$i]
        $ehLetra = -not (Test-ChordLine $linhaAtual)

        # ===== INVERSO: ";" no FINAL de uma linha de letra -> junta com o proximo par cifra+letra
        if ($ehLetra -and $linhaAtual.EndsWith(';')) {
            $juntou = $false
            if (($i + 2) -lt $linhas.Count) {
                $chordProx = $linhas[$i + 1]
                $lyricProx = $linhas[$i + 2]
                $temCifraAnterior = ($resultado.Count -gt 0) -and (Test-ChordLine $resultado[$resultado.Count - 1])

                if ($temCifraAnterior -and (Test-ChordLine $chordProx) -and -not (Test-ChordLine $lyricProx)) {
                    # a cifra ganha um espaco no ponto de juncao (repoe a coluna que a quebra
                    # original descartou - ver AJUSTE DAS Cifras); a letra e concatenada direto,
                    # sem separador, so removendo o ";" que marcava onde juntar.
                    $chordAtual = $resultado[$resultado.Count - 1]
                    $resultado[$resultado.Count - 1] = $chordAtual + " " + $chordProx
                    $resultado.Add($linhaAtual.Substring(0, $linhaAtual.Length - 1) + $lyricProx)

                    $juncoes++
                    $i += 3
                    $juntou = $true
                }
            }

            if ($juntou) { continue }

            # ";" no final sem contexto valido pra juntar (ex.: primeira linha do arquivo, ou o
            # proximo par nao e cifra+letra) - deixa como esta, nao arrisca produzir lixo.
            $resultado.Add($linhaAtual)
            $i++
            continue
        }

        # ===== NORMAL: ";" no MEIO de uma linha de letra -> quebra ela e a cifra anterior
        if ($ehLetra) {
            $idx = $linhaAtual.IndexOf(';')
            if ($idx -ge 0) {
                $letraParte1 = $linhaAtual.Substring(0, $idx)
                $letraParte2 = $linhaAtual.Substring($idx + 1)

                $temCifraAnterior = ($resultado.Count -gt 0) -and (Test-ChordLine $resultado[$resultado.Count - 1])

                if ($temCifraAnterior) {
                    $linhaCifraAnterior = $resultado[$resultado.Count - 1]

                    # mesma coluna (idx) usada pra quebrar a letra tambem quebra a cifra -
                    # substring puro, sem reindentar, igual ao quebrarLinhasLongas de telaCel.html.
                    # A coluna do ";" some dos dois lados (na letra o ";" e removido; na cifra
                    # descarta-se a mesma coluna), por isso a segunda parte comeca em idx+1 nos
                    # dois casos.
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
                $i++
                continue
            }
        }

        $resultado.Add($linhaAtual)
        $i++
    }

    return [PSCustomObject]@{ Linhas = $resultado; Quebras = $quebras; Juncoes = $juncoes }
}

function Processar-Arquivo {
    param([string]$caminho)

    $conteudo = (Get-Content -Path $caminho -Raw -Encoding UTF8).TrimEnd("`r", "`n")
    $linhas = [regex]::Split($conteudo, '\r?\n')

    $limpezaObj = Remover-AspasMaiorQue -linhas $linhas
    $resultadoObj = Ajustar-LinhasComPontoEVirgula -linhas $limpezaObj.Linhas

    $totalAjustes = $resultadoObj.Quebras + $resultadoObj.Juncoes + $limpezaObj.Remocoes
    if ($totalAjustes -gt 0) {
        Set-Content -Path $caminho -Value ($resultadoObj.Linhas -join "`r`n") -Encoding UTF8
    }

    return [PSCustomObject]@{ Quebras = $resultadoObj.Quebras; Juncoes = $resultadoObj.Juncoes; Remocoes = $limpezaObj.Remocoes }
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
Write-Host " AjustaCifra - quebra/junta letra+cifra no ';'"
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
                $r = Processar-Arquivo -caminho $arquivo
                if (($r.Quebras + $r.Juncoes + $r.Remocoes) -gt 0) {
                    Write-Host "Ajustado ($($r.Quebras) quebra(s), $($r.Juncoes) juncao(oes), $($r.Remocoes) remocao(oes) de aspas+maior): $arquivo"
                    Write-Host "  -> se o arquivo estiver aberto no editor, feche SEM salvar e reabra pra ver o resultado (senao salvar por cima desfaz o ajuste)."
                } else {
                    Write-Host "Nada pendente: $arquivo"
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

# Regenera telaCel.html/nodeMCU a partir de \cifras (inclui.ps1) e da add+commit+push. Pensado pra
# rodar sem interacao nenhuma - chamado em loop por simplificado\AjustaCifra.ps1 a cada rodada (ver
# rc.md secao EDITAR MUSICAS) alem de poder ser rodado direto via push.bat. So pausa e pede
# confirmacao se algo der errado; dando tudo certo, roda do inicio ao fim e fecha sozinho.

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Pausar-ParaConfirmacao {
    try {
        $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    } catch {
        Read-Host "ENTER para fechar" | Out-Null
    }
}

try {
    & (Join-Path $scriptDir "simplificado\inclui.ps1")

    Set-Location $scriptDir

    git add -A
    if ($LASTEXITCODE -ne 0) { throw "git add -A falhou (codigo $LASTEXITCODE)" }

    $mensagem = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $saidaCommit = git commit -m $mensagem 2>&1 | Out-String
    # codigo diferente de 0 so por "nada pra commitar" nao e erro de verdade - so segue pro push
    if ($LASTEXITCODE -ne 0 -and $saidaCommit -notmatch "nothing to commit") {
        throw "git commit falhou:`n$saidaCommit"
    }
    Write-Host $saidaCommit.Trim()

    git push
    if ($LASTEXITCODE -ne 0) { throw "git push falhou (codigo $LASTEXITCODE)" }

    Write-Host "Push concluido com sucesso ($mensagem)."
} catch {
    Write-Host ""
    Write-Host "ERRO NO PUSH: $($_.Exception.Message)"
    Write-Host ""
    Write-Host "Pressione qualquer tecla para fechar..."
    Pausar-ParaConfirmacao
    exit 1
}

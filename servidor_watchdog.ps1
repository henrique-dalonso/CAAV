# servidor_watchdog.ps1
# Chamado pelo iniciar_servidor.bat. Antes de subir um novo servidor,
# verifica se ja existe um Extratus rodando neste computador - evita
# duas copias brigando pela mesma porta 8000, uma delas com codigo
# antigo escondido por tras (ja causou confusao real em sessoes
# anteriores: parecia que o servidor tinha reiniciado, mas era a
# copia velha que continuava respondendo).

$raiz = $PSScriptRoot
$arquivoPid = Join-Path $raiz "servidor.pid"

if (Test-Path $arquivoPid) {
    $pidAntigo = Get-Content $arquivoPid -ErrorAction SilentlyContinue
    if ($pidAntigo) {
        $processoAntigo = Get-Process -Id $pidAntigo -ErrorAction SilentlyContinue
        if ($processoAntigo -and $processoAntigo.ProcessName -eq "python") {
            Write-Host ""
            Write-Host "============================================================"
            Write-Host " Ja existe um Extratus rodando neste computador (processo $pidAntigo)."
            Write-Host " Feche a janela do servidor antigo antes de abrir um novo,"
            Write-Host " ou peca pra alguem tecnico encerrar o processo $pidAntigo"
            Write-Host " no Gerenciador de Tarefas."
            Write-Host "============================================================"
            Write-Host ""
            exit 1
        }
    }
}

$pythonExe = Join-Path $raiz ".venv\Scripts\python.exe"
$processo = Start-Process -FilePath $pythonExe `
    -ArgumentList "-m", "uvicorn", "app.plataforma.web.main:app", "--host", "0.0.0.0", "--port", "8000" `
    -WorkingDirectory $raiz `
    -NoNewWindow `
    -PassThru

# O uvicorn sobe um processo FILHO (PID diferente do que acabou de ser
# criado acima) que é quem realmente fica escutando a porta - é esse PID
# que precisa ir pra carteirinha, não o do processo "pai". Espera até
# 15 segundos a porta aparecer antes de desistir.
$pidReal = $null
for ($i = 0; $i -lt 30; $i++) {
    $conexao = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conexao) {
        $pidReal = $conexao.OwningProcess
        break
    }
    Start-Sleep -Milliseconds 500
}

if ($pidReal) {
    $pidReal | Out-File -FilePath $arquivoPid -Encoding ascii -NoNewline
} else {
    $processo.Id | Out-File -FilePath $arquivoPid -Encoding ascii -NoNewline
}

try {
    Wait-Process -Id $processo.Id
}
finally {
    Remove-Item $arquivoPid -ErrorAction SilentlyContinue
}

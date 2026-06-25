@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "PORTA_BASE=8000"
set "PORTA_ATUAL=%PORTA_BASE%"
set "LIMITE_PORTAS=20"
set /a TENTATIVA=0

:verificar_porta
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":!PORTA_ATUAL! .*LISTENING"') do (
    set "PORTA_OCUPADA=1"
)

if not defined PORTA_OCUPADA goto iniciar_servidor

set /a TENTATIVA+=1
if !TENTATIVA! geq %LIMITE_PORTAS% (
    echo Nenhuma porta livre encontrada entre %PORTA_BASE% e %PORTA_ATUAL%.
    goto fim
)

set /a PORTA_ATUAL+=1
set "PORTA_OCUPADA="
goto verificar_porta

:iniciar_servidor
echo Iniciando servidor na porta !PORTA_ATUAL!...
npx next dev -p !PORTA_ATUAL!

:fim
endlocal
pause

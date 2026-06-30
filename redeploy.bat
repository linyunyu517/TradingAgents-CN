@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

set "PROJECT_DIR=D:\AI-Projects\TradingAgents-CN_v1.0.1"
set "BACKEND_PORT=8000"
set "BACKEND_LOG=%PROJECT_DIR%\logs\redeploy.log"

cd /d "%PROJECT_DIR%"

echo ============================================
echo  TradingAgents Backend Redeploy
echo  %date% %time%
echo ============================================

REM === Step 1: 按端口杀旧进程 ===
echo [1/5] 清理旧进程...
for /f "tokens=5" %%a in ('powershell -noprofile -command "try{$conn=Get-NetTCPConnection -LocalPort %BACKEND_PORT% -ErrorAction Stop | Where-Object {$_.State -eq 'Listen'}; if($conn){$conn.OwningProcess}}catch{exit 1}" 2^>nul') do (
    set "OLD_PID=%%a"
    if not "!OLD_PID!"=="" (
        echo   发现旧进程 PID=!OLD_PID!，正在终止...
        taskkill /f /pid !OLD_PID! >nul 2>&1
    )
)

REM === Step 2: 等待端口释放（含 TIME_WAIT 检测） ===
echo [2/5] 等待端口 %BACKEND_PORT% 释放...
:wait_port_free
set WAIT_TIMEOUT=0
:wait_port_free_loop
set /a WAIT_TIMEOUT+=1
if !WAIT_TIMEOUT! gtr 10 (
    echo   端口等待超时，强制继续...
    goto port_clean_done
)

REM 检测 LISTENING
netstat -ano 2>nul | findstr ":%BACKEND_PORT% " | findstr "LISTENING" >nul
if errorlevel 1 goto check_timewait
echo   端口仍在监听，等待 3 秒...
choice /t 3 /d y /n >nul 2>&1
goto wait_port_free_loop

:check_timewait
REM 检测 TIME_WAIT
netstat -ano 2>nul | findstr ":%BACKEND_PORT% " | findstr "TIME_WAIT" >nul
if errorlevel 1 goto port_clean_done
echo   端口处于 TIME_WAIT 状态，等待 30 秒...
choice /t 30 /d y /n >nul 2>&1
goto wait_port_free

:port_clean_done
echo   端口已释放 ✅

REM === Step 3: 激活虚拟环境 ===
echo [3/5] 激活虚拟环境...
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else (
    if exist "venv\Scripts\activate.bat" (
        call venv\Scripts\activate.bat
    ) else (
        echo   ⚠️ 未找到虚拟环境，使用系统 Python
    )
)

REM === Step 4: 启动 uvicorn ===
echo [4/5] 启动后端服务...

REM 验证 watchfiles（--reload 依赖）
python -c "import watchfiles" 2>nul
if errorlevel 1 (
    echo   ⚠️ watchfiles 未安装，尝试自动安装...
    python -m pip install watchfiles -q
)

REM 启动 uvicorn（带日志重定向）
echo   启动命令: uvicorn app.main:app --host 0.0.0.0 --port %BACKEND_PORT% --reload --reload-exclude '*/__pycache__/*'
start "TradingAgents-Backend" /MIN cmd /c "cd /d %PROJECT_DIR% && .venv\Scripts\activate.bat && uvicorn app.main:app --host 0.0.0.0 --port %BACKEND_PORT% --reload --reload-exclude '*/__pycache__/*' >> %BACKEND_LOG% 2>&1"

REM === Step 5: 健康检查（含重试） ===
echo [5/5] 等待服务就绪...
set RETRY_COUNT=0

:health_retry
choice /t 10 /d y /n >nul 2>&1
powershell -noprofile -command "try{$r=Invoke-WebRequest -Uri 'http://localhost:%BACKEND_PORT%/docs' -UseBasicParsing -TimeoutSec 5; if($r.StatusCode -eq 200){exit 0}else{exit 1}}catch{exit 1}" >nul 2>&1
if errorlevel 1 (
    set /a RETRY_COUNT+=1
    if !RETRY_COUNT! leq 3 (
        echo [WARN] 健康检查失败 (attempt !RETRY_COUNT!/3)，重试中...
        goto health_retry
    ) else (
        echo ❌ 健康检查在 3 次重试后仍未通过，请检查日志: %BACKEND_LOG%
        exit /b 1
    )
) else (
    echo ✅ 后端已就绪，访问 http://localhost:%BACKEND_PORT%/docs
)

echo ============================================
endlocal

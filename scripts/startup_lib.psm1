# startup_lib.psm1 — TradingAgents-CN 启动核心模块
# 方案C: 架构级重写 — PowerShell 核心逻辑
# 版本: 1.0.0
# 要求: PowerShell 5.1+ (Windows 8+/2012R2+)

# ============================================================
# 模块级配置
# ============================================================
$script:ModuleLogPath = $null
$script:ModuleLogDir = $null
$script:NetTCPAvailable = $null  # 缓存 Get-NetTCPConnection 可用性检测结果

# ============================================================
# Write-Log — 统一日志
# ============================================================
function Write-Log {
    <#
    .SYNOPSIS
        统一日志输出，同时写入控制台和日志文件
    .PARAMETER Level
        INFO / WARN / ERROR / DIAG / OK
    .PARAMETER Message
        日志内容
    #>
    param(
        [Parameter(Mandatory)]
        [ValidateSet('INFO','WARN','ERROR','DIAG','OK')]
        [string]$Level,

        [Parameter(Mandatory)]
        [string]$Message
    )

    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $line = "[$timestamp] [$Level] $Message"

    # 控制台输出（彩色）
    $color = @{
        'INFO'  = 'Cyan'
        'WARN'  = 'Yellow'
        'ERROR' = 'Red'
        'DIAG'  = 'Gray'
        'OK'    = 'Green'
    }[$Level]
    Write-Host $line -ForegroundColor $color

    # 日志文件
    if ($script:ModuleLogPath -and (Test-Path -PathType Leaf $script:ModuleLogPath -ErrorAction SilentlyContinue)) {
        try {
            Add-Content -Path $script:ModuleLogPath -Value $line -ErrorAction Stop
        } catch {
            # 日志写入失败不中断主流程
            Write-Host "[WARN] Log write failed: $_" -ForegroundColor Yellow
        }
    }
}

# ============================================================
# Set-LogPath — 设置日志路径
# ============================================================
function Set-LogPath {
    param([string]$Path)
    $script:ModuleLogPath = $Path
    $script:ModuleLogDir = Split-Path $Path -Parent
    if ($script:ModuleLogDir -and -not (Test-Path $script:ModuleLogDir)) {
        New-Item -ItemType Directory -Path $script:ModuleLogDir -Force | Out-Null
    }
}

# ============================================================
# Test-NetTCPAvailability — 检测 Get-NetTCPConnection 是否可用
# ============================================================
function Test-NetTCPAvailability {
    if ($script:NetTCPAvailable -ne $null) { return $script:NetTCPAvailable }
    try {
        $null = Get-Command Get-NetTCPConnection -ErrorAction Stop
        # 验证能成功调用
        $null = Get-NetTCPConnection -LocalPort 9999 -ErrorAction SilentlyContinue
        $script:NetTCPAvailable = $true
    } catch {
        Write-Log 'DIAG' 'Get-NetTCPConnection unavailable, will use netstat fallback'
        $script:NetTCPAvailable = $false
    }
    return $script:NetTCPAvailable
}

# ============================================================
# Get-ProcessByPort — 根据端口返回占用进程 PID
# ============================================================
function Get-ProcessByPort {
    <#
    .SYNOPSIS
        获取占用指定端口的进程 PID
    .PARAMETER Port
        端口号
    .PARAMETER State
        连接状态过滤（默认 Listen，$null 表示不过滤）
    #>
    param(
        [Parameter(Mandatory)]
        [ValidateRange(1,65535)]
        [int]$Port,

        [ValidateSet('Listen','Established','TimeWait','CloseWait','Bound')]
        [string]$State = 'Listen',

        [switch]$AnyState
    )

    # 主路径: Get-NetTCPConnection
    if (Test-NetTCPAvailability) {
        try {
            $conn = Get-NetTCPConnection -LocalPort $Port -ErrorAction Stop
            if (-not $AnyState) {
                $conn = $conn | Where-Object { $_.State -eq $State }
            }
            if ($conn) {
                return [PSCustomObject]@{
                    PID   = $conn.OwningProcess
                    Port  = $Port
                    State = $conn.State
                }
            }
        } catch {
            # 无连接时静默继续到 fallback
        }
    }

    # Fallback: netstat 解析
    try {
        $stateFilter = if (-not $AnyState) { "| findstr `"$State`"" } else { '' }
        $raw = cmd /c "netstat -ano | findstr `":$Port `" $stateFilter 2>nul"
        if ($raw) {
            $lines = $raw -split "`r`n" | Where-Object { $_ -match ":$Port\s+" }
            foreach ($line in $lines) {
                $parts = $line -split '\s+'
                $procPid = $parts[-1]  # 最后一列是 PID
                if ($procPid -match '^\d+$') {
                    return [PSCustomObject]@{
                        PID   = [int]$procPid
                        Port  = $Port
                        State = 'Unknown'
                    }
                }
            }
        }
    } catch {
        Write-Log 'DIAG' "netstat fallback failed: $_"
    }

    return $null
}

# ============================================================
# Clear-Port — 强制释放端口
# ============================================================
function Clear-Port {
    <#
    .SYNOPSIS
        强制释放指定端口（杀掉占用进程）
    .PARAMETER Port
        端口号
    .PARAMETER TimeoutSeconds
        等待端口释放的超时时间（秒）
    .PARAMETER ForceKillAll
        当未能精确找到占用进程时，是否尝试杀所有可能的进程
    #>
    param(
        [Parameter(Mandatory)]
        [ValidateRange(1,65535)]
        [int]$Port,

        [ValidateRange(1,30)]
        [int]$TimeoutSeconds = 10,

        [switch]$ForceKillAll
    )

    Write-Log 'INFO' "Clearing port $Port..."

    # Step 1: 精确查找占用进程
    $proc = Get-ProcessByPort -Port $Port -State 'Listen'
    if (-not $proc) {
        $proc = Get-ProcessByPort -Port $Port -AnyState  # 不限制状态
    }

    if ($proc) {
        try {
            Write-Log 'INFO' "Killing PID=$($proc.PID) on port $Port"
            Stop-Process -Id $proc.PID -Force -ErrorAction Stop

            # Step 2: 等待端口释放
            $sw = [Diagnostics.Stopwatch]::StartNew()
            while ($sw.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
                $check = Get-ProcessByPort -Port $Port -AnyState
                if (-not $check) {
                    Write-Log 'OK' "Port $Port released (PID $($proc.PID) terminated)"
                    return $true
                }
                Start-Sleep -Milliseconds 500
            }
            Write-Log 'WARN' "Port $Port still occupied after ${TimeoutSeconds}s timeout"
            return $false
        } catch {
            Write-Log 'WARN' "Failed to kill PID $($proc.PID): $_"
        }
    } else {
        Write-Log 'OK' "Port $Port is already free"
        return $true
    }

    # Step 3: ForceKillAll 兜底
    if ($ForceKillAll) {
        Write-Log 'DIAG' "ForceKillAll: killing common server processes..."
        $killTargets = @('node.exe', 'uvicorn.exe', 'python.exe')
        foreach ($exe in $killTargets) {
            try {
                Stop-Process -Name ($exe -replace '\.exe$','') -Force -ErrorAction SilentlyContinue
            } catch {}
        }
        Start-Sleep -Seconds 2
        $check = Get-ProcessByPort -Port $Port -AnyState
        if (-not $check) {
            Write-Log 'OK' "Port $Port released via ForceKillAll"
            return $true
        }
    }

    return $false
}

# ============================================================
# Wait-PortFree — 等待端口空闲
# ============================================================
function Wait-PortFree {
    <#
    .SYNOPSIS
        等待指定端口变为空闲（无进程占用）
    .PARAMETER Port
        端口号
    .PARAMETER TimeoutSeconds
        最大等待时间（秒）
    #>
    param(
        [Parameter(Mandatory)]
        [ValidateRange(1,65535)]
        [int]$Port,

        [ValidateRange(1,120)]
        [int]$TimeoutSeconds = 30
    )

    Write-Log 'INFO' "Waiting for port $Port to be free (timeout=${TimeoutSeconds}s)..."
    $sw = [Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
        $proc = Get-ProcessByPort -Port $Port -AnyState
        if (-not $proc) {
            Write-Log 'OK' "Port $Port is free after $([math]::Round($sw.Elapsed.TotalSeconds, 1))s"
            return $true
        }
        Start-Sleep -Milliseconds 1000
    }
    Write-Log 'WARN' "Port $Port not free after ${TimeoutSeconds}s (still owned by PID $($proc.PID))"
    return $false
}

# ============================================================
# Wait-PortListening — 等待端口开始监听
# ============================================================
function Wait-PortListening {
    <#
    .SYNOPSIS
        等待端口进入 LISTENING 状态
    .PARAMETER Port
        端口号
    .PARAMETER TimeoutSeconds
        最大等待时间（秒）
    #>
    param(
        [Parameter(Mandatory)]
        [ValidateRange(1,65535)]
        [int]$Port,

        [ValidateRange(1,120)]
        [int]$TimeoutSeconds = 60
    )

    Write-Log 'INFO' "Waiting for port $Port to start listening (timeout=${TimeoutSeconds}s)..."
    $sw = [Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
        $proc = Get-ProcessByPort -Port $Port -State 'Listen'
        if ($proc) {
            Write-Log 'OK' "Port $Port is now listening after $([math]::Round($sw.Elapsed.TotalSeconds, 1))s (PID=$($proc.PID))"
            return $true
        }
        Start-Sleep -Milliseconds 1000
    }
    Write-Log 'WARN' "Port $Port not listening after ${TimeoutSeconds}s"
    return $false
}

# ============================================================
# Start-BuildWithTimeout — 带超时控制的 npm build
# ============================================================
function Start-BuildWithTimeout {
    <#
    .SYNOPSIS
        在指定目录执行 npm run build，使用 PowerShell Job 实现超时控制
    .PARAMETER Directory
        frontend 目录路径
    .PARAMETER TimeoutSeconds
        超时时间（秒）
    .PARAMETER BuildCommand
        构建命令（默认 'npm run build'）
    #>
    param(
        [Parameter(Mandatory)]
        [ValidateScript({ Test-Path $_ -PathType Container })]
        [string]$Directory,

        [ValidateRange(10,300)]
        [int]$TimeoutSeconds = 60,

        [string]$BuildCommand = 'npm run build'
    )

    Write-Log 'INFO' "Starting frontend build in $Directory (timeout=${TimeoutSeconds}s, command='$BuildCommand')"

    # 使用 Start-Job 实现超时控制
    $job = Start-Job -ScriptBlock {
        param($dir, $cmd)
        try {
            Set-Location -Path $dir
            # 合并 stdout/stderr，确保错误不被吞没
            $result = Invoke-Expression $cmd 2>&1
            $global:LASTEXITCODE = $LASTEXITCODE
            return @{
                Success   = ($LASTEXITCODE -eq 0)
                Output    = ($result | Out-String)
                ExitCode  = $LASTEXITCODE
            }
        } catch {
            return @{
                Success   = $false
                Output    = $_.ToString()
                ExitCode  = -1
            }
        }
    } -ArgumentList $Directory, $BuildCommand

    # 等待 Job 完成或超时
    $completed = Wait-Job $job -Timeout $TimeoutSeconds
    if ($completed) {
        $result = Receive-Job $job -Keep
        Remove-Job $job

        if ($result.Success) {
            Write-Log 'OK' 'Frontend build completed successfully'
            return $true
        } else {
            Write-Log 'WARN' "Build failed (exit=$($result.ExitCode)): $($result.Output)"
            return $false
        }
    } else {
        # 超时: 强制停止
        Write-Log 'WARN' "Build timed out after ${TimeoutSeconds}s, stopping job..."
        Stop-Job $job -ErrorAction SilentlyContinue
        $partial = Receive-Job $job -ErrorAction SilentlyContinue
        Remove-Job $job -ErrorAction SilentlyContinue
        Write-Log 'WARN' "Build output before timeout: $partial"
        return $false
    }
}

# ============================================================
# Test-Health — HTTP 健康检查
# ============================================================
function Test-Health {
    <#
    .SYNOPSIS
        对指定 URL 进行 HTTP 健康检查
    .PARAMETER Uri
        健康检查 URL
    .PARAMETER TimeoutSeconds
        超时时间（秒）
    .PARAMETER ExpectedStatus
        期望的 HTTP 状态码（默认 200）
    #>
    param(
        [Parameter(Mandatory)]
        [ValidateScript({ $_ -match '^https?://' })]
        [string]$Uri,

        [ValidateRange(1,120)]
        [int]$TimeoutSeconds = 30,

        [int]$ExpectedStatus = 200
    )

    Write-Log 'INFO' "Health check: $Uri (timeout=${TimeoutSeconds}s)"

    $sw = [Diagnostics.Stopwatch]::StartNew()
    $lastError = $null

    while ($sw.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
        try {
            $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
            if ($response.StatusCode -eq $ExpectedStatus) {
                Write-Log 'OK' "Health check passed ($Uri) after $([math]::Round($sw.Elapsed.TotalSeconds, 1))s"
                return $true
            }
            Write-Log 'DIAG' "Health check returned $($response.StatusCode), waiting..."
        } catch {
            $lastError = $_.Exception.Message
            # 服务未就绪时静默重试
        }
        Start-Sleep -Milliseconds 2000
    }

    Write-Log 'WARN' "Health check failed after ${TimeoutSeconds}s: $lastError"
    return $false
}

# ============================================================
# Start-ServiceWithRetry — 带重试的 Windows 服务启动
# ============================================================
function Start-ServiceWithRetry {
    <#
    .SYNOPSIS
        启动 Windows 服务，带重试和等待端口确认
    .PARAMETER ServiceName
        服务名称（如 MongoDB、Memurai、Redis）
    .PARAMETER MaxRetries
        最大重试次数
    .PARAMETER PortCheck
        可选：确认服务启动后检查的端口
    .PARAMETER PortTimeout
        端口等待超时（秒）
    .PARAMETER FallbackCommand
        可选：当服务不存在时的启动命令
    .PARAMETER FallbackName
        回退方式的显示名称
    #>
    param(
        [Parameter(Mandatory)]
        [string]$ServiceName,

        [ValidateRange(1,10)]
        [int]$MaxRetries = 3,

        [ValidateRange(1,65535)]
        [int]$PortCheck = 0,

        [ValidateRange(1,60)]
        [int]$PortTimeout = 30,

        [string]$FallbackCommand = '',

        [string]$FallbackName = ''
    )

    Write-Log 'INFO' "Starting service: $ServiceName (retries=$MaxRetries)"

    # Step 1: 检查服务是否存在
    $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if (-not $svc) {
        Write-Log 'WARN' "Service '$ServiceName' not found"
        if ($FallbackCommand) {
            Write-Log 'INFO' "Using fallback: $FallbackName"
            return (Invoke-FallbackCommand -FallbackCommand $FallbackCommand -FallbackName $FallbackName -PortCheck $PortCheck -PortTimeout $PortTimeout)
        }
        Write-Log 'WARN' "Service '$ServiceName' unavailable, no fallback configured"
        return $false
    }

    # Step 2: 检查是否已在运行
    if ($svc.Status -eq 'Running') {
        Write-Log 'OK' "$ServiceName already running"
        if ($PortCheck -gt 0) {
            return (Wait-PortListening -Port $PortCheck -TimeoutSeconds 5)
        }
        return $true
    }

    # Step 3: 带重试启动
    $attempt = 0
    while ($attempt -lt $MaxRetries) {
        $attempt++
        Write-Log 'INFO' "Starting $ServiceName (attempt $attempt/$MaxRetries)..."
        try {
            Start-Service -Name $ServiceName -ErrorAction Stop
            Start-Sleep -Seconds 3

            # 验证服务状态
            $svc.Refresh()
            if ($svc.Status -eq 'Running') {
                Write-Log 'OK' "$ServiceName started (attempt $attempt)"
                if ($PortCheck -gt 0) {
                    return (Wait-PortListening -Port $PortCheck -TimeoutSeconds $PortTimeout)
                }
                return $true
            }
        } catch {
            Write-Log 'WARN' "Attempt $attempt failed: $_"
        }
        if ($attempt -lt $MaxRetries) {
            Start-Sleep -Seconds 2
        }
    }

    Write-Log 'WARN' "Service $ServiceName failed to start after $MaxRetries attempts"
    if ($FallbackCommand) {
        Write-Log 'INFO' "Trying fallback: $FallbackName"
        return (Invoke-FallbackCommand -FallbackCommand $FallbackCommand -FallbackName $FallbackName -PortCheck $PortCheck -PortTimeout $PortTimeout)
    }
    return $false
}

# ============================================================
# Invoke-FallbackCommand — 执行回退命令（内部函数）
# ============================================================
function Invoke-FallbackCommand {
    param(
        [string]$FallbackCommand,
        [string]$FallbackName,
        [int]$PortCheck,
        [int]$PortTimeout
    )

    if (-not $FallbackCommand) { return $false }

    try {
        Write-Log 'INFO' "Running fallback: $FallbackCommand"
        $proc = Start-Process -FilePath 'cmd.exe' -ArgumentList "/c $FallbackCommand" -NoNewWindow -PassThru -ErrorAction Stop
        Start-Sleep -Seconds 3

        if ($proc.HasExited -and $proc.ExitCode -ne 0) {
            Write-Log 'WARN' "Fallback exited with code $($proc.ExitCode)"
        }

        if ($PortCheck -gt 0) {
            return (Wait-PortListening -Port $PortCheck -TimeoutSeconds $PortTimeout)
        }
        return $true
    } catch {
        Write-Log 'WARN' "Fallback failed: $_"
        return $false
    }
}

# ============================================================
# Start-Backend — 启动后端服务
# ============================================================
function Start-Backend {
    <#
    .SYNOPSIS
        启动 uvicorn 后端服务
    .PARAMETER ProjectDir
        项目根目录
    .PARAMETER Port
        后端端口
    .PARAMETER VenvPath
        虚拟环境路径（可选，自动检测 .venv 或 venv）
    .PARAMETER LogPath
        后端日志路径
    #>
    param(
        [Parameter(Mandatory)]
        [ValidateScript({ Test-Path $_ -PathType Container })]
        [string]$ProjectDir,

        [ValidateRange(1,65535)]
        [int]$Port = 8000,

        [string]$VenvPath = '',

        [string]$LogPath = ''
    )

    if (-not $LogPath) {
        $logDir = Join-Path $ProjectDir 'logs'
        if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
        $LogPath = Join-Path $logDir "backend_startup.log"
    }

    Write-Log 'INFO' "Starting backend on port $Port..."
    Write-Log 'INFO' "Project dir: $ProjectDir"
    Write-Log 'INFO' "Log: $LogPath"

    # 检测虚拟环境
    $activateScript = $null
    if ($VenvPath -and (Test-Path $VenvPath)) {
        # 💡 智能兼容: 如果传的是文件路径（如 activate.bat），自动提取所在目录
        $resolvedVenv = if (Test-Path $VenvPath -PathType Leaf) { Split-Path $VenvPath -Parent } else { $VenvPath }
        $activateScript = Join-Path $resolvedVenv 'Scripts\activate.bat'
    } else {
        $candidates = @(
            Join-Path $ProjectDir '.venv\Scripts\activate.bat',
            Join-Path $ProjectDir 'venv\Scripts\activate.bat'
        )
        foreach ($c in $candidates) {
            if (Test-Path $c) { $activateScript = $c; break }
        }
    }

    # 构建启动命令
    if ($activateScript) {
        $cmdLine = "cmd /c ""cd /d `"$ProjectDir`" && call `"$activateScript`" && uvicorn app.main:app --host 0.0.0.0 --port $Port >> `"$LogPath`" 2>&1"""
    } else {
        $cmdLine = "cmd /c ""cd /d `"$ProjectDir`" && uvicorn app.main:app --host 0.0.0.0 --port $Port >> `"$LogPath`" 2>&1"""
    }

    try {
        $proc = Start-Process -FilePath 'cmd.exe' -ArgumentList "/c $cmdLine" -WindowStyle Minimized -PassThru
        Write-Log 'OK' "Backend started (PID=$($proc.Id))"
        return $proc.Id
    } catch {
        Write-Log 'ERROR' "Failed to start backend: $_"
        return $null
    }
}

# ============================================================
# Start-Frontend — 启动前端服务
# ============================================================
function Start-Frontend {
    <#
    .SYNOPSIS
        启动 npm run dev 前端服务
    .PARAMETER ProjectDir
        项目根目录
    .PARAMETER Port
        前端端口
    .PARAMETER Mode
        启动模式：dev / production
    .PARAMETER LogPath
        前端日志路径
    .PARAMETER TimeoutSeconds
        构建超时（仅 production 模式）
    #>
    param(
        [Parameter(Mandatory)]
        [ValidateScript({ Test-Path $_ -PathType Container })]
        [string]$ProjectDir,

        [ValidateRange(1,65535)]
        [int]$Port = 3000,

        [ValidateSet('dev', 'production')]
        [string]$Mode = 'dev',

        [string]$LogPath = '',

        [ValidateRange(10,300)]
        [int]$TimeoutSeconds = 60
    )

    $frontendDir = Join-Path $ProjectDir 'frontend'
    if (-not (Test-Path $frontendDir)) {
        Write-Log 'ERROR' "Frontend directory not found: $frontendDir"
        return $false
    }

    if (-not $LogPath) {
        $logDir = Join-Path $ProjectDir 'logs'
        if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
        $LogPath = Join-Path $logDir "frontend_startup.log"
    }

    Write-Log 'INFO' "Starting frontend in $Mode mode on port $Port..."

    if ($Mode -eq 'production') {
        # Production: 先 build 再 preview
        Write-Log 'INFO' 'Building frontend for production...'
        $buildOk = Start-BuildWithTimeout -Directory $frontendDir -TimeoutSeconds $TimeoutSeconds
        if (-not $buildOk) {
            Write-Log 'WARN' 'Frontend build failed or timed out, will try dev mode'
            $Mode = 'dev'
        } else {
            $cmdLine = "cmd /c ""cd /d `"$frontendDir`" && npm run preview >> `"$LogPath`" 2>&1"""
            try {
                $proc = Start-Process -FilePath 'cmd.exe' -ArgumentList "/c $cmdLine" -WindowStyle Minimized -PassThru
                Write-Log 'OK' "Frontend (production preview) started (PID=$($proc.Id))"
                return $proc.Id
            } catch {
                Write-Log 'WARN' "Frontend preview failed: $_"
                return $false
            }
        }
    }

    # Dev 模式
    $cmdLine = "cmd /c ""cd /d `"$frontendDir`" && npm run dev >> `"$LogPath`" 2>&1"""
    try {
        $proc = Start-Process -FilePath 'cmd.exe' -ArgumentList "/c $cmdLine" -WindowStyle Minimized -PassThru
        Write-Log 'OK' "Frontend (dev) started (PID=$($proc.Id))"
        return $proc.Id
    } catch {
        Write-Log 'ERROR' "Failed to start frontend: $_"
        return $false
    }
}

# ============================================================
# Invoke-LauncherCheck — 综合环境检查
# ============================================================
function Invoke-LauncherCheck {
    <#
    .SYNOPSIS
        全面检查系统环境，返回诊断结果
    .PARAMETER ProjectDir
        项目根目录
    #>
    param(
        [Parameter(Mandatory)]
        [string]$ProjectDir
    )

    $results = @()

    # 1. 项目目录
    $results += [PSCustomObject]@{
        Check   = 'Project Directory'
        Status  = if (Test-Path $ProjectDir) { 'OK' } else { 'FAIL' }
        Detail  = $ProjectDir
    }

    # 2. Node.js
    try {
        $nodeVer = (node --version 2>&1).ToString().Trim()
        $results += [PSCustomObject]@{ Check = 'Node.js'; Status = 'OK'; Detail = $nodeVer }
    } catch {
        $results += [PSCustomObject]@{ Check = 'Node.js'; Status = 'FAIL'; Detail = 'Not found' }
    }

    # 3. Python
    try {
        $pyVer = (python --version 2>&1).ToString().Trim()
        $results += [PSCustomObject]@{ Check = 'Python'; Status = 'OK'; Detail = $pyVer }
    } catch {
        $results += [PSCustomObject]@{ Check = 'Python'; Status = 'FAIL'; Detail = 'Not found' }
    }

    # 4. Virtual Environment
    $venvFound = $false
    foreach ($v in @('.venv\Scripts\activate.bat', 'venv\Scripts\activate.bat')) {
        if (Test-Path (Join-Path $ProjectDir $v)) { $venvFound = $true; break }
    }
    $results += [PSCustomObject]@{
        Check   = 'Virtual Env'
        Status  = if ($venvFound) { 'OK' } else { 'WARN' }
        Detail  = if ($venvFound) { 'Found' } else { 'Not found (system Python)' }
    }

    # 5. MongoDB 服务
    $mongo = Get-Service -Name 'MongoDB' -ErrorAction SilentlyContinue
    if ($mongo) {
        $results += [PSCustomObject]@{
            Check   = 'MongoDB'
            Status  = if ($mongo.Status -eq 'Running') { 'OK' } else { 'STOPPED' }
            Detail  = "Service: $($mongo.Status)"
        }
    } else {
        # 检查 mongod 或 docker
        $mongod = Get-Command mongod -ErrorAction SilentlyContinue
        $dockerMongo = docker ps --filter "name=mongodb" --format "{{.Names}}" 2>$null
        if ($mongod) {
            $results += [PSCustomObject]@{ Check = 'MongoDB'; Status = 'WARN'; Detail = 'Service not registered, mongod.exe available' }
        } elseif ($dockerMongo) {
            $results += [PSCustomObject]@{ Check = 'MongoDB'; Status = 'WARN'; Detail = 'Docker container available' }
        } else {
            $results += [PSCustomObject]@{ Check = 'MongoDB'; Status = 'FAIL'; Detail = 'Not available' }
        }
    }

    # 6. Redis/Memurai
    $redis = Get-Service -Name 'Memurai' -ErrorAction SilentlyContinue
    if (-not $redis) { $redis = Get-Service -Name 'Redis' -ErrorAction SilentlyContinue }
    if ($redis) {
        $results += [PSCustomObject]@{
            Check   = 'Redis/Memurai'
            Status  = if ($redis.Status -eq 'Running') { 'OK' } else { 'STOPPED' }
            Detail  = "$($redis.Name): $($redis.Status)"
        }
    } else {
        $redisCli = Get-Command redis-server -ErrorAction SilentlyContinue
        $dockerRedis = docker ps --filter "name=redis" --format "{{.Names}}" 2>$null
        if ($redisCli) {
            $results += [PSCustomObject]@{ Check = 'Redis/Memurai'; Status = 'WARN'; Detail = 'redis-server.exe available' }
        } elseif ($dockerRedis) {
            $results += [PSCustomObject]@{ Check = 'Redis/Memurai'; Status = 'WARN'; Detail = 'Docker container available' }
        } else {
            $results += [PSCustomObject]@{ Check = 'Redis/Memurai'; Status = 'FAIL'; Detail = 'Not available' }
        }
    }

    # 7. PowerShell 版本
    $psVer = $PSVersionTable.PSVersion.ToString()
    $results += [PSCustomObject]@{
        Check   = 'PowerShell'
        Status  = if ($PSVersionTable.PSVersion.Major -ge 5) { 'OK' } else { 'WARN' }
        Detail  = $psVer
    }

    # 8. 端口占用
    $results += [PSCustomObject]@{
        Check   = 'Port 8000'
        Status  = if (Get-ProcessByPort -Port 8000) { 'IN USE' } else { 'FREE' }
        Detail  = 'Backend'
    }
    $results += [PSCustomObject]@{
        Check   = 'Port 3000'
        Status  = if (Get-ProcessByPort -Port 3000) { 'IN USE' } else { 'FREE' }
        Detail  = 'Frontend'
    }
    $results += [PSCustomObject]@{
        Check   = 'Port 27017'
        Status  = if (Get-ProcessByPort -Port 27017) { 'IN USE' } else { 'FREE' }
        Detail  = 'MongoDB'
    }
    $results += [PSCustomObject]@{
        Check   = 'Port 6379'
        Status  = if (Get-ProcessByPort -Port 6379) { 'IN USE' } else { 'FREE' }
        Detail  = 'Redis'
    }

    return $results
}

# ============================================================
# 模块导出
# ============================================================
Export-ModuleMember -Function @(
    'Write-Log',
    'Set-LogPath',
    'Get-ProcessByPort',
    'Clear-Port',
    'Wait-PortFree',
    'Wait-PortListening',
    'Start-BuildWithTimeout',
    'Test-Health',
    'Start-ServiceWithRetry',
    'Start-Backend',
    'Start-Frontend',
    'Invoke-LauncherCheck'
)

# 模块加载完成提示
Write-Host "[OK] startup_lib.psm1 loaded successfully" -ForegroundColor Green

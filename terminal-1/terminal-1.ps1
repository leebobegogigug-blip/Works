<#
.SYNOPSIS
  terminal-1 (Terminal–1) - tmux-like multi-instance opencode dashboard for Windows Terminal

  Every `terminal-1 add` opens a NEW TAB (a numbered channel) in the same "terminal-1" window:
    tab "00 overview"        : [ overview (tokens / instances / active work / events / logs) ]
                               [ usage chart + mixer (all)  | pet ranch (all pets)           ]
    tab "01 api-server :4096": [ opencode TUI | status (tokens / sessions / events / logs)   ]
                               [ compose      | usage chart | TOKEN QUEST pet               ]
    ...
  In every pane: ? (F1 in compose) shows the guide - numbered callouts + legend.
  Formerly 'ocmux': the first run moves %LOCALAPPDATA%\ocmux (registry, pets, logs) to %LOCALAPPDATA%\terminal-1.

.EXAMPLE
  terminal-1 add                          # current folder, next free port
  terminal-1 add C:\work\web -Name web    # another project in a new tab
  terminal-1 add C:\work\api -Headless    # hidden `opencode serve` + attach (survives closing the tab)
  terminal-1 overview                     # open the overview tab
  terminal-1 ls                           # list instances + health
  terminal-1 focus api                    # reopen the tab for an instance
  terminal-1 rm api                       # unregister (and stop headless server)
  terminal-1 prune                        # drop offline instances
  terminal-1 setup                        # install 'Terminal-1 Black' color scheme (auto on first run)
  terminal-1 version                      # print the version (VERSION in t1_term.py)
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('add', 'overview', 'ls', 'focus', 'rm', 'prune', 'setup', 'version', 'help')]
    [string]$Cmd = 'add',
    [Parameter(Position = 1)]
    [string]$Target,                 # add: folder / focus,rm: name or port
    [string]$Name,
    [int]$Port = 0,
    [int]$BasePort = 4096,
    [string]$HostName = '127.0.0.1',
    [string]$Python = '',            # default: 'py -3' if the Python launcher exists, else 'python'
    [string]$Window = 'terminal-1',
    [double]$RightWidth = 0.5,
    [double]$BottomHeight = 0.42,   # usage/pet row height
    [double]$GameWidth = 0.58,      # pet(TOKEN QUEST) share of the bottom row
    [Alias('Hero')][string]$PetName,  # name for a NEW pet egg (default: 토큰이)
    [switch]$Headless,
    [double]$ComposeHeight = 0.30,  # big input pane under the TUI
    [switch]$NoCompose,
    [switch]$Compact,               # no usage/rpg row
    [switch]$NoPet,                 # no TOKEN QUEST pane (monitor only: usage takes the whole bottom row)
    [switch]$NoLogs,                # no LOGS section inside status
    [switch]$NoOverview
)

$ErrorActionPreference = 'Stop'
if (-not $Python) {
    # python.org installer puts the 'py' launcher on PATH even when 'python' is not (or is the Store stub)
    $Python = if (Get-Command py -ErrorAction SilentlyContinue) { 'py -3' } else { 'python' }
}
$Here     = Split-Path -Parent $MyInvocation.MyCommand.Path
$Monitor  = Join-Path $Here 't1_monitor.py'
$Palette  = @('#3F77A6', '#A5AAAE', '#75A1C7', '#6ABA23', '#B8CEE0', '#81888D', '#95D85A', '#45741B')  # navy first, lime is accent
$Scheme   = 'Terminal-1 Black'
function Get-Version {
    # one version for the whole app: VERSION in t1_term.py (the Python panes print the same with --version)
    $m = Select-String -LiteralPath (Join-Path $Here 't1_term.py') -Pattern '^VERSION = "([^"]+)"' | Select-Object -First 1
    if ($m) { $m.Matches[0].Groups[1].Value } else { '?' }
}

# ------------------------------------------------------------------ output (same design language as the panes)
function Chip([string]$t, [string]$bgc = 'Green', [string]$fgc = 'Black') {
    Write-Host -NoNewline (" $t ") -BackgroundColor $bgc -ForegroundColor $fgc
}
function Txt([string]$t, [string]$c = 'Gray') { Write-Host -NoNewline $t -ForegroundColor $c }
function Say([string]$tag, [string]$msg, [string]$note = '', [string]$bgc = 'Green') {
    Chip $tag $bgc; Txt " $msg"
    if ($note) { Txt "  $note" 'DarkGray' }
    Write-Host ''
}

# ------------------------------------------------------------------ data folder (+ the rename from ocmux)
# This tool used to be called 'ocmux'. The first run after the rename moves %LOCALAPPDATA%\ocmux (registry,
# pets, logs) here. While an ocmux window is still open its panes use that folder, so keep using it too and
# try again on the next run - the Python panes follow the same rule (t1_term.data_dir) and never move it.
$DataDir  = Join-Path $env:LOCALAPPDATA 'terminal-1'
$OldData  = Join-Path $env:LOCALAPPDATA 'ocmux'
function Move-OldData {
    if ((Test-Path -LiteralPath $DataDir) -or -not (Test-Path -LiteralPath $OldData)) { return }
    $open = $false
    if (Get-Command Get-CimInstance -ErrorAction SilentlyContinue) {
        # old panes that hold no file open would not block the move, but would keep writing to the old folder
        try { $open = [bool](Get-CimInstance Win32_Process -Filter "CommandLine LIKE '%oc_monitor.py%'" -ErrorAction SilentlyContinue) } catch { }
    }
    if (-not $open) {
        try { Move-Item -LiteralPath $OldData -Destination $DataDir -ErrorAction Stop } catch { $open = $true }
    }
    if ($open) {
        $script:DataDir = $OldData
        Say 'RENAME' 'an ocmux window is still open' 'close it, then run terminal-1 again to move the data' 'DarkGray'
    } else {
        Say 'RENAME' 'ocmux -> terminal-1' "moved $OldData" 'Gray'
    }
}
function Update-OldPath {
    # the user PATH still points at the old program folder (...\ocmux next to this one) -> point it here
    $old = Join-Path (Split-Path -Parent $Here) 'ocmux'
    if (Test-Path -LiteralPath (Join-Path $old 'ocmux.ps1')) { return }   # an old copy still lives there
    $p = [Environment]::GetEnvironmentVariable('Path', 'User')           # (null outside Windows)
    if (-not $p) { return }
    $parts = @($p.Split(';') | Where-Object { $_ -ne '' })
    if (-not ($parts | Where-Object { $_.TrimEnd('\') -ieq $old })) { return }
    $new = @()
    foreach ($x in $parts) {
        $y = if ($x.TrimEnd('\') -ieq $old) { $Here } else { $x }
        if ($new -notcontains $y) { $new += $y }
    }
    [Environment]::SetEnvironmentVariable('Path', ($new -join ';'), 'User')
    Say 'PATH' "$old -> $Here" 'open a new terminal, then: terminal-1 add' 'Gray'
}
Move-OldData
Update-OldPath
$RegFile  = Join-Path $DataDir 'instances.json'
$LogDir   = Join-Path $DataDir 'logs'
$PwFile   = Join-Path $DataDir 'server-password'   # read by the Python panes (never put on a command line)
New-Item -ItemType Directory -Force -Path $DataDir, $LogDir | Out-Null

# ------------------------------------------------------------------ color scheme (WT JSON fragment)
# Black background + navy/lime/gray ANSI palette, installed as a Windows Terminal fragment
function Install-Scheme {
    $fragDir  = Join-Path $env:LOCALAPPDATA 'Microsoft\Windows Terminal\Fragments\terminal-1'
    $fragFile = Join-Path $fragDir 'terminal-1.json'
    $def = [ordered]@{
        name = $Scheme
        background = '#000000'; foreground = '#D4D6D8'
        cursorColor = '#6ABA23'; selectionBackground = '#1F507A'
        black = '#000000';  red = '#F2F2F3';  green = '#6ABA23';  yellow = '#95D85A'
        blue  = '#3F77A6';  purple = '#75A1C7'; cyan = '#B8CEE0'; white = '#D4D6D8'
        brightBlack = '#5C6166'; brightRed = '#FFFFFF'; brightGreen = '#95D85A'; brightYellow = '#C0E79D'
        brightBlue  = '#75A1C7'; brightPurple = '#B8CEE0'; brightCyan = '#D6E4EF'; brightWhite = '#FFFFFF'
    }
    $json = ConvertTo-Json -InputObject ([ordered]@{ schemes = @($def) }) -Depth 5
    $old = if (Test-Path $fragFile) { [System.IO.File]::ReadAllText($fragFile) } else { '' }
    if ($old -ne $json) {
        New-Item -ItemType Directory -Force -Path $fragDir | Out-Null
        [System.IO.File]::WriteAllText($fragFile, $json, (New-Object System.Text.UTF8Encoding($false)))
        Say 'SCHEME' "installed '$Scheme'" $fragFile
        Say 'NOTE' 'close ALL Windows Terminal windows once so WT loads the new colors' '' 'DarkGray'
    }
    # 'ocmux Black' (the scheme before the rename): drop it once no ocmux window uses it any more
    $oldFrag = Join-Path $env:LOCALAPPDATA 'Microsoft\Windows Terminal\Fragments\ocmux'
    if ($DataDir -ne $OldData -and (Test-Path -LiteralPath (Join-Path $oldFrag 'ocmux.json'))) {
        try {
            Remove-Item -LiteralPath (Join-Path $oldFrag 'ocmux.json') -Force
            if (-not (Get-ChildItem -LiteralPath $oldFrag -Force)) { Remove-Item -LiteralPath $oldFrag -Force }
            Say 'SCHEME' "removed the old 'ocmux Black'" '' 'DarkGray'
        } catch { }
    }
}

# ------------------------------------------------------------------ registry
# old blue/pink tab colors -> new palette (same index), so existing instances switch palettes too
$OldPalette = @('#3B82F6', '#EC4899', '#6366F1', '#F472B6', '#0EA5E9', '#DB2777', '#818CF8', '#D946EF')
function Get-Reg {
    if (-not (Test-Path $RegFile)) { return @() }
    $raw = Get-Content $RegFile -Raw -Encoding UTF8
    if (-not $raw.Trim()) { return @() }
    $list = @($raw | ConvertFrom-Json | ForEach-Object { $_ })  # PS5.1: unroll array
    $changed = $false
    foreach ($e in $list) {
        if ($e.color) {
            $k = [array]::IndexOf($OldPalette, ([string]$e.color).ToUpper())
            if ($k -ge 0) { $e.color = $Palette[$k]; $changed = $true }
        }
        $lf = [string]$e.logfile
        if ($lf -and $DataDir -ne $OldData -and $lf.StartsWith($OldData + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
            $e.logfile = $DataDir + $lf.Substring($OldData.Length)   # headless log moved with the data folder (ocmux -> terminal-1)
            $changed = $true
        }
        if (-not ($e.PSObject.Properties.Name -contains 'ch') -or -not $e.ch) {
            # every instance gets a channel number (01, 02, ...) that never changes
            $e | Add-Member -NotePropertyName ch -NotePropertyValue (Get-FreeCh $list) -Force
            $changed = $true
        }
    }
    if ($changed) { Save-Reg $list }
    return $list
}
function Get-FreeCh($list) {
    $used = @($list | Where-Object { $_.PSObject.Properties.Name -contains 'ch' -and $_.ch } | ForEach-Object { [int]$_.ch })
    for ($c = 1; $c -lt 100; $c++) { if ($used -notcontains $c) { return $c } }
    return 99
}
function Ch($i) { return ('{0:D2}' -f [int]$i.ch) }

function Save-Reg($list) {
    $json = ConvertTo-Json -InputObject @($list) -Depth 5
    [System.IO.File]::WriteAllText($RegFile, $json, (New-Object System.Text.UTF8Encoding($false)))
}
function Find-Inst($reg, $key) {
    return $reg | Where-Object { $_.name -eq $key -or "$($_.port)" -eq "$key" } | Select-Object -First 1
}

# ------------------------------------------------------------------ helpers
function Test-Health([string]$url) {
    try {
        $req = [System.Net.HttpWebRequest]::Create("$url/global/health")
        $req.Proxy = $null
        $req.Timeout = 1500
        if ($env:OPENCODE_SERVER_PASSWORD) {
            $tok = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("opencode:$($env:OPENCODE_SERVER_PASSWORD)"))
            $req.Headers.Add('Authorization', "Basic $tok")
        }
        $resp = $req.GetResponse(); $resp.Close(); return $true
    } catch [System.Net.WebException] {
        # older opencode without /global/health -> 404, but any HTTP response means the server is up
        return ($null -ne $_.Exception.Response)
    } catch { return $false }
}
function Test-PortFree([int]$p) {
    try {
        $l = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, $p)
        $l.Start(); $l.Stop(); return $true
    } catch { return $false }
}
function Get-FreePort($reg) {
    $used = @($reg | ForEach-Object { [int]$_.port })
    for ($p = $BasePort; $p -lt $BasePort + 200; $p++) {
        if ($used -notcontains $p -and (Test-PortFree $p)) { return $p }
    }
    throw "no free port from $BasePort"
}
function Q([string]$s) {
    # "C:\" would end with \" (an escaped quote) -> double the trailing backslash
    if ($s.EndsWith('\')) { $s += '\' }
    # ';' separates wt sub-commands even inside quotes -> escape it
    return '"' + ($s -replace ';', '\;') + '"'
}
function Sync-PwFile {
    # The panes need OPENCODE_SERVER_PASSWORD, but new tabs of an already-open WT window do not inherit
    # this shell's environment. Passing it as --password would put it on every pane's command line
    # (visible to process listings and EDR command-line logs), so hand it over through a file in the
    # per-user data folder instead; the monitor reads the env var first, then this file.
    if ($env:OPENCODE_SERVER_PASSWORD) {
        [System.IO.File]::WriteAllText($PwFile, $env:OPENCODE_SERVER_PASSWORD, (New-Object System.Text.UTF8Encoding($false)))
    } elseif (Test-Path $PwFile) {
        Remove-Item $PwFile -Force
    }
}
function Invoke-WT([string]$wtArgs) {
    if (-not (Get-Command wt -ErrorAction SilentlyContinue)) { throw 'Windows Terminal (wt.exe) not found' }
    Install-Scheme
    Sync-PwFile
    Write-Verbose "wt $wtArgs"
    Start-Process wt -ArgumentList $wtArgs
}
function Stop-Tree($procId) {
    if (-not $procId) { return }
    $p = Get-Process -Id $procId -ErrorAction SilentlyContinue
    if (-not $p) { return }                                   # already gone
    # after a reboot the PID may belong to something else -> only kill our own launcher/opencode
    if (@('cmd', 'opencode', 'node', 'bun') -notcontains $p.ProcessName) { return }
    # run through cmd so a 'not found' on stderr never becomes a terminating error in PS 5.1
    try { cmd.exe /c "taskkill /PID $procId /T /F >nul 2>&1" | Out-Null } catch { }
}
function PwArg([string]$flag) {
    if ($env:OPENCODE_SERVER_PASSWORD) { return " $flag " + (Q $env:OPENCODE_SERVER_PASSWORD) } else { return '' }
}

# ------------------------------------------------------------------ tab builders
function Py([string]$mode, [string]$rest) {
    $x = "cmd /k $Python $(Q $Monitor) $mode $rest"
    if ($NoLogs) { $x += ' --no-logs' }
    return $x
}
function Get-BottomRow([string]$dir, [string]$usageArgs) {
    if ($Compact) { return '' }
    $heroArg = if ($PetName) { " --hero $(Q $PetName)" } else { '' }
    $a  = " ; split-pane -H -s $BottomHeight --colorScheme $(Q $Scheme) -d $dir $(Py 'usage' $usageArgs)"
    if (-not $NoPet) {
        $a += " ; split-pane -V -s $GameWidth --colorScheme $(Q $Scheme) -d $dir $(Py 'rpg' ($usageArgs + $heroArg))"
    }
    return $a
}
function Get-OverviewTabArgs {
    $d = Q $DataDir
    $a  = "new-tab --title $(Q '00 overview') --suppressApplicationTitle --tabColor $(Q '#08365E') --colorScheme $(Q $Scheme) -d $d $(Py 'overview' '--level WARN')"
    $a += Get-BottomRow $d '--all'
    $a += ' ; focus-pane -t 0'
    return $a
}
function Get-InstanceTabArgs($i) {
    $d     = Q $i.dir
    $title = Q ("{0} {1} :{2}" -f (Ch $i), $i.name, $i.port)
    $who  = "--url $($i.url) --name $(Q $i.name) --color $($i.color)"   # password: env / $PwFile (see Sync-PwFile)
    if ($i.headless) {
        $main   = "cmd /k opencode attach $($i.url)$(PwArg '-p') --dir $d"
        $logSrc = "--file $(Q $i.logfile)"
    } else {
        $main   = "cmd /k opencode --port $($i.port) --hostname $HostName"
        $logSrc = "--since $($i.created)"
    }
    $a  = "new-tab --title $title --suppressApplicationTitle --tabColor $(Q $i.color) --colorScheme $(Q $Scheme) -d $d $main"
    # the folder is read from the registry (--reg-dir), not put on the cmd line where cmd would expand %...%
    $a += " ; split-pane -V -s $RightWidth --colorScheme $(Q $Scheme) -d $d $(Py 'status' "$who --reg-dir $logSrc")"
    $a += Get-BottomRow $d $who
    $a += ' ; focus-pane -t 0'
    if (-not $NoCompose) {
        # big input pane under the TUI (Ctrl+V paste, Ctrl+S send) - focus stays here
        $a += " ; split-pane -H -s $ComposeHeight --colorScheme $(Q $Scheme) -d $d $(Py 'compose' $who)"
    }
    return $a
}

# ------------------------------------------------------------------ commands
switch ($Cmd) {

'add' {
    if (-not (Test-Path $Monitor)) { throw "t1_monitor.py not found: $Monitor" }
    if (-not (Get-Command opencode -ErrorAction SilentlyContinue)) { throw 'opencode not in PATH' }
    $dir = if ($Target) { (Resolve-Path $Target).ProviderPath } else { (Get-Location).ProviderPath }
    if ($Headless -and $dir.Contains('%')) {
        # headless panes run `opencode attach ... --dir <folder>` through cmd, which expands %NAME%
        throw "-Headless cannot use a folder whose path contains '%' ($dir). Rename the folder or add it without -Headless"
    }
    $reg = @(Get-Reg)
    $firstEver = ($reg.Count -eq 0)

    $base = if ($Name) { $Name } else { Split-Path $dir -Leaf }
    # the name ends up inside wt/cmd command lines: " breaks the quoting, % ^ & | < > are cmd metacharacters
    if ($base -match '["%^&|<>]') {
        if ($Name) { throw "name must not contain any of: `" % ^ & | < >  (got '$Name')" }
        $base = $base -replace '["%^&|<>]', '_'
    }
    $n = $base; $k = 2
    while (Find-Inst $reg $n) { $n = "$base-$k"; $k++ }

    $p = if ($Port -gt 0) { $Port } else { Get-FreePort $reg }
    $url = "http://${HostName}:$p"
    $inst = [ordered]@{
        name     = $n
        dir      = $dir
        port     = $p
        url      = $url
        color    = $Palette[$reg.Count % $Palette.Count]
        headless = [bool]$Headless
        pid      = $null
        logfile  = $null
        created  = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
        ch       = Get-FreeCh $reg
    }

    if ($Headless) {
        $inst.logfile = Join-Path $LogDir "$n.log"
        Say 'SERVE' "starting opencode serve ($n) on $url" '...' 'DarkGray'
        $proc = Start-Process cmd.exe -WindowStyle Hidden -PassThru -WorkingDirectory $dir `
            -ArgumentList "/c opencode serve --port $p --hostname $HostName --print-logs --log-level INFO 2> $(Q $inst.logfile)"
        $inst.pid = $proc.Id
        $ok = $false
        for ($t = 0; $t -lt 40; $t++) { if (Test-Health $url) { $ok = $true; break }; Start-Sleep -Milliseconds 500 }
        if (-not $ok) { Stop-Tree $proc.Id; throw "server did not come up at $url (20s). see $($inst.logfile)" }
    }

    $reg += [pscustomobject]$inst
    Save-Reg $reg

    $wtArgs = "-w $Window "
    if ($firstEver -and -not $NoOverview) { $wtArgs += (Get-OverviewTabArgs) + ' ; ' }
    $wtArgs += Get-InstanceTabArgs ([pscustomobject]$inst)
    Invoke-WT $wtArgs
    Say 'ADD' ("{0}  {1,-16} {2}" -f ('{0:D2}' -f [int]$inst.ch), $n, $url) $dir
}

'overview' {
    Invoke-WT ("-w $Window " + (Get-OverviewTabArgs))
}

'focus' {
    $i = Find-Inst (Get-Reg) $Target
    if (-not $i) { throw "no instance '$Target'" }
    if (-not $i.headless -and -not (Test-Health $i.url)) {
        # TUI mode: tab was closed -> relaunch opencode on the same port
        $i.created = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    }
    Invoke-WT ("-w $Window " + (Get-InstanceTabArgs $i))
}

'ls' {
    $reg = @(Get-Reg)
    if ($reg.Count -eq 0) { Say 'LS' 'no instances' '-> terminal-1 add' 'DarkGray'; break }
    # TE-style table: channel number, name, port, mode, state LED, folder
    Txt (" {0,-3} {1,-18} {2,-6} {3,-9} {4,-10} {5}" -f 'CH', 'NAME', 'PORT', 'MODE', 'STATE', 'DIR') 'DarkGray'
    Write-Host ''
    foreach ($i in ($reg | Sort-Object { [int]$_.ch })) {
        $on = Test-Health $i.url
        Chip (Ch $i) 'DarkGreen' 'Black'
        Txt (" {0,-18} {1,-6} {2,-9} " -f $i.name, $i.port, $(if ($i.headless) { 'headless' } else { 'tui' }))
        if ($on) { Txt '● online   ' 'Green' } else { Txt '○ offline  ' 'DarkGray' }
        Txt $i.dir 'DarkGray'
        Write-Host ''
    }
}

'rm' {
    $reg = @(Get-Reg)
    $i = Find-Inst $reg $Target
    if (-not $i) { throw "no instance '$Target'" }
    if ($i.headless) { Stop-Tree $i.pid }
    Save-Reg @($reg | Where-Object { $_.name -ne $i.name })
    Say 'RM' ("{0}  {1}" -f (Ch $i), $i.name) 'close its tab with Ctrl+Shift+W' 'Gray'
}

'prune' {
    $reg = @(Get-Reg)
    $keep = @($reg | Where-Object { Test-Health $_.url })
    Save-Reg $keep
    Say 'PRUNE' ("{0} offline instance(s) removed" -f ($reg.Count - $keep.Count)) '' 'Gray'
}

'setup' { Install-Scheme; Say 'SCHEME' "'$Scheme' ready" }

'version' { "Terminal-1 $(Get-Version)" }

'help' { Get-Help $PSCommandPath -Detailed | Out-String -Width 120 }  # Out-String: with redirected output pwsh 7 printed only blank lines
}

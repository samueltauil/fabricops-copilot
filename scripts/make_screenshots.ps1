$ErrorActionPreference = "Stop"
$cfg = "config\examples\synthetic-healthcare\project.yml"
$tmp = "artifacts\shots"
$state = ".fabricops\shots-state.json"
Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
Remove-Item -Force $state -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $tmp | Out-Null

function Shot($name, $title, $text) {
    Set-Content -Path "$tmp\$name.txt" -Value $text -Encoding utf8
    python scripts\render_terminal.py $title "$tmp\$name.txt" "docs\images\$name.png"
}

# 1. Preview plan
python -m fabricops.cli plan --config $cfg --state $state --use-case all --output "$tmp\plan" | Out-Null
$plan = Get-Content "$tmp\plan\all-plan.md" | Select-Object -First 22
Shot "01-plan-preview" "fabricops plan" (@('$ fabricops plan --use-case all', '') + $plan)

# 2. Demo: first run, then rerun proves idempotency
python -m fabricops.cli demo --config $cfg --state $state --output "$tmp\demo" --data-dir "$tmp\synthea" --tools-dir ".fabricops\tools" | Out-Null
$first = Get-Content "$tmp\demo\demo-summary.json" -Raw | ConvertFrom-Json
$lines = @('$ fabricops demo   # first run, then an automatic rerun', '', ('{0,-12} {1,-26} {2}' -f 'USE CASE','FIRST RUN','RERUN'))
foreach ($r in $first) {
    $f = ($r.firstRun.PSObject.Properties | ForEach-Object { "$($_.Name)=$($_.Value)" }) -join ', '
    $s = ($r.rerun.PSObject.Properties | ForEach-Object { "$($_.Name)=$($_.Value)" }) -join ', '
    $lines += ('{0,-12} {1,-26} {2}' -f $r.useCase, $f, $s)
}
Shot "02-idempotent-demo" "fabricops demo" $lines

# 3. TUI health and drift
$tui = ("4`n`n5`n`n7`n" | python -m fabricops.cli tui --config $cfg --state $state --output "$tmp\tui") -join "`n"
$tuiLines = @('$ fabricops tui') + ($tui -split "`n" | Where-Object { $_ -notmatch '^\s*$' -and $_ -notmatch 'Press Enter' } | Select-Object -First 28)
Shot "03-admin-tui" "fabricops tui" $tuiLines

# 4. Synthea dataset
$syn = Get-Content "$tmp\demo\synthea-dataset.json" -Raw
Shot "04-synthea-dataset" "fabricops synthea" (@('$ fabricops synthea', '') + ($syn -split "`r?`n"))

# 5. Tests
$tests = python -m pytest -q 2>&1
Shot "06-tests" "pytest" (@('$ pytest -q') + $tests)

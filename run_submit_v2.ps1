$env:V2_ENABLE_BING_HTML = '0'
$env:V2_ENABLE_ROUTE_META_QUERIES = '0'
$env:V2_ENABLE_DUCKDUCKGO = '0'
$env:V2_ENABLE_PLAYWRIGHT = '1'
$env:V2_ENABLE_ROUTE_PLAYWRIGHT_QUERIES = '1'
$env:V2_PLAYWRIGHT_MAX_QUERIES_PER_CLAIM = '1'
$env:V2_MAX_CLAIMS = '5'
$env:V2_MAX_RESULTS_PER_QUERY = '2'
$env:V2_MAX_QUERIES_PER_CLAIM = '4'
$env:V2_RETRIEVAL_TIMEOUT = '6'
$env:V2_RETRIEVAL_BUDGET_SEC = '180'
$env:V2_FETCH_DETAILS = '1'
$env:V2_FETCH_DETAILS_PER_CLAIM = '2'
$env:V2_ENABLE_REWRITE = '1'
$env:V2_WORKERS = '4'
$env:V2_ENABLE_LLM_CACHE = '0'

python "$PSScriptRoot\solve_v2.py" `
  --input "$PSScriptRoot\data.json" `
  --output "$PSScriptRoot\output\results.json" `
  --workers $env:V2_WORKERS

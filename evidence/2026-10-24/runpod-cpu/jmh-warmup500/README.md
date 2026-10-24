# Further CPU warmup sensitivity

All15fresh cases passed3forks ×500warmup ×10measurement iterations. Complete raw logs, JSON, exact plan and independent Cartesian-case verification are retained. No code changed from the warmup5/100 cohort. These are64-command batch means, not per-order p99 or full-platform throughput.

|Action|Levels|Trades|Warmup100 us|Warmup500 us|500/100|
|---|---:|---:|---:|---:|---:|
|MATCH|1|1|0.758059|0.353474|0.466|
|MATCH|1|10|0.829775|0.768023|0.926|
|MATCH|1|100|4.350137|3.697077|0.850|
|MATCH|100|1|0.743584|1.434173|1.929|
|MATCH|100|10|0.895512|0.896740|1.001|
|MATCH|100|100|5.833351|3.474977|0.596|
|MATCH|10000|1|0.620155|0.236515|0.381|
|MATCH|10000|10|1.368037|0.743080|0.543|
|MATCH|10000|100|7.711453|4.921100|0.638|
|PLACE|1|0|0.480845|0.311080|0.647|
|PLACE|100|0|0.488065|0.236297|0.484|
|PLACE|10000|0|0.613679|0.325236|0.530|
|CANCEL|1|0|0.497186|0.213123|0.429|
|CANCEL|100|0|0.595656|0.245456|0.412|
|CANCEL|10000|0|0.787376|0.455341|0.578|

Warmup100 still materially affects small fixtures. Use500warmup iterations consistently for the next core code comparison, retaining every fork and reporting uncertainty. This recommendation supersedes the earlier100-iteration comparison choice; earlier raw data stays unchanged. Last50-versus-previous50 warmup means for all45forks are retained in[comparison](warmup-comparison.json); short-window variation is not a JIT or scheduling guarantee.

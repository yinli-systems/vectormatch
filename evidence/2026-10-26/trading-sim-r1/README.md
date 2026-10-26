# Synthetic trading campaign

Read [the result and limitations](../../../docs/TRADING_SIMULATION_RESULTS.md).
All evidence concerns synthetic accounts/orders on the existing CPU Pod.

Private raw asset679262900 in draft release423510304 contains450 original members,
including both library artifacts,source patch,original traces,samples,events,
canonical states,Aeron files,JFR,metrics,controllers and failed audit/test records.
Size74472080 bytes;SHA-256
`909e3ef50bbecf4781d237745619d882bc0a3905fe5f3824720a528fe09de95a`.
Both complete local download copies and every member hash were verified.
The expanded archive contains about3.25GB; use at least4GB free disk for extraction.

With authorized access to this private repository:

```sh
gh api -H 'Accept: application/octet-stream' \
  repos/yinli-systems/vectormatch/releases/assets/679262900 > raw.tar.gz
shasum -a 256 raw.tar.gz
# Verify the exact SHA above before extracting into a fresh directory.
tar -xzf raw.tar.gz
python3 scripts/audit-trading-simulation.py trading-sim-20261026-r1 --output new-core-audit.json
python3 scripts/audit-trading-polling.py trading-sim-20261026-r1/polling \
  --jfr "$JAVA_HOME/bin/jfr" --output new-polling-audit.json
```

The cache candidate fails its promotion rule and is not the default implementation.
Both replicated polling pairs pass their finite latency-direction gates. No
sustained capacity,HFT SLA,physical-fault or funded external-trading claim follows.
`POLLING_AUDIT_V2.json` repeats the native audit with the current portable auditor;
the earlier raw-archive auditor/report is preserved. The later source-only
leader/time-window additions were not part of the measured JAR.

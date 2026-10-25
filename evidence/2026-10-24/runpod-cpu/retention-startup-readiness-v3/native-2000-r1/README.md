# All-member-ready fixed-read128 capacity 2000/s

Fresh40000-order lineage over20seconds. Confirmed in-window accepted goodput 1996.65/s,all-arrival scheduled-to-reply p99 228817372ns,notSent 0,rejected 0,observed/final unknown 0/0.

Original native controller,all-member startup and pre-load gates,complete native/member inventories,CSV and all physical request/reply/identity/result/offer bindings passed. Both readiness gates use original owned PIDs and read-only CnC samples,expected roles/term0/closed elections/same commit positions,shared Archive/driver error counting and a2s quiet period. Both gates close before arrivals;5s pre-load warm-up remains between setup and the second gate. Sampling is non-atomic. No JFR.

Source e5ac8f7ccb872c2f98c2857aec51ce189b905376,actual code1a9ee9586e83c32d6ddab3cf89e927b6ecbb2639b30dab506f8b43c2c774f494;leader0,sync2,read128,page32,batch4,chunk6144,owner1ms,driver100us,W128Q64,one physical client session. Three JVMs share one CPU host over loopback UDP. Explicit Aeron-first classpath agrees with the73-test runtime and8 actual Linux class origins.

Full original native TARs,raw bodies,decoded frames and review inputs are retained. Files above32MiB are losslessly partitioned with complete original paths/lengths/SHA/mode/owner and ordered part hashes. The included lossless_parts.py verifies or reconstructs all original bytes. No samples are discarded.

This new startup-qualified artifact/cohort is separate from the previous3acc8428 capacity curve. A20s observation is not sustained capacity,an independent matching oracle,cold recovery,hard realtime,zero latency or a100M result. Original failed startup artifacts remain archived. No new resource was created.

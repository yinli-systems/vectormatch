# Node-idle treatment B1:100us maximum park

Registered fixed18k/s,350kfresh arrivals,W128/Q64,source433,leader0,sync2,three JVMs on one CPU host over loopback UDP. Only node maximum park changes from A1's1ms to100us;client driver/owner/scheduler and queues remain unchanged.

Independent31e4 result:valid finite stable window, 17986.474286/s confirmed inside arrival window. All350000commands accepted,not-sent/reject/server-error/initial-UNKNOWN/final-UNKNOWN0. All-offered accepted p99 80.193542ms;drain 0.015863792s. Full canonical/asset/leader/configuration/actual-idle-instance checks and complete native archive passed;all owned processes stopped.

This is the first treatment repetition, not a sustained ceiling or production SLA. A2/B2 are still required. A1 had dropped arrivals and therefore no all-offered p99;its conditional accepted tail cannot be relabeled as an all-arrival baseline.

[Analysis](analysis/summary.json),[completion](completion.json),[idle instances](raw/evidence/runs/cpu-capacity-idle-b1-18000-w128-r1/node-idle-variant-verification.json).

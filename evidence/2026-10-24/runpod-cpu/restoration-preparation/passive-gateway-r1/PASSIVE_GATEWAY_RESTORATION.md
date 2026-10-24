# Passive gateway startup for an existing cluster

Base source: `e1db2e755a834234efb60b7a1ed291b31ce33c16`. The existing defaults remain enabled. An existing cluster restoration must explicitly set both JVM properties before construction:

```
-Dvm.bootstrap.enabled=false -Dvm.flow.enabled=false
```

`vm.bootstrap.enabled=false` skips the constructor's six deposits and 32 seed orders. `vm.flow.enabled=false` initializes flow as disabled before clock tasks or an HTTP socket exist. Disabling flow through HTTP after startup cannot prevent constructor seeding or the startup race. Unspecified properties retain the original bootstrap and synthetic flow behavior.

These properties disable automatic startup commands. They do not make order/cancel/control HTTP routes read-only, stop explicit user writes, or stop mirror polling and WebSocket publication. The server remains bound to loopback. They do not reset/rewrite a cluster, database, cursor or producer identity. The existing local journal replay behavior is unchanged.

The only production source change is Workbench initialization and its conditional seed call. Tests exercise a recording cluster adapter with a nonempty authoritative snapshot: constructor and three actual scheduled ticks before HTTP bind issue zero business calls and preserve all canonical bytes. A separate actual Netty server test waits before binding, verifies a header-only journal, then reads HTTP state with disabled flow and zero commands. The existing API, retry/recovery, WebSocket, mirror and projection-observer tests still run.

Validation: actual forced local `:server:test :server:installDist --rerun-tasks`, 17 tests passed, zero failed/skipped; 13 actionable tasks executed. This includes two new behavior tests, not networked Aeron or restored PostgreSQL execution. No cloud deployment or performance claim is made.

All four actual compiled module class ZIPs, server sources, complete distribution JARs, XML, command/log and a before/after JAR entry comparison are preserved under `build/passive-gateway-validation`. The actual freshly tested distribution has new project JAR container hashes. Comparison against the original same-source restore bundle confirms every uncompressed dependency/project entry is byte-identical except `io/vectormatch/server/Workbench.class`. It is an opt-in gateway adaptation, not original gateway binary identity.

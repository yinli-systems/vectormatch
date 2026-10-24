# CPU cohort, 2026-10-24

User supplied existing prepaid/free CPU Pod and authorized continuous use; no additional resource was opened. Source, machine, artifact and trial identities remain distinct from old GPU cohorts.

- [Observed host/cgroups/filesystems](preflight.json):32 allowed logical CPUs,16SMT pairs,64GB memory limit; no exclusive-core claim.
- [Verified cluster433 deployment](deployment.json), pinned Temurin21.0.13+9. Measured state uses container overlayfs; FUSE /workspace is archive only.
- [Replicated smoke](replicated-smoke/cpu-replicated-smoke-433-r1/independent-verification.json):one actual workload,1002accepted/334trades,0unknown/rejects,reference/canonical/assets pass. The original wrapper failed its filename lookup; its receipt is retained unchanged. Independent verification reads the actual result.json and all1002samples.
- [Strict350k baseline](capacity/cpu-pilot-10000-w128-r2/README.md):10k/s×35s,350kaccepted,all-arrival p9918.51665ms,fullcanonical/leader/configuration and independent raw analysis pass. This is a finite-window stable point, not a ceiling.
- [Capacity protocol](CAPACITY_PROTOCOL.md):single-host three-JVM loopback UDP, not three-machine networking. Each fresh350k run requires fixed leader/configuration, complete identities, terminal outcomes, all-arrival tails and canonical snapshot checks. A pilot is not sustained capacity.
- [JMH deployment](jmh-deployment/deployment.json):all five runtime JARs hashed, generated benchmark discovery verified, core JAR entries identical to deployed cluster433 core. [Registered CPU baseline](jmh/registration.json) separates packaging smoke,16case default matrix and15fresh-case warmup100 sensitivity. Active results are not claimed before final verification.
- [Full142-test source build](tool-validation/jmh-attempts/987f6526b8a0b3c3516ee668a239990cc79fbd8f/jmh-java-tests.json). Earlier22c build failure is retained under tool-validation; it executed no tests.

No CPU capacity ceiling,100M cumulative fresh commands,100M/s,100M connections or hard real-time guarantee has been demonstrated. The original HTTP/PostgreSQL app remains pending CPU restoration; backups survive locally and old GPU Pods are stopped.

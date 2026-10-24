# Local-only candidate builder, not an executable cloud release

Root may invoke this builder only after the NEW Java R2 native functional pair succeeds and the exact source/artifact inputs are frozen. This author has not invoked it. It never uses SSH or cloud APIs, starts no Aeron driver/cluster or business request, and never creates or changes an executable remote release. It creates a fresh LOCAL output directory, preserves any failure and refuses reuse or output within frozen source/preparation/capture roots.

The builder verifies captured source/docs against the explicit final Git commit, all4 captured JAR bytes, complete core/cluster class ZIP/JAR closures, and both successful native arm inventories. It independently reconstructs the native code fingerprint, including actual class-directory versus JAR CodeSources. A separate metadata Java helper is compiled forJava21 and appended AFTER the4 frozen JARs in its classpath. All4 fingerprint anchor classes must actually load from frozen complete JARs. The helper evaluates actual profile, code fingerprint and both selected admitted boundedPlan maps. Python independently reconstructs the complete-JAR fingerprint, including repeated Aeron bytes when DirectBuffer loads from aeron-all, and compares both plans exactly with successful native maps. It does not confuse native class-directory and distribution fingerprints.

The local metadata JDK must be21.0.13; canonical paths/hashes are recorded. The previous CPU candidate's canonical remote JDK hashes and current R3 original-state protection manifest are copied with exact file SHA provenance. This is not a new remote JDK or native-state observation: the later CPU controller preflight independently rechecks them. Actual remote release paths come from the selected immutable controller preparation, normallyR2. Candidate provenance stays inside optional `rootReview` or a separate receipt, preserving the controller's strict known-key release schema.

`release/release.candidate.json` always retains `releaseReady:false`. A detached copy is contract-validated with readiness enabled solely to check shape; the saved candidate is never enabled. Root must review the full actual input/output provenance, freeze a separate final `release/release.json` and independently record its SHA, then stage and run Linux guards/preflight. No files in either frozen source-preparation revision are edited.

Required root invocation shape (NOT executed by this author):

```text
python3 build_candidate.py \
  --preparation /absolute/path/chunk-cloud-abab-preparation-r2 \
  --capture /absolute/path/retention-chunk-v3-worktree/build/chunk-validation/native-r2/artifact-state \
  --capture-sha256 <independently-frozen-r2-manifest-sha> \
  --worktree /absolute/path/retention-chunk-v3-worktree \
  --source-commit <exact-final-40-character-commit> \
  --native-pair /absolute/path/to/the-successful-r2-chunk-pair \
  --previous-candidate /absolute/path/capacity-cloud-pilot-preparation/candidate-release/release.candidate.json \
  --java /absolute/path/.tools/jdk-extract/jdk-21.0.13+9/Contents/Home/bin/java \
  --output /absolute/path/fresh-chunk-cloud-abab-candidate-r2
```

The native candidate may have scheduler-invalid arms; functional success permits candidate preparation but never a valid latency comparison or performance promotion. Both selected source/profile/plan semantics must match. This builder does not replace full sparse-native tar closure verification, raw arrival/RPC reconciliation, Linux execution, budget admission or independent correctness review. A mismatch fails and remains visible. The8 local pure guard fixtures invoke no actual subprocess/JVM, Git, SSH or cloud action.

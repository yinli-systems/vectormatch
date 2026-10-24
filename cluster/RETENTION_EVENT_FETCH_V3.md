# Explicit V3 event fetch pages16/32

This source candidate supports exactly two selected page sizes,16(default) or32. A final partial request may carry1..selected count. Legacy Config/Plan/coordinator constructors select16; legacy CommandCodec.MAX_EVENTS_PER_BATCH and ReplicatedOutbox.fetch still clamp to16. V3 alone uses a bounded fetchV3 entry that returns all32 contiguous original events when available. Detail is never truncated: each event remains limited to128 valid UTF-8 bytes, including multi-byte text.

The actual local codec fixture encodes32 valid maximum-width events, full64-byte scope/hash fields and128-byte outererror, with both Chinese+accent andastral details of exactly128 UTF-8 bytes. The actual complete reply is6763bytes, or6795including the32-byte Aeron session header. Existing8192reply/common6919reply/6951complete envelope remains unchanged. This is a codec witness, not network latency evidence. Illegal33, truncated payloads, malformed UTF-8/surrogates, wrong event ranges and over128-byte Unicode details are rejected.

Config has explicit eventFetchCount/commonEventFetchEnvelope. commonEventFetchPlan calculates both real16/32 codec inventories and takes a conservative union: both arms have equal operational RPC/trace/payload/file/allocated/staging/failure limits. Only selected page and selected prospective RPC counts differ. For the fixed long33792@500/s plan the event fetch bound is4225 versus2113; common maximumRawTraceBytes remains185514924 and maximumAllocatedGrowthBytes remains757122377. The counts are finite admission arithmetic, not observed RPCs or speedup. Existing hard2GiB raw/2.5GiB growth/1GiB floor, journal, writer, sample/path and offer caps are unchanged.

The coordinator accepts an explicit selected page, retains readwindow8 including completed-unconsumed slots, writes original evidence before arm, matches replies by original ranges, verifies identical history/outbox prefixes, and force/readbacks both payloads before either ACK. Page32 error tests retain all8 originals and fence both ACKs. No changes to owner polling/default1ms, driver policies, batchflush50us, readcredit, ACK identities, UNKNOWN retention, retry/deadline renewal or dispatch pause semantics are included.

One explicit fresh-arm source entry is:

    RetentionCapacityAeronPilotV3 <fresh-directory> event-fetch-page-long-cuts 16|32 42000

It requires explicit server/driver100000ns and effective owner1000000ns, fixed long33792@500/read8/chunk6144/cap4/leader0/sync2/ports42000. Invalid selection fails before filesystem/port use. This opt-in feature is now integrated on main after four actual Linux cloud rounds; existing CLI modes/default16 remain available.

The same new artifact must run all replicas and both comparison arms. An old V3 binary only accepts16; this opt-in extension does not make a mixed-binary cluster support32. The wire version/tag/layout is unchanged for16. The completed campaign binds actual Linux installed-JAR metadata and all four rounds to artifact87a7ccd092f4d3c890bf8cc8bd7c6ffcd18900838699cd2b873fd1931cddb6aa.

Completed local proof: first codec/service4tests, then final9classes/47tests/0skip/0failure plus forced installDist. Source/JDK/argv/classpath/XML/class/JAR captures are in runtime/event-fetch-local-validation. Initial4 are included in final47, not51 distinct tests.

Completed performance evidence: a fixed-factor16/32/16/32 campaign used three JVM nodes on one CPU host with loopback UDP, each with33792 fresh synthetic orders at500/s. The paired scheduled-arrival-to-reply p99 values were550.774389→449.890003ms and562.453877→422.691382ms, reductions of18.3168% and24.8487%. All four rounds had zero rejection and UNKNOWN; event-fetch RPCs fell from4225 to2113. The strict LONG parser, full raw TARs, canonical reference checks, three checkpoint logs, independent root reviews and private-push receipts are preserved. Checkpoint logs do not constitute independent snapshot-record decoding or cold-restart proof. See [the full results and evidence links](../docs/EVENT_FETCH_RESULTS.md).

These fixed500/s observations do not establish a throughput ceiling, a three-host network result, statistical significance, hard realtime, zero latency or any100M target. A new read-window32 candidate has a separate artifact and requires its own Linux metadata and native qualification; it cannot reuse this artifact's qualification. Do not reuse scheduler-invalid local proof as strictCPU evidence, bypass raw limits, aggregate different reset lineages into endurance, or alter closed campaign evidence.

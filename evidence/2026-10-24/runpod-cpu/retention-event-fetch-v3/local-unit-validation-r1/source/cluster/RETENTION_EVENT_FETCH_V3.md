# Explicit V3 event fetch pages16/32

This source candidate supports exactly two selected page sizes,16(default) or32. A final partial request may carry1..selected count. Legacy Config/Plan/coordinator constructors select16; legacy CommandCodec.MAX_EVENTS_PER_BATCH and ReplicatedOutbox.fetch still clamp to16. V3 alone uses a bounded fetchV3 entry that returns all32 contiguous original events when available. Detail is never truncated: each event remains limited to128 valid UTF-8 bytes, including multi-byte text.

The actual local codec fixture encodes32 valid maximum-width events, full64-byte scope/hash fields and128-byte outererror, with both Chinese+accent andastral details of exactly128 UTF-8 bytes. The actual complete reply is6763bytes, or6795including the32-byte Aeron session header. Existing8192reply/common6919reply/6951complete envelope remains unchanged. This is a codec witness, not network latency evidence. Illegal33, truncated payloads, malformed UTF-8/surrogates, wrong event ranges and over128-byte Unicode details are rejected.

Config has explicit eventFetchCount/commonEventFetchEnvelope. commonEventFetchPlan calculates both real16/32 codec inventories and takes a conservative union: both arms have equal operational RPC/trace/payload/file/allocated/staging/failure limits. Only selected page and selected prospective RPC counts differ. For the fixed long33792@500/s plan the event fetch bound is4225 versus2113; common maximumRawTraceBytes remains185514924 and maximumAllocatedGrowthBytes remains757122377. The counts are finite admission arithmetic, not observed RPCs or speedup. Existing hard2GiB raw/2.5GiB growth/1GiB floor, journal, writer, sample/path and offer caps are unchanged.

The coordinator accepts an explicit selected page, retains readwindow8 including completed-unconsumed slots, writes original evidence before arm, matches replies by original ranges, verifies identical history/outbox prefixes, and force/readbacks both payloads before either ACK. Page32 error tests retain all8 originals and fence both ACKs. No changes to owner polling/default1ms, driver policies, batchflush50us, readcredit, ACK identities, UNKNOWN retention, retry/deadline renewal or dispatch pause semantics are included.

One explicit fresh-arm source entry is:

    RetentionCapacityAeronPilotV3 <fresh-directory> event-fetch-page-long-cuts 16|32 42000

It requires explicit server/driver100000ns and effective owner1000000ns, fixed long33792@500/read8/chunk6144/cap4/leader0/sync2/ports42000. Invalid selection fails before filesystem/port use. No native pilot or cloud deployment was run for this candidate. Existing CLI modes/default16 remain available.

The same new artifact must run all replicas and both comparison arms. An old V3 binary only accepts16; this opt-in extension does not make a mixed-binary cluster support32. The wire version/tag/layout is unchanged for16. Actual Linux JAR/class-source metadata and homogeneous code fingerprints still need independent new evidence.

Completed local proof: first codec/service4tests, then final9classes/47tests/0skip/0failure plus forced installDist. Source/JDK/argv/classpath/XML/class/JAR captures are in runtime/event-fetch-local-validation. Initial4 are included in final47, not51 distinct tests.

Before any performance claim: create a separate new metadata/helper/controller/release scope for this artifact; add explicit page selection and common-plan binding; adapt the strict LONG raw decoder/auditor for up to32 events and selected requested range while preserving old frozen16 parser bytes; collect actual wire/correlation/phase/owner/header/Image attestations, all3 snapshots/canonical source and fullrawTAR; validate both fresh lineages before a separately authorized fixed-factor comparison. Do not reuse scheduler-invalid local proof as strictCPU evidence, bypass raw limits, aggregate different lineages into endurance, or alter current frozen owner ABAB cloud resources.

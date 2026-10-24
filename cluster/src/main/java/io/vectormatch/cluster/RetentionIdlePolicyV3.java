package io.vectormatch.cluster;

import io.aeron.archive.Archive;
import io.aeron.archive.ArchiveThreadingMode;
import io.aeron.cluster.ConsensusModule;
import io.aeron.cluster.service.ClusteredServiceContainer;
import io.aeron.driver.MediaDriver;
import io.aeron.driver.ThreadingMode;
import org.agrona.concurrent.BackoffIdleStrategy;
import org.agrona.concurrent.IdleStrategy;

import java.io.IOException;
import java.nio.file.*;
import java.time.Instant;
import java.util.*;

/** Explicit retention-only experiment. No selection preserves the original library supplier paths. */
final class RetentionIdlePolicyV3 {
    static final String PROPERTY = "vectormatch.retention.idleMaxParkNs";
    private static final List<String> HIDDEN_OPTIONS = List.of("JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS");
    private static final List<String> IDLE_OVERRIDES = List.of("aeron.archive.idle.strategy",
            "aeron.archive.recorder.idle.strategy", "aeron.archive.replayer.idle.strategy", "aeron.cluster.idle.strategy",
            "aeron.shared.idle.strategy", "aeron.sharednetwork.idle.strategy", "aeron.sender.idle.strategy",
            "aeron.receiver.idle.strategy", "aeron.conductor.idle.strategy", "aeron.driver.native.resource.agent.idle.strategy");

    record Selection(Long maximumParkNs) {
        Selection {
            if (maximumParkNs != null && maximumParkNs != 100_000L && maximumParkNs != 1_000_000L)
                throw new IllegalArgumentException("retention idle comparison requires100000 or1000000ns");
        }
        boolean explicit() { return maximumParkNs != null; }
        Map<String,Object> observation() {
            return explicit() ? Map.of("schema", "retention-idle-selection-v1", "property", PROPERTY,
                    "maximumParkNs", maximumParkNs, "factor", "maximum requested park only") : Map.of("explicit", false);
        }
        List<String> childArguments(List<String> original) {
            if (!explicit()) return original;
            if (original.isEmpty() || original.stream().anyMatch(s -> s.startsWith("-D" + PROPERTY + "=")))
                throw new IllegalArgumentException("fresh child JVM argument list required");
            var result = new ArrayList<>(original);
            result.add(1, "-D" + PROPERTY + "=" + maximumParkNs);
            return List.copyOf(result);
        }
        String identitySuffix() { return explicit() ? "idleMaxParkNs=" + maximumParkNs + "\n" : ""; }
    }

    static Selection selection(Map<String,String> properties, Map<String,String> environment) {
        String requested = properties.get(PROPERTY);
        for (String option : HIDDEN_OPTIONS) {
            String hidden = environment.getOrDefault(option, "");
            if (hidden.contains("vectormatch.retention.idle"))
                throw new IllegalArgumentException("retention idle selection must be explicit, not hidden in " + option);
            if (requested != null && IDLE_OVERRIDES.stream().anyMatch(hidden::contains))
                throw new IllegalArgumentException("conflicting hidden idle override in " + option);
        }
        if (requested == null) return new Selection(null);
        if (!requested.equals("100000") && !requested.equals("1000000"))
            throw new IllegalArgumentException(PROPERTY + " must be exactly100000 or1000000");
        for (String property : IDLE_OVERRIDES) if (properties.containsKey(property))
            throw new IllegalArgumentException("explicit retention idle arm conflicts with " + property);
        return new Selection(Long.valueOf(requested));
    }

    static Selection systemSelection() {
        var properties = new HashMap<String,String>();
        for (String key : IDLE_OVERRIDES) if (System.getProperty(key) != null) properties.put(key, System.getProperty(key));
        if (System.getProperty(PROPERTY) != null) properties.put(PROPERTY, System.getProperty(PROPERTY));
        return selection(properties, System.getenv());
    }

    static final int MAX_STARTUP_OBSERVATIONS = 256;
    record StartupObservation(Path actualFile, int node, Selection selection) {
        void complete(Map<String,Object> actual) throws IOException {
            if (!Objects.equals(actual.get("node"),node) || !selection.observation().equals(actual.get("selection")))
                throw new IllegalArgumentException("startup observation must match reserved node/selection");
            RetentionCapacityJsonV3.writeNew(actualFile,actual);
        }
    }
    /** Reserve before launch; a failed launch consumes its slot and can never erase earlier evidence. */
    static StartupObservation reserveStartupObservation(Path nodeRoot, int node, Selection selection) throws IOException {
        if (!selection.explicit()) throw new IllegalArgumentException("explicit startup observation required");
        Path directory = nodeRoot.resolve("idle-observations");
        if (!Files.exists(directory,LinkOption.NOFOLLOW_LINKS)) Files.createDirectory(directory);
        if (Files.isSymbolicLink(directory) || !Files.isDirectory(directory,LinkOption.NOFOLLOW_LINKS))
            throw new IOException("unsafe idle observation directory");
        try (var entries=Files.newDirectoryStream(directory)) {
            int count=0;
            for(Path entry:entries) {
                if(++count>2*MAX_STARTUP_OBSERVATIONS || !entry.getFileName().toString().matches("idle-(?:[01][0-9]{2}|2[0-4][0-9]|25[0-5])\\.(?:intent|actual)\\.json")
                        || Files.isSymbolicLink(entry) || !Files.isRegularFile(entry,LinkOption.NOFOLLOW_LINKS) || Files.size(entry)>1024*1024)
                    throw new IOException("unbounded or unsafe idle observation entry");
                if(entry.getFileName().toString().contains(".actual.") && !Files.isRegularFile(
                        directory.resolve(entry.getFileName().toString().replace(".actual.",".intent.")),LinkOption.NOFOLLOW_LINKS))
                    throw new IOException("idle actual observation lacks its original intent");
            }
        }
        for(int slot=0;slot<MAX_STARTUP_OBSERVATIONS;slot++) {
            String prefix=String.format(Locale.ROOT,"idle-%03d",slot);
            Path intent=directory.resolve(prefix+".intent.json"),actual=directory.resolve(prefix+".actual.json");
            if(Files.exists(intent,LinkOption.NOFOLLOW_LINKS))continue;
            try {
                RetentionCapacityJsonV3.writeNew(intent,Map.of("schema","retention-idle-startup-intent-v1","slot",slot,
                        "node",node,"pid",ProcessHandle.current().pid(),"atUTC",Instant.now().toString(),"selection",selection.observation()));
                return new StartupObservation(actual,node,selection);
            } catch(FileAlreadyExistsException concurrentReservation) {
                if(Files.isSymbolicLink(intent)||!Files.isRegularFile(intent,LinkOption.NOFOLLOW_LINKS))throw new IOException("unsafe concurrent idle intent",concurrentReservation);
            }
        }
        throw new IOException("bounded256 idle startup observations exhausted before launch; preserve all previous attempts");
    }

    private final Selection selection;
    private final int node;
    private final Map<String,List<String>> expectedUses;
    private final Map<String,List<IdleStrategy>> actual = new TreeMap<>();
    private final Map<IdleStrategy,Integer> identities = new IdentityHashMap<>();
    private final Map<IdleStrategy,List<Map<String,Object>>> callers = new IdentityHashMap<>();
    private Archive.Context installedArchive;
    private ConsensusModule.Context installedConsensus;
    private ClusteredServiceContainer.Context installedService;
    private static final int CALLER_FRAME_LIMIT=5,CALLER_TEXT_BYTE_LIMIT=256;

    private RetentionIdlePolicyV3(Selection selection, int node, Map<String,List<String>> expectedUses) {
        if (!selection.explicit()) throw new IllegalArgumentException("explicit retention idle selection required");
        this.selection = selection; this.node = node; this.expectedUses = Map.copyOf(expectedUses);
    }
    static RetentionIdlePolicyV3 node(Selection selection, int node) {
        if (node < 0 || node > 2) throw new IllegalArgumentException("retention node must be0..2");
        return selection.explicit() ? new RetentionIdlePolicyV3(selection, node, Map.of(
                "driver-shared",List.of("directly installed shared-driver context object"),
                "archive-shared",List.of("control-subscription registration retry helper; may never idle", "Archive shared AgentRunner"),
                "consensus",List.of("ConsensusModuleAgent internal waits", "ConsensusModule AgentRunner"),
                "service",List.of("ClusteredServiceAgent internal waits", "ClusteredServiceContainer AgentRunner"))) : null;
    }
    static RetentionIdlePolicyV3 owner(Selection selection) {
        return selection.explicit() ? new RetentionIdlePolicyV3(selection, -1,
                Map.of("owner-driver-shared",List.of("directly installed shared-driver context object"))) : null;
    }

    synchronized BackoffIdleStrategy driver() {
        return create(node < 0 ? "owner-driver-shared" : "driver-shared", 5);
    }
    synchronized BackoffIdleStrategy agent(String role) {
        if (!Set.of("archive-shared","consensus","service").contains(role))
            throw new IllegalArgumentException("unknown selected agent role: " + role);
        return create(role,20);
    }
    private synchronized BackoffIdleStrategy create(String role, int yields) {
        var uses=expectedUses.get(role);
        if (uses==null || actual.getOrDefault(role,List.of()).size()>=uses.size())
            throw new IllegalStateException("bounded fresh idle consumption inventory exceeded: " + role);
        // Agrona2.6.1 no-arg driver:10/5/1000/1ms; Aeron1.53.3 agent factory:10/20/1000/1ms.
        var idle = new BackoffIdleStrategy(10,yields,1000,selection.maximumParkNs());
        if (identities.put(idle,identities.size()+1)!=null) throw new IllegalStateException("mutable idle instance reused");
        actual.computeIfAbsent(role,key -> new ArrayList<>()).add(idle);
        callers.put(idle,StackWalker.getInstance().walk(frames -> frames
                .filter(frame -> !frame.getClassName().equals(RetentionIdlePolicyV3.class.getName())).limit(CALLER_FRAME_LIMIT)
                .map(frame -> Map.<String,Object>of("class",boundedTraceText(frame.getClassName()),"method",boundedTraceText(frame.getMethodName()),
                        "classTruncated",!boundedTraceText(frame.getClassName()).equals(frame.getClassName()),
                        "methodTruncated",!boundedTraceText(frame.getMethodName()).equals(frame.getMethodName()),"line",frame.getLineNumber())).toList()));
        return idle;
    }
    static String boundedTraceText(String value) {
        int bytes=0,end=0;
        while(end<value.length()) {
            int cp=value.codePointAt(end),width=cp<=0x7f?1:cp<=0x7ff?2:cp<=0xffff?3:4;
            if(bytes+width>CALLER_TEXT_BYTE_LIMIT)break;
            bytes+=width;end+=Character.charCount(cp);
        }
        return value.substring(0,end);
    }
    private static void requireAgentScope(Archive.Context archive,ConsensusModule.Context consensus) {
        if (archive.threadingMode()!=ArchiveThreadingMode.SHARED || !archive.controlChannelEnabled() || consensus.useAgentInvoker())
            throw new IllegalStateException("fixed idle inventory requires shared Archive, enabled control channel, and agent-runner consensus");
    }
    static void applyAgents(RetentionIdlePolicyV3 policy, Archive.Context archive,
                            ConsensusModule.Context consensus, ClusteredServiceContainer.Context service) {
        if (policy == null) return;
        if (policy.node < 0 || policy.installedArchive != null) throw new IllegalStateException("one node context installation required");
        requireAgentScope(archive,consensus);
        policy.installedArchive = archive; policy.installedConsensus = consensus; policy.installedService = service;
        archive.idleStrategySupplier(() -> policy.agent("archive-shared"));
        consensus.idleStrategySupplier(() -> policy.agent("consensus"));
        service.idleStrategySupplier(() -> policy.agent("service"));
    }
    synchronized Map<String,Object> ownerAttestation(MediaDriver.Context media) {
        if (node >= 0) throw new IllegalStateException("owner-only attestation required");
        requireDriver(media,"owner-driver-shared");
        return completeAttestation();
    }
    synchronized Map<String,Object> nodeAttestation(MediaDriver.Context media, Archive.Context archive,
            ConsensusModule.Context consensus, ClusteredServiceContainer.Context service) {
        if (node < 0) throw new IllegalStateException("node-only attestation required");
        requireDriver(media,"driver-shared"); requireAgentScope(archive,consensus);
        // No supplier getter exists. Never invoke a supplier again to manufacture an observation.
        if (archive != installedArchive || consensus != installedConsensus || service != installedService)
            throw new IllegalStateException("selected idle contexts differ from the installed contexts");
        return completeAttestation();
    }
    private void requireDriver(MediaDriver.Context media,String role) {
        var instances=actual.getOrDefault(role,List.of());
        if (media.threadingMode()!=ThreadingMode.SHARED || instances.size()!=1 || media.sharedIdleStrategy()!=instances.getFirst())
            throw new IllegalStateException("selected actual shared-driver instance differs");
    }
    private Map<String,Object> completeAttestation() {
        var expectedCounts=new TreeMap<String,Integer>();var observedCounts=new TreeMap<String,Integer>();
        expectedUses.forEach((role,uses) -> expectedCounts.put(role,uses.size()));
        actual.forEach((role,instances) -> observedCounts.put(role,instances.size()));
        int total=actual.values().stream().mapToInt(List::size).sum();
        if (!observedCounts.equals(expectedCounts) || total!=identities.size() || total!=callers.size())
            throw new IllegalStateException("exact bounded factory consumption inventory incomplete: " + observedCounts);
        var rows=new ArrayList<Map<String,Object>>();
        for (var entry:actual.entrySet()) {
            String role=entry.getKey();int yields=role.contains("driver")?5:20;int call=0;
            for(IdleStrategy idle:entry.getValue()) {
                String expectedText="BackoffIdleStrategy{alias=backoff, maxSpins=10, maxYields="+yields
                        +", minParkPeriodNs=1000, maxParkPeriodNs="+selection.maximumParkNs()+"}";
                if(!idle.toString().equals(expectedText))throw new IllegalStateException("actual idle configuration differs");
                var row=new LinkedHashMap<String,Object>();
                row.put("role",role);row.put("instanceOrdinal",identities.get(idle));row.put("roleConsumptionOrdinal",++call);
                row.put("roleConsumptionBound",expectedUses.get(role).size());row.put("strategyClass",idle.getClass().getName());
                row.put("strategyDescription",idle.toString());row.put("maximumSpins",10);row.put("maximumYields",yields);
                row.put("minimumParkNs",1000);row.put("maximumParkNs",selection.maximumParkNs());
                row.put("sourceDerivedIntendedUse",expectedUses.get(role).get(call-1));row.put("factoryCallerStack",callers.get(idle));
                row.put("factoryCallerFrameLimit",CALLER_FRAME_LIMIT);row.put("factoryCallerTextByteLimit",CALLER_TEXT_BYTE_LIMIT);
                row.put("factoryCallerTailMayBeOmitted",callers.get(idle).size()==CALLER_FRAME_LIMIT);
                row.put("association",role.contains("driver")?"actual installed shared-driver getter object":"source-ordered factory consumption; private agent field not read back");
                rows.add(Collections.unmodifiableMap(row));
            }
        }
        var out=new LinkedHashMap<String,Object>();out.put("schema","retention-idle-actual-v2");out.put("node",node);out.put("pid",ProcessHandle.current().pid());
        out.put("selection",selection.observation());out.put("instancesDistinct",true);out.put("instances",List.copyOf(rows));
        out.put("selectedLogicalRoles",List.copyOf(expectedCounts.keySet()));out.put("expectedConsumptionCounts",Collections.unmodifiableMap(expectedCounts));out.put("observedConsumptionCounts",Collections.unmodifiableMap(observedCounts));
        out.put("sleepDurationMeasured",false);out.put("hardRealtimeGuaranteed",false);out.put("runningAgentThreadCountIndependentlyObserved",false);
        out.put("associationScope","Direct shared-driver object and bounded factory creations associated with exact launched contexts. Intended uses follow pinned per-role constructor order, not a global call order or a count of active threads.");
        return Collections.unmodifiableMap(out);
    }
}

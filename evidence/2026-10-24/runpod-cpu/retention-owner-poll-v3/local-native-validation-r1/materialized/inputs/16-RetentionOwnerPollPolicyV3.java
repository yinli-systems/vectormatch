package io.vectormatch.cluster;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/** Load-owner polling only. Does not configure an Aeron driver, node or batch flush delay. */
final class RetentionOwnerPollPolicyV3 {
    static final String PROPERTY = "vectormatch.retention.ownerPollMaxParkNs";
    static final long LEGACY_MAXIMUM_PARK_NS = 1_000_000L;
    private static final List<String> HIDDEN_OPTIONS = List.of("JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS");

    static long requireMaximum(long value) {
        if (value != 100_000L && value != LEGACY_MAXIMUM_PARK_NS)
            throw new IllegalArgumentException("owner poll comparison requires100000 or1000000ns");
        return value;
    }

    record Selection(Long maximumParkNs) {
        Selection { if (maximumParkNs != null) requireMaximum(maximumParkNs); }
        boolean explicit() { return maximumParkNs != null; }
        long effectiveMaximumParkNs() { return explicit() ? maximumParkNs : LEGACY_MAXIMUM_PARK_NS; }
        Map<String,Object> observation() {
            return explicit() ? Map.of("schema", "retention-owner-poll-selection-v1", "property", PROPERTY,
                    "maximumParkNs", maximumParkNs, "factor", "owner poll requested park cap only",
                    "hardRealtimeGuaranteed", false) : Map.of("explicit", false);
        }
        Map<String,Object> actualObservation(RetentionBatchOwnerV3 owner) {
            if (owner == null) return Map.of("available", false, "reason", "owner_not_constructed");
            var actual = owner.snapshot();
            if (!Objects.equals(actual.get("ownerPollMaxParkNs"), effectiveMaximumParkNs()))
                throw new IllegalStateException("constructed owner polling cap differs from captured selection");
            return Map.of("available", true, "schema", "retention-owner-poll-actual-v1",
                    "source", "actual-constructed-owner-snapshot", "ownerPollMaxParkNs", actual.get("ownerPollMaxParkNs"),
                    "waitPolicy", actual.get("waitPolicy"), "requestedSleepOnly", actual.get("ownerPollRequestedSleepOnly"),
                    "osLatenessBounded", actual.get("ownerPollOsLatenessBounded"));
        }
    }

    static Selection selection(Map<String,String> properties, Map<String,String> environment) {
        for (String name : HIDDEN_OPTIONS)
            if (environment.getOrDefault(name, "").contains(PROPERTY))
                throw new IllegalArgumentException("owner poll selection must be explicit, not hidden in " + name);
        String requested = properties.get(PROPERTY);
        if (requested == null) return new Selection(null);
        if (!requested.equals("100000") && !requested.equals("1000000"))
            throw new IllegalArgumentException(PROPERTY + " must be exactly100000 or1000000");
        return new Selection(Long.valueOf(requested));
    }

    static Selection systemSelection() {
        var properties = new HashMap<String,String>();
        String value = System.getProperty(PROPERTY);
        if (value != null) properties.put(PROPERTY, value);
        return selection(properties, System.getenv());
    }

    private RetentionOwnerPollPolicyV3() {}
}

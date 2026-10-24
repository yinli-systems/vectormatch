package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine.Event;
import java.util.List;

/** Events begin at the requested inclusive sequence. Acknowledged events are no longer retained. */
public record EventBatch(long exportedSeq, long lastEventSeq, List<Event> events) {
    public EventBatch { events = List.copyOf(events); }
}

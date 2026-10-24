package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.MatchingEngine.*;
import org.junit.jupiter.api.Test;

import java.util.Arrays;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class CommandCodecTest {
    @Test void roundTripsEveryCommandAndOriginalResult() {
        MatchingEngine engine = new MatchingEngine();
        List<Command> commands = List.of(
                new Deposit(7, "producer", 1, Asset.QUOTE, 1_000),
                new Place(7, "producer", 2, "client-id", Side.BUY, 10, 20, TimeInForce.GTC),
                new Cancel(7, "producer", 3, 1));
        long correlation = 0;
        for (Command command : commands) {
            CommandCodec.Request decoded = CommandCodec.decodeRequest(CommandCodec.request(++correlation, command));
            assertEquals(command, decoded.command());
            assertEquals(correlation, decoded.correlationId());
            Execution execution = engine.apply(command);
            CommandCodec.Reply reply = new CommandCodec.Reply(correlation, execution.result(), execution.replayed(),
                    engine.lastCommandSeq(), engine.lastEventSeq(), engine.lastMarketSeq(), "", "");
            assertEquals(reply, CommandCodec.decodeReply(CommandCodec.reply(reply)));
        }
        assertTrue(CommandCodec.decodeRequest(CommandCodec.request(5, null)).query());
    }

    @Test void preservesInvalidBusinessFieldsForCoreValidation() {
        Command invalid = new Place(-1, null, -1, null, null, -2, 0, null);
        assertEquals(invalid, CommandCodec.decodeRequest(CommandCodec.request(1, invalid)).command());
    }

    @Test void rejectsTruncationTrailingDataAndUnknownVersion() {
        byte[] valid = CommandCodec.request(1, new Deposit(1, "a", 1, Asset.BASE, 5));
        for (int length = 0; length < valid.length; length++) {
            byte[] partial = Arrays.copyOf(valid, length);
            assertThrows(IllegalArgumentException.class, () -> CommandCodec.decodeRequest(partial));
        }
        assertThrows(IllegalArgumentException.class,
                () -> CommandCodec.decodeRequest(Arrays.copyOf(valid, valid.length + 1)));
        valid[5] = 99;
        assertThrows(IllegalArgumentException.class, () -> CommandCodec.decodeRequest(valid));
        assertThrows(IllegalArgumentException.class,
                () -> CommandCodec.decodeRequest(new byte[CommandCodec.MAX_COMMAND_BYTES + 1]));
    }

    @Test void eventFetchAcknowledgementAndChunkProtocolHaveBoundedRoundTrips() {
        MatchingEngine engine = new MatchingEngine();
        List<Event> events = engine.apply(new Deposit(1, "p", 1, Asset.QUOTE, 7)).events();
        CommandCodec.Request fetch = CommandCodec.decodeRequest(CommandCodec.fetch(12, 1, 16));
        assertEquals(1, fetch.sequence()); assertEquals(16, fetch.count());
        assertEquals(7, CommandCodec.decodeRequest(CommandCodec.ack(13, 7)).sequence());
        EventBatch batch = new EventBatch(0, 1, events);
        byte[] encoded = CommandCodec.events(12, batch, "");
        assertEquals(12, CommandCodec.correlation(encoded));
        assertEquals(batch, CommandCodec.decodeEvents(encoded).batch());
        byte[] payload = new byte[CommandCodec.MAX_SNAPSHOT_CHUNK];
        Arrays.fill(payload, (byte) 19);
        CommandCodec.SnapshotChunk snapshot = new CommandCodec.SnapshotChunk(14, "abc", 5000, 0, payload, "");
        byte[] wire = CommandCodec.snapshotChunk(snapshot);
        assertTrue(wire.length < CommandCodec.MAX_REPLY_BYTES);
        assertArrayEquals(payload, CommandCodec.decodeSnapshotChunk(wire).data());
        assertThrows(IllegalArgumentException.class, () -> CommandCodec.decodeReply(wire));
    }

    @Test void positionQueryHasNoBusinessPayloadAndKeepsFullStateQueryDistinct() {
        CommandCodec.Request position = CommandCodec.decodeRequest(CommandCodec.position(42));
        assertEquals(42, position.correlationId());
        assertEquals(CommandCodec.POSITION, position.operation());
        assertNull(position.command());
        assertFalse(position.query());
        assertTrue(CommandCodec.decodeRequest(CommandCodec.request(43, null)).query());
        byte[] valid = CommandCodec.position(42);
        assertEquals(15, valid.length);
        assertThrows(IllegalArgumentException.class,
                () -> CommandCodec.decodeRequest(Arrays.copyOf(valid, valid.length + 1)));
    }
}

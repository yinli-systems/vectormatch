package io.vectormatch.server;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.MatchingEngine.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import static org.junit.jupiter.api.Assertions.*;

class CommandJournalTest {
    @TempDir Path directory;
    @Test void forceAcknowledgedCommandsReplayExactly() throws Exception {
        Path path = directory.resolve("commands.vmj");
        MatchingEngine engine = new MatchingEngine();
        try (CommandJournal journal = new CommandJournal(path, new ObjectMapper())) {
            Command[] commands = {new Deposit(1, "test", 1, Asset.QUOTE, 100_000),
                    new Deposit(2, "test", 1, Asset.BASE, 100),
                    new Place(2, "test", 2, "sell", Side.SELL, 100, 20, TimeInForce.GTC),
                    new Place(1, "test", 2, "buy", Side.BUY, 110, 10, TimeInForce.IOC)};
            for (Command command : commands) { journal.append(command); engine.execute(command); }
        }
        try (CommandJournal journal = new CommandJournal(path, new ObjectMapper())) {
            MatchingEngine recovered = new MatchingEngine();
            assertEquals(4, journal.replay(recovered::execute, false));
            assertEquals(engine.stateHash(), recovered.stateHash());
        }
    }
    @Test void incompleteUnacknowledgedTailCanBeDiscarded() throws Exception {
        Path path = directory.resolve("tail.vmj");
        try (CommandJournal journal = new CommandJournal(path, new ObjectMapper())) {
            journal.append(new Deposit(1, "test", 1, Asset.BASE, 50));
        }
        long validSize = java.nio.file.Files.size(path);
        java.nio.file.Files.write(path, new byte[]{1, 2, 3}, StandardOpenOption.APPEND);
        try (CommandJournal journal = new CommandJournal(path, new ObjectMapper())) {
            assertEquals(1, journal.replay(command -> {}, true));
            assertEquals(3, journal.repairedTailBytes()); assertEquals(validSize, journal.size());
        }
    }
    @Test void corruptionFailsClosedInsteadOfSilentlyDroppingAcknowledgedData() throws Exception {
        Path path = directory.resolve("corrupt.vmj");
        try (CommandJournal journal = new CommandJournal(path, new ObjectMapper())) {
            journal.append(new Deposit(1, "test", 1, Asset.BASE, 50));
        }
        try (FileChannel channel = FileChannel.open(path, StandardOpenOption.WRITE)) {
            channel.write(ByteBuffer.wrap(new byte[]{0}), 20);
        }
        try (CommandJournal journal = new CommandJournal(path, new ObjectMapper())) {
            assertThrows(java.io.IOException.class, () -> journal.replay(command -> {}, true));
        }
    }
    @Test void corruptedFrameLengthCannotMasqueradeAsAnIncompleteTail() throws Exception {
        Path path = directory.resolve("length.vmj");
        try (CommandJournal journal = new CommandJournal(path, new ObjectMapper())) {
            journal.append(new Deposit(1, "test", 1, Asset.BASE, 50));
        }
        long originalSize = java.nio.file.Files.size(path);
        try (FileChannel channel = FileChannel.open(path, StandardOpenOption.WRITE)) {
            channel.write(ByteBuffer.allocate(4).putInt(16_384).flip(), 8);
        }
        try (CommandJournal journal = new CommandJournal(path, new ObjectMapper())) {
            assertThrows(java.io.IOException.class, () -> journal.replay(command -> {}, true));
            assertEquals(originalSize, journal.size());
        }
    }
}

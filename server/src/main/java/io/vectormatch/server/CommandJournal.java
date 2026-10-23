package io.vectormatch.server;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.MatchingEngine.Command;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.function.Consumer;
import java.util.zip.CRC32C;

/** Local write-ahead command log. A successful append has completed force(true). */
public final class CommandJournal implements AutoCloseable {
    private static final long MAGIC = 0x564D4A4E4C303032L;
    private static final int MAX_FRAME = 16_384;
    private static final long MAX_BYTES = 1_073_741_824L;
    private final FileChannel channel;
    private final FileLock lock;
    private final ObjectMapper mapper;
    private long repairedTailBytes;

    public CommandJournal(Path path, ObjectMapper mapper) throws IOException {
        this.mapper = mapper;
        Files.createDirectories(path.toAbsolutePath().getParent());
        channel = FileChannel.open(path, StandardOpenOption.CREATE, StandardOpenOption.READ, StandardOpenOption.WRITE);
        try {
            lock = channel.tryLock();
            if (lock == null) throw new IOException("journal already owned by another process");
            if (channel.size() == 0) {
                writeFully(ByteBuffer.allocate(8).putLong(MAGIC).flip());
                channel.force(true);
            }
            ByteBuffer header = ByteBuffer.allocate(8);
            if (!readFully(header, 0) || header.flip().getLong() != MAGIC)
                throw new IOException("invalid journal header");
        } catch (RuntimeException | IOException e) {
            channel.close();
            throw e;
        }
    }

    public long replay(Consumer<Command> consumer, boolean repairIncompleteTail) throws IOException {
        long position = 8, count = 0, size = channel.size();
        while (position < size) {
            ByteBuffer header = ByteBuffer.allocate(12);
            if (!readFully(header, position)) {
                repairTail(position, size, repairIncompleteTail);
                break;
            }
            header.flip();
            int length = header.getInt(), complement = header.getInt(), checksum = header.getInt();
            if (complement != ~length) throw new IOException("journal frame header mismatch at " + position);
            if (length <= 0 || length > MAX_FRAME) throw new IOException("invalid frame length at " + position);
            ByteBuffer payload = ByteBuffer.allocate(length);
            if (!readFully(payload, position + 12)) {
                repairTail(position, size, repairIncompleteTail);
                break;
            }
            byte[] bytes = payload.array();
            CRC32C crc = new CRC32C();
            crc.update(bytes);
            if ((int) crc.getValue() != checksum) throw new IOException("journal CRC mismatch at " + position);
            consumer.accept(decode(mapper.readTree(bytes)));
            position += 12L + length;
            count++;
        }
        channel.position(channel.size());
        return count;
    }

    private void repairTail(long position, long size, boolean allowed) throws IOException {
        if (!allowed) throw new IOException("incomplete trailing journal frame");
        repairedTailBytes += size - position;
        channel.truncate(position);
        channel.force(true);
    }

    public void append(Command command) throws IOException {
        ObjectNode node = mapper.valueToTree(command);
        node.put("type", command instanceof MatchingEngine.Deposit ? "DEPOSIT"
                : command instanceof MatchingEngine.Place ? "PLACE" : "CANCEL");
        byte[] bytes = mapper.writeValueAsBytes(node);
        if (bytes.length > MAX_FRAME) throw new IOException("command frame too large");
        if (channel.size() + bytes.length + 12 > MAX_BYTES) throw new IOException("journal capacity reached");
        CRC32C crc = new CRC32C(); crc.update(bytes);
        channel.position(channel.size());
        writeFully(ByteBuffer.allocate(12 + bytes.length).putInt(bytes.length).putInt(~bytes.length).putInt((int) crc.getValue()).put(bytes).flip());
        channel.force(true);
    }

    private Command decode(JsonNode value) throws IOException {
        if (value.path("type").isMissingNode()) throw new IOException("journal command has no type");
        ObjectNode body = ((ObjectNode) value).deepCopy();
        String type = body.remove("type").asText();
        return switch (type) {
            case "DEPOSIT" -> mapper.treeToValue(body, MatchingEngine.Deposit.class);
            case "PLACE" -> mapper.treeToValue(body, MatchingEngine.Place.class);
            case "CANCEL" -> mapper.treeToValue(body, MatchingEngine.Cancel.class);
            default -> throw new IOException("unknown command type: " + type);
        };
    }

    public long size() throws IOException { return channel.size(); }
    public long repairedTailBytes() { return repairedTailBytes; }
    private boolean readFully(ByteBuffer target, long position) throws IOException {
        while (target.hasRemaining()) {
            int n = channel.read(target, position);
            if (n < 0) return false;
            if (n == 0) throw new IOException("journal read made no progress");
            position += n;
        }
        return true;
    }
    private void writeFully(ByteBuffer source) throws IOException {
        while (source.hasRemaining()) channel.write(source);
    }
    @Override public void close() throws IOException { lock.release(); channel.close(); }
}


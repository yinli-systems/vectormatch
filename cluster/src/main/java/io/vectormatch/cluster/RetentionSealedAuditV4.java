package io.vectormatch.cluster;

import org.agrona.DirectBuffer;
import java.io.*;
import java.nio.channels.Channels;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;

/** Finite original-frame ledger. Close forces this ledger;it never certifies business durability. */
final class RetentionSealedAuditV4 implements RetentionSealedAeronEndpointV4.Audit,AutoCloseable {
    static final int MAGIC=0x56584134,VERSION=1,RECORD_HEADER_BYTES=21;
    static final long MAXIMUM_BYTES=128L*1024*1024;
    static final int METADATA=1,OUTGOING=2,INCOMING=3;
    private final Thread owner=Thread.currentThread();
    private final FileChannel channel;
    private final DataOutputStream out;
    private final long maximumBytes;
    private long bytes=8,records;
    private boolean closed,failed,forced;
    RetentionSealedAuditV4(Path path,long maximumBytes)throws IOException {
        if(maximumBytes<1024||maximumBytes>MAXIMUM_BYTES)throw new IllegalArgumentException("finite sealed audit budget1KiB..128MiB required");
        Path absolute=Objects.requireNonNull(path).toAbsolutePath().normalize();
        for(Path parent=absolute.getParent();parent!=null;parent=parent.getParent())if(Files.isSymbolicLink(parent))throw new IOException("symlink sealed audit parent refused");
        this.maximumBytes=maximumBytes;
        channel=FileChannel.open(absolute,StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE,LinkOption.NOFOLLOW_LINKS);
        out=new DataOutputStream(new BufferedOutputStream(Channels.newOutputStream(channel),65536));
        try{out.writeInt(MAGIC);out.writeInt(VERSION);}catch(IOException error){channel.close();throw error;}
    }
    @Override public void metadata(String kind,Map<String,Object> value){
        requireOpen();if(kind==null||!kind.matches("[A-Z_]{1,32}"))throw new IllegalArgumentException("bounded sealed metadata kind required");
        byte[] body=RetentionCapacityJsonV3.json(Map.of("kind",kind,"value",value)).getBytes(StandardCharsets.UTF_8);
        if(body.length>8192)throw new IllegalArgumentException("sealed metadata exceeds8KiB");record(METADATA,body);
    }
    @Override public void outgoing(int peerPort,long publicationId,DirectBuffer source,int offset,int length,long called,long returned,long result){
        requireOpen();frame(source,offset,length);if(peerPort<1024||peerPort>65535||publicationId<0||returned<called)throw new IllegalArgumentException("invalid actual sealed publication metadata");
        var bytes=new ByteArrayOutputStream(44+length);
        try{var body=new DataOutputStream(bytes);body.writeInt(peerPort);body.writeLong(publicationId);body.writeLong(called);body.writeLong(returned);body.writeLong(result);body.writeInt(length);byte[] copy=new byte[length];source.getBytes(offset,copy);body.write(copy);}catch(IOException impossible){throw new AssertionError(impossible);}
        record(OUTGOING,bytes.toByteArray());
    }
    @Override public void incoming(long imageId,byte[] source,long observedAt){
        requireOpen();if(imageId<0||source==null||source.length<1||source.length>RetentionSealedReadWireV4.MAX_FRAME_BYTES)throw new IllegalArgumentException("bounded actual sealed Image/frame required");
        var bytes=new ByteArrayOutputStream(20+source.length);
        try{var body=new DataOutputStream(bytes);body.writeLong(imageId);body.writeLong(observedAt);body.writeInt(source.length);body.write(source);}catch(IOException impossible){throw new AssertionError(impossible);}
        record(INCOMING,bytes.toByteArray());
    }
    private void record(int type,byte[] body){
        requireOpen();long size=RECORD_HEADER_BYTES+(long)body.length;
        if(size>maximumBytes-bytes){failed=true;throw new IllegalStateException("sealed original-frame audit budget exhausted");}
        try{out.writeByte(type);out.writeLong(records+1);out.writeLong(System.nanoTime());out.writeInt(body.length);out.write(body);bytes+=size;records++;}
        catch(IOException error){failed=true;throw new UncheckedIOException("sealed original-frame audit failed",error);}
    }
    Map<String,Object> observation(){requireOwner();return Map.of("bytes",bytes,"maximumBytes",maximumBytes,"records",records,"closed",closed,"failed",failed,"forcedOnClose",forced,"businessDurabilityCertificate",false);}
    @Override public void close()throws IOException {
        requireOwner();if(closed)return;closed=true;
        try{out.flush();channel.force(true);forced=true;}catch(IOException error){failed=true;throw error;}finally{channel.close();}
    }
    private static void frame(DirectBuffer bytes,int offset,int length){if(bytes==null||length<1||length>RetentionSealedReadWireV4.MAX_FRAME_BYTES||offset<0||offset>bytes.capacity()-length)throw new IllegalArgumentException("bounded sealed audit frame required");}
    private void requireOpen(){requireOwner();if(closed||failed)throw new IllegalStateException("sealed original-frame audit is closed or failed");}
    private void requireOwner(){if(Thread.currentThread()!=owner)throw new IllegalStateException("sealed audit requires its network owner");}
}

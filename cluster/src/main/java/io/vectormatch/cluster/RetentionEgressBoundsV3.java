package io.vectormatch.cluster;

import io.aeron.cluster.client.AeronCluster;
import io.aeron.logbuffer.FrameDescriptor;
import java.util.*;

/** Owner-thread observations of actual receiver Images; never substitutes channel defaults. */
public final class RetentionEgressBoundsV3 {
    public static final int MAX_IMAGES=16,MAX_LIFECYCLE_EVENTS=256,EXPECTED_MTU=1248;
    public record ImageMetadata(long correlationId,int sessionId,int streamId,int termLength,int mtuLength){
        public ImageMetadata{
            if(correlationId<0||termLength<65536||Integer.bitCount(termLength)!=1||mtuLength!=EXPECTED_MTU)
                throw new IllegalArgumentException("invalid actual bounded egress Image metadata");
        }
        public int maxMessageLength(){return FrameDescriptor.computeMaxMessageLength(termLength);}
    }
    private static final class Observed{
        final ImageMetadata image;long replies,largestApplicationReply;boolean active=true;
        Observed(ImageMetadata image){this.image=image;}
    }
    private final int requiredApplicationReplyBytes;
    private final Map<Long,Observed> observed=new TreeMap<>();
    private final List<Map<String,Object>> lifecycleEvents=new ArrayList<>();
    private long actualImageObservations,totalReplyHeaderAssociations;
    private int minimumMaxMessageLength=Integer.MAX_VALUE;
    public RetentionEgressBoundsV3(int requiredApplicationReplyBytes){
        if(requiredApplicationReplyBytes<1||requiredApplicationReplyBytes>RetentionReplyV3.MAX_REPLY_BYTES
                ||AeronCluster.SESSION_HEADER_LENGTH!=32)
            throw new IllegalArgumentException("bounded reply or pinned Aeron session header changed; rederive envelope");
        this.requiredApplicationReplyBytes=requiredApplicationReplyBytes;
    }
    /** Actual Images may arrive or retire after connect; each identity keeps immutable geometry. */
    public void observe(List<ImageMetadata> actual){
        if(actual==null||actual.isEmpty()||actual.size()>MAX_IMAGES)
            throw new IllegalStateException("actual egress Images missing or unbounded; no default term fallback");
        var unique=new TreeMap<Long,ImageMetadata>();
        for(ImageMetadata image:actual){
            if(unique.put(image.correlationId(),image)!=null)throw new IllegalStateException("duplicate actual Image correlation");
            if((long)requiredApplicationReplyBytes+AeronCluster.SESSION_HEADER_LENGTH>image.maxMessageLength())
                throw new IllegalStateException("complete archive reply plus session header exceeds actual egress maxMessageLength");
        }
        int additions=0,removals=0;
        for(var entry:unique.entrySet()){
            Observed prior=observed.get(entry.getKey());
            if(prior==null)additions++;
            else{
                if(!prior.image.equals(entry.getValue()))throw new IllegalStateException("actual egress Image term/MTU/session metadata drift");
                if(!prior.active)throw new IllegalStateException("retired actual egress Image identity returned");
            }
        }
        for(var entry:observed.entrySet())if(entry.getValue().active&&!unique.containsKey(entry.getKey()))removals++;
        if(observed.size()+additions>MAX_IMAGES||lifecycleEvents.size()+additions+removals>MAX_LIFECYCLE_EVENTS)
            throw new IllegalStateException("finite actual egress Image/lifecycle inventory exhausted");
        // Validate the entire observation before changing any admitted identity or active flag.
        long at=System.nanoTime();
        for(var entry:unique.entrySet())if(!observed.containsKey(entry.getKey())){
            observed.put(entry.getKey(),new Observed(entry.getValue()));event("ADDED",entry.getKey(),at);
        }
        for(var entry:observed.entrySet())if(entry.getValue().active&&!unique.containsKey(entry.getKey())){
            entry.getValue().active=false;event("REMOVED",entry.getKey(),at);
        }
        minimumMaxMessageLength=observed.values().stream().mapToInt(row->row.image.maxMessageLength()).min().orElseThrow();
        actualImageObservations++;
    }
    private void event(String kind,long correlation,long at){
        lifecycleEvents.add(Map.of("sequence",lifecycleEvents.size()+1,"event",kind,"imageCorrelationId",correlation,
                "observedAtMonotonicNs",at,"source","actual owner-thread egress subscription Image observation"));
    }
    /** The transport resamples its actual subscription before accepting an unfamiliar live Header Image. */
    public boolean isActive(long correlation){Observed entry=observed.get(correlation);return entry!=null&&entry.active;}
    /** Associate the actual reassembled application reply Header with its exact receiver Image. */
    public void reply(long imageCorrelation,int session,int stream,int term,int mtu,int applicationBytes){
        Observed entry=observed.get(imageCorrelation);
        if(entry==null||!entry.active)throw new IllegalStateException("reply Header Image was not admitted as active from actual egress subscription");
        ImageMetadata image=entry.image;
        if(image.sessionId()!=session||image.streamId()!=stream||image.termLength()!=term||image.mtuLength()!=mtu)
            throw new IllegalStateException("reply Header and actual egress Image metadata differ");
        if(applicationBytes<1||applicationBytes>RetentionReplyV3.MAX_REPLY_BYTES
                ||(long)applicationBytes+AeronCluster.SESSION_HEADER_LENGTH>image.maxMessageLength())
            throw new IllegalStateException("actual complete reply/session envelope exceeds admitted Image bounds");
        if(entry.replies==Long.MAX_VALUE||totalReplyHeaderAssociations==Long.MAX_VALUE)
            throw new IllegalStateException("finite reply association counter exhausted");
        entry.replies++;entry.largestApplicationReply=Math.max(entry.largestApplicationReply,applicationBytes);totalReplyHeaderAssociations++;
    }
    public Map<String,Object> snapshot(){
        if(observed.isEmpty())throw new IllegalStateException("no actual egress Image evidence");
        var images=new ArrayList<Map<String,Object>>();
        for(Observed entry:observed.values()){
            ImageMetadata image=entry.image;var row=new LinkedHashMap<String,Object>();
            row.put("imageCorrelationId",image.correlationId());row.put("publicationSessionId",image.sessionId());row.put("streamId",image.streamId());
            row.put("actualTermBufferLength",image.termLength());row.put("actualMtuLength",image.mtuLength());row.put("derivedMaxMessageLength",image.maxMessageLength());
            row.put("associatedApplicationReplies",entry.replies);row.put("largestObservedApplicationReplyBytes",entry.largestApplicationReply);row.put("activeAtLastObservation",entry.active);images.add(Collections.unmodifiableMap(row));
        }
        var result=new LinkedHashMap<String,Object>();result.put("source","actual AeronCluster.egressSubscription Images plus reassembled reply Header.context Image");
        result.put("requiredApplicationReplyBytes",requiredApplicationReplyBytes);result.put("aeronSessionHeaderBytes",AeronCluster.SESSION_HEADER_LENGTH);
        result.put("requiredCompleteMessageBytes",requiredApplicationReplyBytes+AeronCluster.SESSION_HEADER_LENGTH);result.put("minimumActualDerivedMaxMessageLength",minimumMaxMessageLength);
        result.put("actualImageObservations",actualImageObservations);result.put("replyHeaderImageAssociations",totalReplyHeaderAssociations);result.put("images",List.copyOf(images));
        result.put("activeImageCorrelations",observed.entrySet().stream().filter(entry->entry.getValue().active).map(Map.Entry::getKey).toList());
        result.put("lifecycleEvents",List.copyOf(lifecycleEvents));result.put("maximumEverObservedImages",MAX_IMAGES);result.put("maximumLifecycleEvents",MAX_LIFECYCLE_EVENTS);
        result.put("defaultMetadataSubstituted",false);result.put("sameOwnerThreadRequired",true);return Collections.unmodifiableMap(result);
    }
}

package io.vectormatch.cluster;

import java.util.Objects;
import static io.vectormatch.cluster.RetentionWireV3.*;

/** Offline physical-order reference with explicit historical read routing;not an independent matching algorithm. */
final class RetentionSealedReplayV4 {
    private final RetentionClusteredServiceV3 service;
    private final RetentionSealedReadBankV4 bank;
    private final RetentionSealedReadPolicyV4.Route route;
    private final long session;
    RetentionSealedReplayV4(RetentionServiceV3.Profile profile,String lineage,long session,RetentionSealedReadPolicyV4.Route route){
        if(session<0||!Objects.requireNonNull(route).enabled())throw new IllegalArgumentException("explicit replay session/route required");
        this.session=session;this.route=route;bank=new RetentionSealedReadBankV4(profile,lineage);service=new RetentionClusteredServiceV3(profile,lineage,true,bank);service.onStart(null,null);
    }
    byte[] dispatch(Request request){
        if(route==RetentionSealedReadPolicyV4.Route.DIRECT_UDP&&(request.operation()instanceof ArchiveChunk||request.operation()instanceof FetchEvents)){
            var grant=bank.grant().orElseThrow(()->new IllegalStateException("direct reference lacks a logged sealed descriptor"));
            try(var permit=bank.open(grant.id(),session)){return permit.answer(request);}
        }
        return service.dispatch(request,session);
    }
    RetentionClusteredServiceV3 service(){return service;}
}

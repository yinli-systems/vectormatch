from pathlib import Path
import json,csv,math,struct,hashlib,datetime
base=Path('cluster/build/retention-chunk-native-attempts/attempt-eab8c8a7-1980-4c12-a04d-80b82d219014');records=[];plans=[]
def reply_corr(raw):
 offset=6
 for i in range(2):n=struct.unpack_from('>i',raw,offset)[0];assert n>=0;offset+=4+n
 return struct.unpack_from('>q',raw,offset)[0]
for chunk in [3072,6144]:
 root=base/f'chunk-{chunk}';load=root/'load';d=json.loads((load/'load-result.json').read_text());plan=json.loads((load/'admission-plan.json').read_text());plans.append(plan)
 assert d['archiveChunkBytes']==chunk and d['batchCap']==4 and d['eventFetchCount']==16 and d['commonChunkEnvelope'] is True
 raw_count=0;largest=0;requests={int(row['correlation_id']) for row in csv.DictReader((load/'physical-request-index.csv').open())}
 with (load/'physical-replies.bin').open('rb') as f:
  while header:=f.read(12):
   assert len(header)==12;offset,n=struct.unpack('>qi',header);assert n>0 and n<=8192;raw=f.read(n);assert len(raw)==n and reply_corr(raw) in requests;raw_count+=1;largest=max(largest,n)
 b=d['physicalOfferTape']['lastActualTransportObservation']['actualEgressBounds'];images=b['images'];assert raw_count==d['physicalOfferTape']['recordedReplies']==b['replyHeaderImageAssociations']==sum(x['associatedApplicationReplies'] for x in images)
 assert b['requiredApplicationReplyBytes']==6919 and b['requiredCompleteMessageBytes']==6951 and b['defaultMetadataSubstituted'] is False and b['activeImageCorrelations']
 assert len(images)<=16 and len(b['lifecycleEvents'])<=256 and all(x['actualMtuLength']==1248 and x['derivedMaxMessageLength']==min(x['actualTermBufferLength']//8,16*1024*1024) and x['derivedMaxMessageLength']>=6951 for x in images)
 timings=list(csv.DictReader((load/'maintenance/logical-rpc-timings.csv').open()));chunks=[r for r in timings if r['kind']=='ArchiveChunk'];events=[r for r in timings if r['kind']=='FetchEvents']
 assert all(0<int(r['archive_chunk_requested_bytes'])<=chunk for r in chunks) and all(0<int(r['event_fetch_requested_count'])<=16 for r in events)
 payloads=sorted((load/'writer').glob('*archive*.bin'));assert len(payloads)==3;expected=sum(math.ceil(p.stat().st_size/chunk) for p in payloads);assert expected==len(chunks)
 assert len(timings)==d['maintenanceRpcMetrics']['logicalRpcCount']==len(chunks)+len(events)+9
 records.append({'archiveChunkBytes':chunk,'actualLogicalMaintenanceRpcs':len(timings),'actualArchiveChunkRpcs':len(chunks),'actualEventFetchRpcs':len(events),'archivePayloadBytes':sum(p.stat().st_size for p in payloads),'rawReplyFrames':raw_count,'largestObservedApplicationReplyBytes':largest,'actualImageHistory':images,'lifecycleEvents':b['lifecycleEvents'],'sourceEnforcedReplyHeaderAssociations':b['replyHeaderImageAssociations'],'allRecordedRepliesHaveAggregateAssociationCount':True,'rawPerReplyImageAssociationIndependentlyAvailable':False,'scope':'Per-reply Header/Image checking is enforced by pinned Java source; raw reply tape has no per-reply Image column, so this independent script verifies aggregate counters and geometry rather than reconstructing each association'})
a,b=[dict(p) for p in plans]
for key in ['archiveChunkBytes','selectedMaximumLogicalMaintenanceRpcs','selectedMaximumArchiveChunkRpcs']:a.pop(key);b.pop(key)
assert a==b
with Path('build/chunk-validation/native-r2/chunk-evidence-validation.json').open('x') as f:json.dump({'createdAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'commonRuntimeEnvelopeEqual':True,'arms':records},f,indent=2);f.write('\n')
print(json.dumps(records))

from pathlib import Path
import json,csv,hashlib
P=Path(__file__).resolve().parent
chain=json.loads((P/'CHAIN_THROUGH_100M.json').read_text());assert chain['acceptedTotal']==100000000 and chain['singleBusinessLineageIndexVerified']
assert json.loads((P/'FINAL_NATIVE_METADATA_VERIFIED.json').read_text())['allBytesMatchPrivateMemberManifests']
previous=0;business=0;anchor=0;count=0;rows=[];metrics=[];total_elapsed=0.;force=0;raw_bytes=0
for index in range(1,24):
 name='segment-'+str(index).zfill(4);d=P/'final-native-metadata'/name;s=json.loads((d/'summary.json').read_text());assert s['startAccepted']==previous and s['lineage']==chain['lineage']and s['replicated']is False
 with(d/'cuts.csv').open()as f:cuts=list(csv.DictReader(f))
 assert cuts
 for row in cuts:
  c={k:int(v)for k,v in row.items()};assert c['cut']==anchor+1 and 0<c['commands']<=1536 and c['business_seq']==business+c['commands'];assert c['business_seq']==c['accepted_total']+2 and c['event_seq']==2*c['accepted_total']+1
  assert c['service_p50_ns']<=c['service_p99_ns']<=c['service_p999_ns']<=c['service_max_ns']
  anchor=c['cut'];business=c['business_seq'];count+=c['commands'];rows.append(c)
 previous=s['acceptedTotal']
 assert int(cuts[-1]['accepted_total'])==previous and s['anchorNumber']==anchor and s['businessSeq']==business and s['eventSeq']==2*previous+1 and s['tradesTotal']==previous-1
 total_elapsed+=s['elapsedSeconds'];force+=s['fileForceNanos'];raw_bytes+=s['rawBytes']
 first,last=cuts[0],cuts[-1]
 metrics.append({'segment':name,'startAccepted':s['startAccepted'],'acceptedTotal':previous,'freshAccepted':s['freshAcceptedThisSegment'],'nativeElapsedSeconds':s['elapsedSeconds'],'packForceNs':s['fileForceNanos'],'cutCount':len(cuts),'rawPackBytes':s['rawBytes'],'interiorCutGcCountDelta':int(last['gc_count'])-int(first['gc_count']),'interiorCutGcMsDelta':int(last['gc_ms'])-int(first['gc_ms']),'interiorCutProcessCpuNsDelta':int(last['process_cpu_ns'])-int(first['process_cpu_ns'])})
assert count==business==100000002 and previous==100000000 and len(metrics)==23
result={'lineage':chain['lineage'],'acceptedOrders':previous,'settledTrades':previous-1,'fundingCommands':2,'businessCommands':business,'events':2*previous+1,'maintenanceCuts':anchor,'rawPacks':23,'coldContinuationBoundaries':22,'nativeSegmentElapsedSecondsSum':total_elapsed,'nativeSegmentElapsedScope':'sum of per-run execution/maintenance/evidence/hash elapsed; excludes prior-pack replay, external replay, archive upload, controller pauses and process startup; not sustained offered throughput','packForceNanosecondsSum':force,'packForceScope':'sum of observed raw-pack FileChannel.force calls; excludes separate final-snapshot force and does not prove physical media persistence','rawPackBytesSum':raw_bytes,'exactOrderServiceNs':chain['exactFreshOrderServiceNs'],'segments':metrics,'allOriginalCutAndSummaryBytesBoundToPrivateManifests':True,'replicated':False,'uninterruptedUptimeProven':False,'openLoopCapacityProven':False,'physicalDiskFaultRecoveryProven':False,'finalSnapshotSha256':chain['finalSnapshotSha256']}
output=P/'CONTINUITY_RESULTS_100M.json';assert not output.exists();output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if k!='segments'}))

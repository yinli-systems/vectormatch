#!/usr/bin/env python3
"""Independent local full-archive and row-ledger verification; no server/SQL actions."""
from pathlib import Path
import hashlib,json,struct,tarfile
P=Path(__file__).resolve().parents[3]/'evidence/2026-10-24/runpod-cpu/restoration-preparation/pg-readonly-r2'
d=json.loads((P/'closure.json').read_text());a=P/'raw-stopped-probe.tar.gz'
assert a.stat().st_size==d['archive']['bytes'] and hashlib.sha256(a.read_bytes()).hexdigest()==d['archive']['sha256']
files={};dirs={};selected={}
with tarfile.open(a,'r:gz') as tf:
    for t in tf:
        assert not t.name.startswith('/') and '..' not in Path(t.name).parts
        if t.isdir():
            assert t.name not in dirs;dirs[t.name]=(t.mode,t.uid,t.gid);continue
        assert t.isfile() and t.name not in files
        f=tf.extractfile(t);h=hashlib.sha256();body=[]
        keep=t.name in ['job/sql-inspection-r2/inspection.json','job/sql-inspection-r2/events.ndjson']
        for b in iter(lambda:f.read(1024*1024),b''):
            h.update(b)
            if keep:body.append(b)
        files[t.name]=(t.size,t.mode,h.hexdigest(),t.uid,t.gid)
        if keep:selected[t.name]=b''.join(body)
assert set(files)==set(d['files']) and set(dirs)==set(d['directories'])
for n,e in d['files'].items():assert files[n]==(e['bytes'],e['mode'],e['sha256'],e['uid'],e['gid']),n
for n,e in d['directories'].items():assert dirs[n]==(e['mode'],e['uid'],e['gid']),n
report=json.loads(selected['job/sql-inspection-r2/inspection.json']);raw=selected['job/sql-inspection-r2/events.ndjson']
assert report['passed'] and hashlib.sha256(raw).hexdigest()==report['eventsRawSha256']
h=hashlib.sha256();event=market=trades=0
for line in raw.splitlines():
    row=json.loads(line);event+=1;ev=row['eventSeq'];ms=row['marketSeq'];kind=row['eventType']
    assert ev==event
    original=row['originalJacksonReencoding'];payload=json.loads(original)
    assert json.loads(row['databaseJsonbText'])==payload
    assert payload['eventSeq']==ev and payload['marketSeq']==ms and payload['type']==kind
    digest=hashlib.sha256(original.encode()).hexdigest()
    assert digest==row['storedPayloadSha256']==row['reencodedPayloadSha256']
    if kind=='DEPOSIT':assert ms==0
    else:market+=1;assert ms==market
    if kind=='TRADE':trades+=1
    kb=kind.encode('ascii');h.update(struct.pack('>qqi',ev,ms,len(kb)));h.update(kb);h.update(bytes.fromhex(digest))
assert (event,market,trades)==(6214,6194,1551)
assert h.hexdigest()==report['framedLedgerSha256']
assert report['settings']['transaction_read_only']=='on' and report['settings']['default_transaction_read_only']=='on'
assert report['settings']['full_page_writes']=='on' and report['settings']['in_recovery'] is False
assert d['control']['fields']['Database cluster state']=='shut down'
assert d['control']['fields']['Database system identifier']=='7699920832388303129'
assert report['sourceClusterCanonicalCompared'] is False
for key,b in selected.items():(P/Path(key).name).write_bytes(b)
result={'passed':True,'files':len(files),'directories':len(dirs),'events':event,'marketEvents':market,'trades':trades,
    'fullArchiveStreamShaModesOwnersClosure':True,'everyEventCanonicalPayloadAndIndexAndSequenceVerified':True,
    'framedLedgerSha256':h.hexdigest(),'sourceClusterCanonicalCompared':False,'pgStoppedCleanly':True,
    'latestOriginalCheckpointEventSeq':6106,'eventsAfterLatestOriginalCheckpoint':event-6106,
    'scope':'PGinternalledgerconsistencyandownedcleanstoponly;6214PGtipisnot6106checkpoint;actualAeron-tailreplaystillpending'}
(P/'independent-readback.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

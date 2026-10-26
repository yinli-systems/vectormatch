"""Counts original recorded requests, not write/force calls or admission attempts."""
from pathlib import Path
import struct,collections,json

def analyze(load):
 load=Path(load);summary=json.loads((load/'load-result.json').read_text())
 operations=collections.Counter();batches=collections.Counter();seen=set();previous=-1
 with(load/'physical-requests.bin').open('rb')as f:
  while True:
   h=f.read(12)
   if not h:break
   assert len(h)==12;ns,n=struct.unpack('>qi',h);assert ns>=previous and 1<=n<=4096;previous=ns
   body=f.read(n);assert len(body)==n and struct.unpack_from('>IH',body)==(0x564d5733,3);offset=6
   for unused in range(2):
    assert offset+4<=len(body);size=struct.unpack_from('>i',body,offset)[0];offset+=4
    assert 0<=size<=64 and offset+size<=len(body);body[offset:offset+size].decode('utf-8','strict');offset+=size
   assert offset+9<=len(body);cid=struct.unpack_from('>q',body,offset)[0];offset+=8
   assert cid>0 and cid not in seen;seen.add(cid);op=body[offset];offset+=1;assert 1<=op<=8;operations[op]+=1
   if op==8:
    assert offset+4<=len(body);count=struct.unpack_from('>i',body,offset)[0];offset+=4;assert 1<=count<=4
    for unused in range(count):
     assert offset+4<=len(body);size=struct.unpack_from('>i',body,offset)[0];offset+=4
     assert 1<=size<=2048 and offset+size<=len(body);offset+=size
    assert offset==len(body);batches[count]+=1
 commands=sum(k*v for k,v in batches.items())
 assert commands==summary['confirmedAcceptedUniqueOrders']+summary['setupBusinessCommands']
 return dict(passed=True,operationUniqueRequestCounts=dict(operations),businessBatchSizeCounts=dict(batches),businessCommands=commands,scope='Whole source including three bootstrap commands; recorded original distinct requests, not force call counts.')

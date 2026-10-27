#!/usr/bin/env python3
"""Locate original worker stalls relative to retained-order growth, without rerunning load."""
import argparse,csv,hashlib,json,heapq
from pathlib import Path

def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def diagnose(root):
 root=Path(root);thresholds={int(.75*2**n)+1 for n in range(4,31)};retained=setup=received=missing=slow=0;growth=[];largest=[]
 with(root/'commands.csv').open()as commands,(root/'server-outcomes.csv').open()as results:
  server=csv.DictReader(results);actual=next(server,None)
  for cmd in csv.DictReader(commands):
   if cmd['phase']=='SETUP':
    assert cmd['kind']!='CANCEL';retained+=1;setup+=1;continue
   assert cmd['phase']=='MEASURED';i=int(cmd['index'])
   if actual is None or int(actual['index'])>i:missing+=1;continue
   assert int(actual['index'])==i
   duration=int(actual['worker_end_ns'])-int(actual['worker_start_ns']);assert duration>=0
   new=actual['accepted']=='true'and cmd['kind']!='CANCEL'
   if new:retained+=1
   row=dict(index=i,kind=cmd['kind'],serviceNs=duration,retainedOrdersAfter=retained,defaultHashMapGrowthBoundary=new and retained in thresholds)
   if row['defaultHashMapGrowthBoundary']:growth.append(row)
   if duration>1_000_000:slow+=1
   item=(duration,i,row)
   if len(largest)<20:heapq.heappush(largest,item)
   elif item[:2]>largest[0][:2]:heapq.heapreplace(largest,item)
   received+=1;actual=next(server,None)
  assert actual is None
 return dict(scope='Original accepted non-cancel count, default growth-boundary hypothesis; no profiler stack or changed business semantics inferred',setupOrders=setup,received=received,notExecutedOriginals=missing,retainedOrdersFinal=retained,workerCallsAbove1ms=slow,growthBoundaryCalls=growth,largestWorkerCalls=[x[2]for x in sorted(largest,reverse=True)],inputs={n:{'bytes':(root/n).stat().st_size,'sha256':sha(root/n)}for n in ['commands.csv','server-outcomes.csv']})
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();v=diagnose(a.root);a.output.write_text(json.dumps(v,indent=2)+'\n');print(json.dumps({'received':v['received'],'largestWorkerCall':v['largestWorkerCalls'][0]}))

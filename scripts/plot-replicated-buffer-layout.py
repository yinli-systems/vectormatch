#!/usr/bin/env python3
"""Show all four original placement arms, including negative comparisons."""
from pathlib import Path
import argparse,json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('summary',type=Path);p.add_argument('output',type=Path)
a=p.parse_args();s=json.loads(a.summary.read_text());r=s['results']
assert s['allOriginalArmsVerified'] and s['actualMappedDevicesVerified'] and s['durabilityLevelUnchanged']
a.output.mkdir(parents=True,exist_ok=True)
names=['layout-a1','layout-b1','layout-a2','layout-b2']
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
fig,axes=plt.subplots(2,2,figsize=(12,7.5),layout='constrained')
panels=[
 ('All-original scheduled-to-reply p99','ms',lambda x:x['fullLatency']['p99Us']/1000 if x['fullLatency']else None),
 ('All-original scheduled-to-reply p99.9','ms',lambda x:x['fullLatency']['p999Us']/1000 if x['fullLatency']else None),
 ('Leader file-force p99','ms',lambda x:x['telemetry'][0]['fileForce']['p99Us']/1000),
 ('Four JVMs combined mean CPU use','cores',lambda x:sum(t['meanCpuCores']for t in x['telemetry']))]
for ax,(title,unit,value)in zip(axes.flat,panels):
 vals=[value(r[n])for n in names];top=max(v for v in vals if v is not None)
 bars=ax.bar(range(4),[v if v is not None else 0 for v in vals],color=['#7e8b99','#2d7f9d']*2)
 for b,v in zip(bars,vals):ax.text(b.get_x()+b.get_width()/2,(v or 0)+.025*top,'undefined'if v is None else f'{v:.3f}',ha='center',fontsize=9)
 ax.set_xticks(range(4),['A1 overlay','B1 tmpfs','A2 overlay','B2 tmpfs']);ax.set_ylabel(unit);ax.set_title(title);ax.set_ylim(0,top*1.2);ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
fig.suptitle('VectorMatch | disposable buffer placement | each arm: 60 s at 100/s',fontsize=14)
fig.supxlabel('Three same-host UDP replicas + separate load JVM; G1, fixed CPU sets and leader. Archive/consensus remain on overlay, sync2.\nOnly media-driver communication buffers move. File-force percentiles are not per-request latency attribution.',fontsize=9)
for ext in ['png','svg']:fig.savefig(a.output/('replicated-buffer-layout.'+ext),dpi=160)

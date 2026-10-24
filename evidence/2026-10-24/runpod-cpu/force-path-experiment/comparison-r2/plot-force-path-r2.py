#!/usr/bin/env python3
"""Standalone scientific figure for the separate synthetic I/O diagnostic."""
from pathlib import Path
import hashlib
import json
import shutil
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

BASE=Path(__file__).resolve().parent;REPO=BASE.parents[2]
OUT=REPO/'evidence/2026-10-24/runpod-cpu/force-path-experiment/comparison-r2'
source=OUT/'comparison.json';data=json.loads(source.read_text());assert data['passed'] and len(data['rows'])==8
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
fig,axes=plt.subplots(1,2,figsize=(11.6,4.9),layout='constrained')
for axis,key,title in zip(axes,('write_elapsed_ns','force_elapsed_ns'),('Data write bracket','force(true) bracket')):
    for writers,color in ((1,'#2668a8'),(3,'#d25c27')):
        rows=[r for r in data['rows'] if r['writers']==writers];x=[r['blockBytes']/1024 for r in rows]
        for quantile,style,marker in (('p50Ns','--','o'),('p99Ns','-','s')):
            axis.plot(x,[r['pooledWithinPoint'][key][quantile]/1e6 for r in rows],style,marker=marker,color=color,
                      label=f'{writers} writer'+('s' if writers>1 else '')+' / '+('p50' if quantile=='p50Ns' else 'p99'))
    axis.set_title(title);axis.set_xlabel('Block size (KiB)');axis.set_ylabel('Elapsed per operation (ms)')
    axis.set_xticks((4,16,24,48));axis.set_ylim(bottom=0);axis.grid(alpha=.22);axis.legend(fontsize=8)
fig.suptitle('Synthetic file I/O on the existing CPU: one JVM, 1 or 3 writer threads',fontsize=13)
fig.supxlabel('200 measured operations per thread; 10 warmups excluded. Fixed order, short windows, shared overlay.\nNearest-rank row quantiles; no trading p99, pure-fsync isolation or durability/SLA claim.',fontsize=9)
for ext in ('png','svg'):fig.savefig(OUT/('force-path-r2.'+ext),dpi=170)
(OUT/'plot-inputs.json').write_text(json.dumps({'comparisonSha256':hashlib.sha256(source.read_bytes()).hexdigest(),
    'plotterSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'rows':8,'quantileMethod':data['quantileMethod']},indent=2)+'\n')
shutil.copy2(Path(__file__),OUT/Path(__file__).name)
print(OUT/'force-path-r2.png')

#!/usr/bin/env python3
"""Independently derive finite UDP outcomes; never substitute successful-only p99."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

HEADER = ['index','scheduled_offset_ns','send_call_offset_ns','send_return_offset_ns','reply_offset_ns','sent_bytes','status']

def audit(root):
    root=Path(root)
    config=json.loads((root/'configuration.json').read_text())
    source=json.loads((root/'summary.json').read_text())
    rate=config['rate'];seconds=config['seconds'];planned=config['planned']
    if config['schema']!='vm-udp-path-1' or planned!=rate*seconds or not 1<=planned<=500000:
        raise ValueError('bounded plan differs')
    if config['packetBytes']!=64 or config['arrivalClockPauses'] or config['retries']!=0 or config['financialCommands']!=0:
        raise ValueError('protocol semantics differ')
    global_ns=[];post_ns=[];in_window=0;not_sent=0;unknown=0;read=0;previous_call=-1
    with (root/'arrivals.csv').open(newline='')as f:
        rows=csv.DictReader(f)
        if rows.fieldnames!=HEADER:raise ValueError('CSV header differs')
        for i,row in enumerate(rows):
            if i>=planned:raise ValueError('extra arrival')
            if None in row or any(v is None for v in row.values()):raise ValueError('truncated or extra fields')
            values={k:int(row[k])for k in HEADER[:-1]}
            scheduled=1_000_000_000*i//rate
            call=values['send_call_offset_ns'];returned=values['send_return_offset_ns'];reply=values['reply_offset_ns'];sent=values['sent_bytes']
            if values['index']!=i or values['scheduled_offset_ns']!=scheduled:raise ValueError('original arrival identity differs')
            if sent not in [-1,0,64]:raise ValueError('invalid datagram result')
            if call<0:
                if call!=-1 or returned!=-1 or sent!=-1 or reply!=-1:raise ValueError('unattempted timing differs')
            elif call<scheduled or call<previous_call or returned<call:raise ValueError('send timeline differs')
            else:previous_call=call
            status='NOT_SENT' if sent!=64 else 'UNKNOWN' if reply<0 else 'REPLIED'
            if row['status']!=status:raise ValueError('outcome differs')
            if sent!=64:
                not_sent+=1
                if reply!=-1:raise ValueError('reply without an accepted send')
            elif reply<0:
                unknown+=1
                if reply!=-1:raise ValueError('invalid missing reply')
            else:
                if call<0 or reply<returned:raise ValueError('reply precedes original send')
                global_ns.append(reply-scheduled);post_ns.append(reply-returned)
                in_window+=reply<seconds*1_000_000_000
            read+=1
    if read!=planned:raise ValueError('missing arrival')
    p99=lambda a:sorted(a)[math.ceil(len(a)*.99)-1]if a else None
    result=dict(planned=planned,replied=len(global_ns),notSent=not_sent,unknown=unknown,acceptedInWindow=in_window,
        goodputPerSecond=in_window/seconds,allArrivalP99Ns=p99(global_ns)if len(global_ns)==planned else None,
        conditionalReplyP99Ns=p99(global_ns),conditionalPostSendP99Ns=p99(post_ns))
    for k,v in result.items():
        if source.get(k)!=v:raise ValueError('source summary differs: '+k)
    result.update(passed=True,allPlannedReplied=not_sent==unknown==0,
        originalCsvSha256=hashlib.sha256((root/'arrivals.csv').read_bytes()).hexdigest(),
        noTradingOrSustainedSlaClaim=True)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root');args=p.parse_args()
    print(json.dumps(audit(args.root),indent=2,sort_keys=True))

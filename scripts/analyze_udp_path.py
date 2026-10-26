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

def audit_server(client_root, server_root):
    """Pair original packet identities; server and client clocks are never subtracted."""
    from itertools import zip_longest
    client_root=Path(client_root);server_root=Path(server_root)
    client=audit(client_root)
    config=json.loads((client_root/'configuration.json').read_text())
    ready=json.loads((server_root/'ready.json').read_text());source=json.loads((server_root/'summary.json').read_text())
    planned=client['planned']
    if ready.get('ledgerVersion')!=2 or source.get('ledgerVersion')!=2 or ready.get('planned')!=planned or source.get('planned')!=planned:
        raise ValueError('exact server ledger plan required')
    if ready['runHex']!=config['runHex'] or ready['maxParkNs']!=config['maxParkNs']:
        raise ValueError('server/client experiment selection differs')
    ingress=egress=echo_not_sent=attempts_total=echoes_total=duplicates=observed=0
    header=['index','first_receive_offset_ns','first_echo_call_offset_ns','echo_attempts','echoes_sent']
    with (client_root/'arrivals.csv').open(newline='')as cf,(server_root/'receipts.csv').open(newline='')as sf:
        clients=csv.DictReader(cf);servers=csv.DictReader(sf)
        if servers.fieldnames!=header:raise ValueError('server ledger header differs')
        for i,(c,s)in enumerate(zip_longest(clients,servers)):
            if c is None or s is None or i>=planned or None in s or any(v is None for v in s.values()):
                raise ValueError('server ledger incomplete or unbounded')
            if int(s['index'])!=i or int(c['index'])!=i:raise ValueError('server/client identity differs')
            received=int(s['first_receive_offset_ns']);called=int(s['first_echo_call_offset_ns']);attempts=int(s['echo_attempts']);echoes=int(s['echoes_sent'])
            if not 0<=echoes<=attempts:raise ValueError('invalid echo counts')
            if attempts==0:
                if received!=-1 or called!=-1:raise ValueError('unobserved server timeline differs')
            elif received<0 or called<received:raise ValueError('server echo precedes original receipt')
            sent=int(c['sent_bytes'])==64;replied=c['status']=='REPLIED'
            if not sent and attempts:raise ValueError('server received an unsent original')
            if replied and echoes==0:raise ValueError('client reply lacks server echo')
            if sent and attempts==0:ingress+=1
            elif sent and not replied:
                if echoes==0:echo_not_sent+=1
                else:egress+=1
            observed+=attempts>0;attempts_total+=attempts;echoes_total+=echoes;duplicates+=max(0,attempts-1)
    expected=dict(received=attempts_total,replied=echoes_total,duplicates=duplicates,sendBackpressure=attempts_total-echoes_total)
    if any(source.get(k)!=v for k,v in expected.items()):raise ValueError('server aggregate differs from original receipts')
    if ingress+egress+echo_not_sent!=client['unknown']:raise ValueError('unknown partition differs')
    return dict(passed=True,planned=planned,uniqueServerReceipts=observed,ingressUnobserved=ingress,
        serverEchoNotSent=echo_not_sent,egressUnobserved=egress,serverDuplicateReceipts=duplicates,
        serverReceiptCsvSha256=hashlib.sha256((server_root/'receipts.csv').read_bytes()).hexdigest(),
        clocksCombined=False,physicalLossLocationProven=False)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root');p.add_argument('--server');args=p.parse_args()
    result=audit(args.root)
    if args.server:result['serverAttribution']=audit_server(args.root,args.server)
    print(json.dumps(result,indent=2,sort_keys=True))

#!/usr/bin/env python3
"""Independent bounded original-byte route audit;not a matching-engine or latency verifier."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import struct
import re
import xml.etree.ElementTree as ET

MAX_FRAME=16384
MAX_LEDGER=128*1024*1024

def require(condition, message):
    if not condition:
        raise ValueError(message)

class Bytes:
    def __init__(self, data):self.data=data;self.offset=0
    def take(self, count):
        require(0<=count<=len(self.data)-self.offset,"truncated bounded record")
        result=self.data[self.offset:self.offset+count];self.offset+=count;return result
    def number(self, fmt):return struct.unpack(">"+fmt,self.take(struct.calcsize(">"+fmt)))[0]
    def text(self, maximum=128, short=False):
        count=self.number("H" if short else "i");require(0<=count<=maximum,"string bound")
        return self.take(count).decode("utf-8",errors="strict")
    def block(self, maximum):
        count=self.number("i");require(0<count<=maximum,"embedded frame bound");return self.take(count)
    def end(self):require(self.offset==len(self.data),"trailing record bytes")

def legacy(data, reply=False):
    b=Bytes(data);require(b.number("I")== (0x564d5233 if reply else 0x564d5733),"legacy magic")
    require(b.number("H")==3,"legacy version");scope=(b.text(64),b.text(64));correlation=b.number("q")
    require(correlation>0,"legacy correlation")
    counters=None
    if reply:
        counters=tuple(b.number("q")for _ in range(7))+(b.text(64),);require(b.text(128)=="","reply error")
    tag=b.number("B")
    return dict(scope=scope,correlation=correlation,tag=tag,counters=counters,bytes=data)

def frame(data):
    require(60<=len(data)<=MAX_FRAME,"sealed frame bound")
    require(hashlib.sha256(data[:-32]).digest()==data[-32:],"sealed checksum")
    b=Bytes(data[:-32]);require(b.number("I")==0x56585234 and b.number("H")==1,"sealed magic/version")
    tag=b.number("B");node=b.number("B");session=b.number("q");correlation=b.number("q");length=b.number("i")
    require(1<=tag<=5 and 0<=node<=2 and session>=0 and correlation>0,"sealed identity")
    require(length==len(data)-60,"sealed body length");r=dict(tag=tag,node=node,session=session,correlation=correlation,bytes=data)
    if tag in (1,3):r["port"]=b.number("i");require(1024<=r["port"]<=65535,"reply port")
    if tag in (2,3,4):
        r["grant"]=b.text(64,short=True);require(len(r["grant"])==64 and all(c in "0123456789abcdef"for c in r["grant"]),"grant hash")
    if tag==2:r["eventCount"]=b.number("i");require(0<=r["eventCount"]<=16384,"grant events")
    if tag in (1,2,3,4):
        r["inner"]=legacy(b.block(16384),reply=tag!=3);require(r["inner"]["correlation"]==correlation,"inner correlation")
        require(r["inner"]["tag"]in ((5,7)if tag==3 else (2,4)if tag==4 else (3,)),"sealed inner operation")
    else:r["code"]=b.number("B");require(r["code"]<8,"failure code")
    b.end();return r

def ledger(path):
    require(path.is_file()and not path.is_symlink()and path.stat().st_size<=MAX_LEDGER,"ledger path/size")
    rows=[]
    with path.open("rb")as stream:
        require(stream.read(8)==struct.pack(">II",0x56584134,1),"ledger header")
        while header:=stream.read(21):
            require(len(header)==21,"truncated ledger header");kind,sequence,at,count=struct.unpack(">Bqqi",header)
            require(kind in (1,2,3)and sequence==len(rows)+1 and 0<count<=MAX_FRAME+64,"ledger sequence/size")
            body=stream.read(count);require(len(body)==count,"truncated ledger body");b=Bytes(body)
            if kind==1:
                require(count<=8192,"metadata bound");row=json.loads(body);require(set(row)=={"kind","value"},"metadata schema")
            elif kind==2:
                row=dict(port=b.number("i"),publication=b.number("q"),called=b.number("q"),returned=b.number("q"),code=b.number("q"));row["frame"]=frame(b.block(MAX_FRAME));b.end()
                require(row["returned"]>=row["called"]and 1024<=row["port"]<=65535,"actual offer metadata")
            else:
                row=dict(image=b.number("q"),observed=b.number("q"));row["frame"]=frame(b.block(MAX_FRAME));b.end()
            rows.append(dict(type=kind,sequence=sequence,at=at,value=row))
    return rows

def check_endpoint(rows, request_side):
    publications={};images={};tx=[];rx=[];routed=[]
    for row in rows:
        value=row["value"]
        if row["type"]==1:
            kind=value["kind"];m=value["value"]
            if kind=="PUBLICATION":
                require(m["streamId"]==(47201 if request_side else 47202)and m["termBytes"]==1048576 and m["maxPayloadBytes"]==1216 and m["maxMessageBytes"]==131072 and m["clusterLogPosition"]is False,"actual publication envelope")
                require(m["registrationId"]not in publications,"duplicate publication metadata");publications[m["registrationId"]]=m
            elif kind=="IMAGE":
                require(m["streamId"]==(47202 if request_side else 47201)and m["termBytes"]==1048576 and m["mtuBytes"]==1248 and m["clusterSessionHeaderBytes"]==0 and m["sourceIdentity"].startswith("127.0.0.1:"),"actual Image envelope")
                require(m["imageId"]not in images,"duplicate Image metadata");images[m["imageId"]]=m
            elif kind=="ROUTED_OFFER":routed.append(m)
        elif row["type"]==2:
            require(value["publication"]in publications and publications[value["publication"]]["peerPort"]==value["port"],"offer lacks actual publication metadata")
            if value["code"]>0:tx.append(value)
        else:
            require(value["image"]in images,"receive lacks actual Image metadata");rx.append(value)
    require(len(publications)<=16 and len(images)<=16,"endpoint identity inventory bound")
    return dict(tx=tx,rx=rx,routed=routed,publications=publications,images=images)

def originals(root):
    """Read original physical attempts,not a success-only subset."""
    if(root/"load/physical-requests.bin").is_file():
        with(root/"load/physical-requests.bin").open("rb")as wires,(root/"load/physical-offer-codes.csv").open()as stream:
            for row in csv.DictReader(stream):
                wires.seek(int(row["wire_offset"]));header=wires.read(12);require(len(header)==12,"original request offset")
                _,length=struct.unpack(">qi",header);require(0<length<=4096,"original wire bound");data=wires.read(length);require(len(data)==length,"original wire truncated")
                yield legacy(data),int(row["return_code"])
    else:
        with(root/"wire-attempts.bin").open("rb")as wires,(root/"offer-codes.csv").open()as stream:
            for index,row in enumerate(csv.DictReader(stream),1):
                require(int(row["attempt"])==index,"original offer sequence");header=wires.read(4);require(len(header)==4,"original request count")
                length=struct.unpack(">i",header)[0];require(0<length<=4096,"original wire bound");data=wires.read(length);require(len(data)==length,"original wire truncated");yield legacy(data),int(row["original_code"])
            require(not wires.read(1),"unindexed original attempt")

def original_replies(root):
    capacity=(root/"load/physical-replies.bin").is_file()
    path=root/("load/physical-replies.bin"if capacity else"wire-replies.bin")
    with path.open("rb")as stream:
        while header:=stream.read(12 if capacity else 4):
            require(len(header)==(12 if capacity else 4),"truncated original reply header")
            length=struct.unpack(">i",header[-4:])[0];require(0<length<=16384,"original reply bound")
            data=stream.read(length);require(len(data)==length,"truncated original reply");yield legacy(data,True)

def check_routed_offer(original,code,record,route):
    is_read=original["tag"]in (5,7)
    expected="DIRECT_UDP"if is_read and route=="DIRECT_UDP"else"AERON_CLUSTER"
    require(record==dict(correlationId=original["correlation"],requestSha256=hashlib.sha256(original["bytes"]).hexdigest(),route=expected,actualReturnCode=code,clusterLogPosition=False,publicationPositionKind="CLUSTER_INGRESS"if expected=="AERON_CLUSTER"else"ORDINARY_UDP"),"route/actual offer/original SHA mismatch")
    return expected

def verify(root,route):
    root=Path(root);require(route in ("CLUSTER","DIRECT_UDP"),"explicit read route required")
    client=check_endpoint(ledger(root/"sealed-client-ledger.bin"),True)
    servers=[check_endpoint(ledger(p),False)for p in sorted(root.glob("node-*/sealed-read-*.bin"))];require(len(servers)==6,"three nodes/two generations required")
    session=int((root/"sealed-client-session.txt").read_text());require(session>=0,"actual cluster session")
    sent=lambda items:Counter(v["frame"]["bytes"]for v in items)
    require(sent(client["tx"])==sent([v for s in servers for v in s["rx"]]),"client positive frames differ from actual server receives")
    require(sent(client["rx"])==sent([v for s in servers for v in s["tx"]]),"server positive frames differ from actual client receives")
    for value in client["tx"]+client["rx"]:require(value["frame"]["session"]==session and value["frame"]["node"]==0,"wire not bound to actual fixed owner/leader")
    physical=list(originals(root));require(len(physical)==len(client["routed"]),"route ledger missing original attempts")
    direct=[];read_count=0
    for(original,code),record in zip(physical,client["routed"]):
        is_read=original["tag"]in (5,7);expected=check_routed_offer(original,code,record,route)
        if is_read:read_count+=1
        if expected=="DIRECT_UDP"and code>0:direct.append((original["bytes"],code))
    network=[(v["frame"]["inner"]["bytes"],v["code"])for v in client["tx"]if v["frame"]["tag"]==3]
    require(direct==network,"direct original admissions/positions differ from actual ordinary publication")
    hellos=[v["frame"]for v in client["tx"]if v["frame"]["tag"]==1];welcomes=[v["frame"]for v in client["rx"]if v["frame"]["tag"]==2]
    require(hellos and len(hellos)==len(welcomes),"sealed handshake incomplete")
    for h,w in zip(hellos,welcomes):require(h["correlation"]==w["correlation"]and h["inner"]["bytes"]==w["inner"]["bytes"],"welcome differs from logged descriptor hello")
    replies=list(original_replies(root));descriptors=Counter(r["bytes"]for r in replies if r["tag"]==3)
    require(Counter(h["inner"]["bytes"]for h in hellos)==descriptors,"hello does not bind every original logged descriptor reply")
    grants={w["grant"]:w["inner"]for w in welcomes};data=[v["frame"]for v in client["rx"]if v["frame"]["tag"]==4]
    for d in data:
        require(d["grant"]in grants and d["inner"]["scope"]==grants[d["grant"]]["scope"]and d["inner"]["counters"]==grants[d["grant"]]["counters"],"data not bound to historical descriptor counters/scope")
    require(not data if route=="CLUSTER"else Counter(d["inner"]["bytes"]for d in data)==Counter(r["bytes"]for r in replies if r["tag"]in (2,4)),"direct DATA differs from original observed callback replies")
    return dict(passed=True,schema="sealed-route-original-byte-audit-1",route=route,originalAttempts=len(physical),readAttempts=read_count,positiveOrdinaryReadAdmissions=len(direct),handshakes=len(hellos),serverLedgers=len(servers),actualSession=session,everyOriginalOfferRouteAndCodeMatched=True,actualImagePublicationEnvelopeMatched=True,allOrdinaryPositiveFramesMatchedEndToEnd=True,allDirectDataMatchedOriginalCallbacks=True,everyGrantBoundToOriginalLoggedDescriptor=True,matchingAlgorithmOrLatencyVerified=False)

def verify_junit(path):
    path=Path(path);require(path.is_file()and not path.is_symlink()and path.stat().st_size<=8*1024*1024,"bounded original JUnit required")
    suite=ET.parse(path).getroot();require(int(suite.get("tests",0))==2 and all(int(suite.get(k,0))==0 for k in ("failures","errors","skipped")),"both actual route tests must pass without skips")
    roots=[Path(p.strip())for p in re.findall(r"VECTOR_SEALED_THREE_JVM_TEST_EVIDENCE ([^\n]+)","".join(suite.itertext()))];require(len(roots)==2 and len(set(roots))==2,"two distinct original route roots")
    expected=path.resolve().parents[2]/"sealed-read-native-attempts";results={}
    for root in roots:
        require(root.is_absolute()and root.parent==expected and root.is_dir(),"route root must be this JUnit build's owned attempt")
        for parent in [root,*root.parents]:require(not parent.is_symlink(),"route root symlink")
        mode=json.loads((root/"sealed-read-selection.json").read_text())["readRoute"];require(mode not in results,"duplicate route instead of both controls")
        results[mode]=verify(root,mode)
    require(set(results)=={"CLUSTER","DIRECT_UDP"},"both actual routes required")
    return dict(passed=True,bothActualThreeJvmRoutesVerified=True,results=results)

def verify_capacity_junit(path):
    path=Path(path);require(path.is_file()and not path.is_symlink()and path.stat().st_size<=8*1024*1024,"bounded original capacity JUnit required")
    suite=ET.parse(path).getroot();require(int(suite.get("tests",0))==1 and all(int(suite.get(k,0))==0 for k in ("failures","errors","skipped")),"actual capacity correctness test must pass without skips")
    roots=[Path(p.strip())for p in re.findall(r"VECTOR_SEALED_CAPACITY_TEST_EVIDENCE ([^\n]+)","".join(suite.itertext()))];require(len(roots)==1,"one original capacity correctness attempt required")
    root=roots[0];require(root.is_absolute()and root.parent==path.resolve().parents[2]/"sealed-capacity-native-attempts"and root.is_dir(),"capacity root must be this JUnit build's owned attempt")
    for parent in [root,*root.parents]:require(not parent.is_symlink(),"capacity root symlink")
    require(json.loads((root/"completion.json").read_text())["passed"]is True,"full capacity protocol did not complete")
    registration=json.loads((root/"registration.json").read_text());require(registration["ratePerSecond"]==500 and registration["sealedReads"]["readRoute"]=="DIRECT_UDP","exact direct500 correctness fixture required")
    return dict(passed=True,actualCapacityProtocolComplete=True,originalByteRouteAudit=verify(root,"DIRECT_UDP"),performanceClaim=False)

if __name__=="__main__":
    parser=argparse.ArgumentParser();source=parser.add_mutually_exclusive_group(required=True);source.add_argument("--root");source.add_argument("--junit");parser.add_argument("--route",choices=("CLUSTER","DIRECT_UDP"));parser.add_argument("--capacity-junit");args=parser.parse_args()
    if args.root:require(args.route is not None and args.capacity_junit is None,"explicit route required for original root;capacity JUnit accompanies JUnit mode")
    else:require(args.route is None,"JUnit determines both original routes")
    result=verify_junit(args.junit)if args.junit else verify(args.root,args.route)
    if args.capacity_junit:result["capacityProtocol"]=verify_capacity_junit(args.capacity_junit)
    print(json.dumps(result,sort_keys=True))

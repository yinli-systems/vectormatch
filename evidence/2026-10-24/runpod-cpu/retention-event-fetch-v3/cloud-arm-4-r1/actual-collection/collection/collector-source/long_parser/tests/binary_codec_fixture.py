"""Synthetic protocol bytes, not Java-captured wires or benchmark/log evidence."""
import struct
MAX=2**63-1

def text(value):
    raw=value.encode('utf8');return struct.pack('>i',len(raw))+raw

def request(count=32,first=1,correlation=MAX):
    return struct.pack('>iH',0x564d5733,3)+text('a'*64)+text('l'*64)+struct.pack('>qBqi',correlation,5,first,count)

def event(seq,detail):
    return struct.pack('>qqBqqqqBqq',seq,seq,2,MAX,MAX,MAX,MAX,0,MAX,MAX)+text(detail)

def reply(count=32,first=1,detail='界'*42+'é',error='E'*128):
    header=struct.pack('>iH',0x564d5233,3)+text('a'*64)+text('l'*64)+struct.pack('>q',MAX)
    header+=struct.pack('>7q',MAX,MAX,32,32,0,MAX,0)+text('b'*64)+text(error)+struct.pack('>Bqqi',2,0,max(32,first+count-1),count)
    return header+b''.join(event(seq,detail)for seq in range(first,first+count))

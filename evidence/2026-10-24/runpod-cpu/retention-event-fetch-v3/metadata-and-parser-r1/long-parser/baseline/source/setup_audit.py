"""Independent byte decode of exactly three setup commands, not a Java invocation."""
from workload_contract import LONG,require,validate_setup_commands
import re


def validate_setup_hashes(business_reply_hashes,position):
    require(business_reply_hashes==['','',''],'Business reply counters(false) must carry an empty stateHash')
    require((position['businessSeq'],position['eventSeq'],position['marketSeq'],position['exportedEventSeq'],position['leaderMemberId'])==(3,3,1,0,0)
        and isinstance(position['combinedSha256'],str) and re.fullmatch('[0-9a-f]{64}',position['combinedSha256'])is not None,
        'Setup Position exact frontier/leader or canonical SHA format differs')
    return {'businessReplyHashIntentionallyEmpty':True,'positionHashFormatAndFrontiersVerified':True,
        'positionHashIndependentlyRederivedFromRawPositionWire':False,
        'scope':'Source counters(false) omits Business hash; native verifyPosition compares query to same-candidate reference but only Position JSON is retained. No raw query/reply hash derivation is claimed here.'}


def decode_setup(value,audit):
    r=audit.Reader(value)
    require(len(value)<=4096 and (r.i(),r.number('H'))==(0x564d5733,3),'Setup V3 envelope differs')
    scope={'profile':r.text(64),'lineage':r.text(64),'correlation':r.q()}
    require(r.b()==1,'Setup must be single canonical Business command')
    nested=audit.Reader(r.take(r.i()));r.end()
    require((nested.i(),nested.number('H'),nested.q())==(0x564d5731,2,0),'Setup nested command envelope differs')
    command={'type':nested.b(),'account':nested.q(),'producer':nested.text(512),'seq':nested.q()}
    if command['type']==1:command.update(asset=nested.b(),amount=nested.q())
    else:
        require(command['type']==2,'Unexpected setup command kind')
        command.update(client=nested.text(512),side=nested.b(),price=nested.q(),quantity=nested.q(),tif=nested.b())
    nested.end();return {'scope':scope,'command':command}


def audit_setup(arm,cfg,audit):
    requests=audit.frames(arm/'setup-requests.bin',False,lambda value:decode_setup(value,audit))
    replies=audit.frames(arm/'setup-replies.bin',False,audit.reply)
    require(len(requests)==len(replies)==3,'Exactly three setup commands/replies required')
    validate_setup_commands([r['decoded']['command'] for r in requests])
    correlations=set()
    for number,(request,reply)in enumerate(zip(requests,replies),1):
        scope=request['decoded']['scope'];answer=reply['decoded']
        require(scope['profile']==answer['profile']==cfg['profileSha256'] and scope['lineage']==answer['lineage']==cfg['lineage']
            and scope['correlation']==answer['correlation'] and scope['correlation']>0 and scope['correlation']not in correlations,'Setup scope/correlation differs')
        correlations.add(scope['correlation'])
        require(answer['tag']==1 and answer['error']=='' and answer['result']is not None and answer['result']['code']==0
            and answer['result']['commandSeq']==number and not answer['replayed'] and 'maintenance'not in answer,'Setup was rejected/replayed/maintenance')
        require((answer['result']['orderId'],answer['result']['remaining'],answer['result']['trades'])
            ==((1,LONG.arrivals,0)if number==3 else(0,0,0)),'Setup result does not match exact maker/deposit')
        require(answer['counters']==[number,number,number,1 if number==3 else 0,0,1 if number==3 else 0,0],'Setup counter prefix differs')
    position=audit.js(arm/'setup-position.json')
    hash_scope=validate_setup_hashes([r['decoded']['stateHash']for r in replies],position)
    return {'passed':True,'businessCommands':3,'fundingBase':LONG.arrivals,'fundingQuote':LONG.arrivals*10,
        'makerQuantity':LONG.arrivals,'makerOrderId':1,'setupLastCommandSeq':3,'setupEventSeq':3,'setupIsIncludedInFirstCommandCut':True,'hashValidation':hash_scope,
        'scope':'Decoded original setup wires and their exact successful replies/position; no external algorithm or business execution'}

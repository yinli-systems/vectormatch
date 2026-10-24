"""Postprocess only the SHA-bound four-arm comparison; no original input mutation."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def run(comparison_path,config_path):
    comparison=json.loads(comparison_path.read_text());config=json.loads(config_path.read_text())
    assert comparison['passed'] is True and comparison['formalFourArmComparisonComplete'] is True
    assert sha(config_path)==comparison['inputs'][str(config_path.resolve())]['sha256']
    reports=[];inputs={str(comparison_path):sha(comparison_path),str(config_path):sha(config_path)}
    for spec,arm in zip(config['arms'],comparison['arms']):
        assert spec['arm']==arm['arm']
        path=(config_path.parent/spec['collection']/'collection/raw-files/job/idle-arm/load/arrivals.csv').resolve()
        before=sha(path);assert before==comparison['inputs'][str(path)]['sha256']
        with path.open(newline='')as f:rows=list(csv.DictReader(f))
        assert len(rows)==6400
        selected=sorted(rows,key=lambda r:(-(int(r['reply_completion_offset_ns'])-int(r['scheduled_offset_ns'])),int(r['arrival_index'])))[:math.ceil(len(rows)*.01)]
        details=[]
        for row in selected:
            scheduled=int(row['scheduled_offset_ns']);dispatch=int(row['dispatch_offset_ns'])
            offered=int(row['first_successful_offer_return_offset_ns']);end=int(row['reply_completion_offset_ns'])
            assert scheduled<=dispatch<=offered<=end
            total=end-scheduled;absolute=scheduled+arm['config']['scheduledOriginMonotonicNs']
            details.append({'arrivalIndex':int(row['arrival_index']),'totalNs':total,'scheduledToDispatchNs':dispatch-scheduled,
                'dispatchToSuccessfulOfferReturnNs':offered-dispatch,'successfulOfferReturnToReplyNs':end-offered,
                'scheduledToDispatchFraction':(dispatch-scheduled)/total,
                'scheduledDuringMaintenanceCycle':any(c['startMonotonicNs']<=absolute<c['endMonotonicNs'] for c in arm['cycles'])})
        total=sum(v['totalNs']for v in details)
        reports.append({'arm':arm['arm'],'maximumParkNs':arm['maximumParkNs'],'cohort':'Exactly slowest64of6400 by complete scheduled-to-reply latency; ties ordered by arrivalIndex',
            'tailCount':len(details),'scheduledToDispatchShareOfTailLatencySum':sum(v['scheduledToDispatchNs']for v in details)/total,
            'minimumIndividualScheduledToDispatchFraction':min(v['scheduledToDispatchFraction']for v in details),
            'tailScheduledDuringMaintenanceCycleCount':sum(v['scheduledDuringMaintenanceCycle']for v in details),'arrivals':details})
        assert sha(path)==before;inputs[str(path)]=before
    for name,value in inputs.items():assert sha(Path(name))==value
    return {'passed':True,'arms':reports,'inputsBeforeAfterSha256':inputs,'scriptSha256':sha(Path(__file__).resolve()),
        'scope':'Finite same-arrival component accounting, not subtraction of unrelated percentiles or unique causal proof. Scheduled-to-dispatch includes external FIFO, maintenance dispatch pause and dispatch scheduling; these components are not separated. All three component times sum exactly to each selected arrival total.'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--comparison',type=Path,required=True);p.add_argument('--config',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=run(a.comparison.resolve(),a.config.resolve())
    with a.output.open('x')as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({'passed':True,'arms':len(result['arms']),'output':str(a.output)}))

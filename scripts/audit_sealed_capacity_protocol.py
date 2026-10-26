"""Run original financial/phase/receipt audits for both owned sealed-capacity CI modes."""
from pathlib import Path
import argparse,json,subprocess,sys
from verify_sealed_read_route import verify_capacity_junit

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--junit',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
    verified=verify_capacity_junit(args.junit);output=Path(args.output);assert not output.exists();output.mkdir(parents=True);results={}
    for policy,proof in verified['results'].items():
        root=Path(proof['root']);destination=output/policy
        with(output/(policy+'.stdout')).open('xb')as stdout,(output/(policy+'.stderr')).open('xb')as stderr:
            run=subprocess.run([sys.executable,'-B',str(Path(__file__).with_name('audit-async-capacity-v4.py')),str(root),str(destination)],stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,timeout=120)
        assert run.returncode==0,'original financial/phase/receipt audit failed for '+policy
        audit=json.loads((destination/'RESULT.json').read_text());bounded=policy=='BOUNDED_TURN'
        assert audit['passed']and audit['plannedArrivals']==audit['confirmedAcceptedTrades']==10000 and audit['notSent']==0
        assert audit['readYieldEnabled']is bounded
        if bounded:assert audit['readYieldTurns']>0 and audit['readYieldBusinessAdmissions']>0
        else:assert audit['readYieldTurns']==audit['readYieldBusinessAdmissions']==0
        assert audit['allNewLogicalSubmissionsWithinAllowedAdmissionPhases']and audit['allOriginalDeadlinesUnchanged']and audit['allReadCreditsConsumed']and audit['allDestructiveOriginalIntentsAndBothPrefixReceiptsPredateOffers']
        results[policy]=dict(passed=True,root=str(root),readYieldEnabled=bounded,readYieldTurns=audit['readYieldTurns'],readYieldBusinessAdmissions=audit['readYieldBusinessAdmissions'],plannedArrivals=10000)
    result=dict(passed=True,bothOriginalFinancialAndBoundedDispatchAuditsPassed=True,results=results,performanceClaim=False)
    (output/'RESULT.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps(result))

if __name__=='__main__':main()

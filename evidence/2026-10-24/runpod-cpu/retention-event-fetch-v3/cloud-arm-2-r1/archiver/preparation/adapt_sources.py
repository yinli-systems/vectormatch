"""Deterministic source-only R1 adaptation; does not run a plan, copy evidence or scan payload."""
from pathlib import Path
HERE=Path(__file__).resolve().parent
OLD=HERE.parent/'event-cloud-arm-archive-preparation-r1/archive.py'
source=OLD.read_text()

def change(old,new):
    global source
    assert source.count(old)==1,repr(old)
    source=source.replace(old,new)

source=source.replace('import datetime, hashlib, importlib.util, io, json, shutil, stat, sys, tarfile, zipfile',
                      'import argparse, datetime, hashlib, importlib.util, io, json, shutil, stat, sys, tarfile, zipfile\nfrom archive_contract import validate_identity, selected_page, render_readme')
begin=source.index('def verify_receipts(');end=source.index('\ndef main():',begin)
source=source[:begin]+'''def verify_receipts(trees, plan):
    page=validate_identity(plan);arm=plan['arm']
    review=load(trees['root-review']/'ROOT_REVIEW.json')
    collection=trees['actual-collection']
    success=load(collection/'SUCCESS.json');final=load(collection/'finalized/LOCAL_COLLECTION_COMPLETE.json');raw=load(collection/'raw/result.json')
    for report in (review,success,final,raw):
        require(report['passed'] is True and report['arm']==arm and report['eventFetchCount']==page
                and report['ownerPollMaximumParkNs']==1000000 and report['serverDriverMaximumParkNs']==100000,
                'Actual same arm/page/fixed owner and driver receipts required')
    require(review['sourceCommit']==raw['sourceCommit']==plan['sourceCommit']
            and review['independent4AnchorCodeFingerprint']==plan['codeFingerprint']
            and review['releaseSha256']==raw['releaseSha256']==final['frozenReleaseSha256']==plan['releaseSha256']
            and final['controllerSha256']==plan['controllerSha256'],'Exact same NEW source/release/artifact/controller')
    require(review['allFullOuterMembersVerified'] is True and review['allRawInputsUnchanged'] is True,
            'Independent full outer and original inputs closure')
    for report in (final,raw,review):
        require(report['allOriginalRawCanonicalAndThreeSnapshotsVerified'] is True
                and report['sameNewArtifactFunctionalQualified'] is True,'Actual qualified raw/canonical/three-checkpoint receipts')
    require(p.sha(trees['root-review']/'ROOT_REVIEW.json')==plan['rootReviewSha256'],'Exact actual root review SHA')
    require(p.sha(trees['root-review-preparation-r2']/'review_event_collected.py')==review['scriptSha256'],'Actual executed root helper retained')
    require(len(success['steps'])==5 and all(x['exitCode']==0 for x in success['steps']),'All five actual closed collection steps')
    require(raw['strictSchedulerTimingAdmission'] is True and raw['localFunctionalDiagnosticOptIn'] is False
            and p.sha(collection/'raw/result.json')==review['rawAuditSha256'],'Actual strict root-bound raw receipt')
    require(p.sha(trees['actual-config']/'collector-config.json')==p.sha(collection/'collection/collector-config.json'),'Exact actual config copy')
    gate=load(trees['closed-controller-gate']/'root-controller-closed.json')
    require(gate['arm']==arm and gate['eventFetchCount']==page and gate['executedSourceSha256']==plan['closeProbeSha256']
            and gate['controllerSha256']==plan['controllerSha256'] and gate['frozenReleaseSha256']==plan['releaseSha256'],
            'Actual same-arm closed-controller gate')
    probes=[];matching=[]
    for name,path in sorted(trees.items()):
        if not name.startswith('close-inspection-r'):continue
        output=path/'stdout.json';wire=p.sha(output)
        try:value=load(output);state=value.get('state','MISSING_STATE_PRESERVED')
        except (ValueError,UnicodeError):value={};state='NON_JSON_STDOUT_PRESERVED'
        probes.append(dict(scope=name,state=state,stdoutSha256=wire))
        if wire==gate['inspectionSha256']:
            require(value['state']=='CLOSED_PASS_CONTROL_PLANE' and value['allFourOwnedJvmsStrictlyPidAbsent'] is True
                    and value['controller']['observation']=='PID_ABSENT' and value['arm']==arm and value['eventFetchCount']==page,
                    'Gate must bind one actually present successful closed observation')
            matching.append(name)
    require(1<=len(probes)<=16 and matching,'All actual existing attempts preserved and one exact gate-bound closed proof required')
    return review,probes

''' +source[end:]
change("    plan = load(HERE / 'COPY_PLAN.json')", "    parser=argparse.ArgumentParser(allow_abbrev=False)\n    parser.add_argument('--config',type=Path,required=True);parser.add_argument('--config-sha256',required=True)\n    args=parser.parse_args();config=args.config.absolute()\n    require(p.sha(config)==args.config_sha256,'Explicit exact root-created plan SHA')\n    plan=load(config);validate_identity(plan)")
change("    require(p.sha(PRIMITIVES) == plan['primitivesSha256'], 'Reviewed R2 primitives changed')", "    require(p.sha(HERE/'SOURCE_FROZEN.json')==plan['preparationSha256'],'Exact frozen R2 source closure')\n    require(p.sha(PRIMITIVES) == plan['primitivesSha256'], 'Reviewed R2 primitives changed')")
change("    source_bytes = sum(r['bytes'] for x in plan['sourceTrees'].values() for r in x['inventory']['files'].values())", "    singles={name:Path(row['source']) for name,row in plan['sourceFiles'].items()}\n    for name,path in singles.items():\n        safe(name);require(path.is_relative_to(BASE) and p.row(path)==plan['sourceFiles'][name]['pin'],'Explicit source-only single file changed')\n    source_bytes = sum(r['bytes'] for x in plan['sourceTrees'].values() for r in x['inventory']['files'].values())+sum(row['pin']['bytes']for row in plan['sourceFiles'].values())")
change("    review = verify_receipts(trees, plan)", "    review,probes = verify_receipts(trees, plan)")
change("    shared = Path(plan['sharedPreparation']['path'])\n    for name, expected in plan['sharedPreparation']['receipts'].items():\n        require(p.row(shared / name) == expected, 'Immutable shared deployment archive reference')", "    for reference in plan['sharedArchives']:\n        shared=Path(reference['path'])\n        for name,expected in reference['receipts'].items():require(p.row(shared/name)==expected,'Immutable shared archive reference')")
change("    attempt = HERE / 'attempt-r1'", "    attempt = config.parent/'archive-attempt-r1'")
change("p.sha(HERE / 'COPY_PLAN.json')", "p.sha(config)")
change("        save(target / 'SOURCE_BEFORE_COPY.json', plan['sourceTrees'])", "        for name,path in singles.items():\n            destination=target/name;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,destination)\n            require(p.row(destination)==plan['sourceFiles'][name]['pin'],'Exact source-only single copy')\n        save(target / 'SOURCE_BEFORE_COPY.json', plan['sourceTrees'])\n        save(target/'SOURCE_SINGLE_FILES_BEFORE_COPY.json',plan['sourceFiles'])")
change("            if not destinations:", "            for name,path in singles.items():\n                if source==path:destinations.append(name)\n            if not destinations:")
change("        save(target / 'SHARED_DEPLOYMENT_REFERENCES.json', plan['sharedPreparation'])", "        save(target / 'SHARED_DEPLOYMENT_REFERENCES.json', plan['sharedPreparation'])\n        save(target/'IMMUTABLE_SHARED_ARCHIVE_REFERENCES.json',plan['sharedArchives'])")
change("(HERE / 'COPY_PLAN.json', 'COPY_PLAN.json'), (HERE / 'REGISTRATION.json', 'REGISTRATION.json')", "(config, 'COPY_PLAN.json'), (config.parent / 'REGISTRATION.json', 'REGISTRATION.json')")
change("        p.copy_tree(HERE / 'baseline', archiver / 'baseline', p.snapshot(HERE / 'baseline'))", "        p.copy_tree(HERE,archiver/'preparation',p.snapshot(HERE))")
begin=source.index("        metrics = review['arms'][0]");end=source.index("        for path in sorted(target.rglob('*')):",begin)
source=source[:begin]+"        (target/'README.md').open('x').write(render_readme(plan,review,plan['sourceTrees']['actual-collection']['inventory'],probes))\n"+source[end:]
change("        save(target / 'SOURCE_AFTER_COPY.json', {'passed': True, 'allOriginalsUnchanged': True, 'sourceTrees': after})", "        for name,path in singles.items():require(p.row(path)==plan['sourceFiles'][name]['pin'],'Source-only single aftercopy drift')\n        save(target / 'SOURCE_AFTER_COPY.json', {'passed': True, 'allOriginalsUnchanged': True, 'sourceTrees': after,'sourceFiles':plan['sourceFiles']})")
change("result = {'schemaVersion': 1, 'passed': True, 'arm': 1, 'eventFetchCount': 16,", "result = {'schemaVersion': 1, 'passed': True, 'arm': plan['arm'], 'eventFetchCount': selected_page(plan['arm']),")
change("'rootActualReviewAndBothProbeAttemptsRetained': True", "'rootActualReviewAndAllExistingProbeAttemptsRetained': True,'actualCloseProbeAttempts':len(probes)")
compile(source,str(HERE/'archive.py'),'exec')
with(HERE/'archive.py').open('x')as out:out.write(source)

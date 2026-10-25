from pathlib import Path
import sys,json,subprocess,hashlib,datetime,shutil
R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';A=R/'evidence/2026-10-24/runpod-cpu/retention-dispatch-capacity-v3';O=B/'dispatch-capacity-repeat-2-reporting-private-proof-r1';assert not O.exists()
sys.path.insert(0,str(B/'dispatch-capacity-scope-tar-preparation-r1'));from scope_tar import tree,verify,sha
def git(*args):return subprocess.check_output(['git',*args])
head=git('rev-parse','HEAD').decode().strip()
for branch in ('main','codex/capacity-boundary-repeats-v3'):assert git('ls-remote','origin','refs/heads/'+branch).decode().split()[0]==head
repo=json.loads(subprocess.check_output(['gh','repo','view','yinli-systems/vectormatch','--json','isPrivate,nameWithOwner']));assert repo['isPrivate']
def package(p):
    inv=json.loads((p/'INVENTORY.json').read_text());closed=json.loads((p/'CLOSED.json').read_text());actual=tree(p)
    assert closed['passed']and closed['inventorySha256']==sha(p/'INVENTORY.json')
    assert set(actual['files'])==set(inv['files'])|{'INVENTORY.json','CLOSED.json'}and actual['directories']==inv['directories']
    assert all(actual['files'][n]==row for n,row in inv['files'].items())
    prefix=p.relative_to(R).as_posix();blobs={}
    for e in git('ls-tree','-r','-z',head,'--',prefix).split(b'\0'):
        if e:
            m,n=e.split(b'\t',1);assert m.split()[1]==b'blob';blobs[n.decode()]=m.split()[2].decode()
    names=sorted(blobs);assert set(names)=={prefix+'/'+n for n in actual['files']}
    assert git('hash-object','--',*names).decode().splitlines()==[blobs[n]for n in names]
    return len(names)
report=A/'repeat-2-reporting-r1';reportCount=package(report)
published=['docs/CAPACITY_BOUNDARY_REPEATS_V3.md','docs/DISPATCH_CAPACITY_RESULTS.md','evidence/index.json']
for n in published:assert git('show',head+':'+n)==(R/n).read_bytes()==(report/'published'/n).read_bytes()
index=json.loads((R/'evidence/index.json').read_text());assert len(index['runs'])==51 and len(index['capacityCohorts'])==20
scopes=json.loads((report/'ORIGINAL_SCOPE_INVENTORIES.json').read_text());reportMembers=verify(report/'complete-reporting-scopes.tar.gz',scopes)
O.mkdir();native=[]
for rate in (7500,8000):
    point=A/f'repeat-2-native-{rate}-r1';count=package(point);prefix=point.relative_to(R).as_posix()
    proof=json.loads((B/f'dispatch-capacity-repeat-2-{rate}-private-proof-r1/PRIVATE_PUSH.json').read_text());assert proof['passed']and proof['private']and proof['allOriginalNativeAndRawEvidencePushed']
    subprocess.run(['git','merge-base','--is-ancestor',proof['commit'],head],check=True)
    mirror=json.loads(git('show',head+':'+prefix+'/SOURCE_MIRRORS.json'));inventory=json.loads(git('show',head+':'+prefix+'/ORIGINAL_SCOPE_INVENTORIES.json'))
    large=json.loads(git('show',head+':'+prefix+'/ORIGINAL_LARGE_FILES.json'))['files'];name=mirror['archiveName'];entry=large[name]
    assert shutil.disk_usage(R).free>entry['bytes']+1024**3
    restored=O/f'restored-{rate}.tar.gz';full=hashlib.sha256();written=0
    with restored.open('xb')as out:
        for part in entry['parts']:
            assert part['offset']==written;h=hashlib.sha256();size=0
            p=subprocess.Popen(['git','cat-file','blob',head+':'+prefix+'/'+part['path']],stdout=subprocess.PIPE)
            for block in iter(lambda:p.stdout.read(1024**2),b''):out.write(block);h.update(block);full.update(block);size+=len(block)
            p.stdout.close();assert p.wait()==0 and size==part['bytes']and h.hexdigest()==part['sha256'];written+=size
    assert written==entry['bytes']==mirror['archiveBytes']and full.hexdigest()==entry['sha256']==mirror['archiveSha256']==proof['archiveCompressedOriginalScopesSha256']
    members=verify(restored,inventory);assert members==mirror['fullMemberReview']
    row=dict(rate=rate,gitBlobsVerified=count,sourcePrivateCommit=proof['commit'],restoredDirectlyFromCommittedGitBlobs=True,bytes=written,sha256=full.hexdigest(),memberReview=members,onlyGeneratedDuplicateRemoved=True)
    (O/f'NATIVE_{rate}.json').write_text(json.dumps(row,indent=2,sort_keys=True)+'\n');restored.unlink();native.append(row)
result=dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),private=True,repository=repo['nameWithOwner'],commit=head,bothRemoteBranchesVerified=True,
    reportingGitBlobsVerified=reportCount,reportingScopeMembersVerified=reportMembers,publishedGitBlobsVerified=len(published),native=native,
    actualRestorationDirectlyFromCommittedGitBlobsVerified=True,records=51,cohorts=20,all49PriorRecordsAndOriginalFivePointsPreserved=True,higherLoadPermitted=False,browserRenderVerified=False,sourceSha256=sha(Path(__file__)))
(O/'PRIVATE_PUSH.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps({k:v for k,v in result.items()if k!='native'}))

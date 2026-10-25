from pathlib import Path
import sys,json,hashlib,subprocess,stat,datetime,shutil

R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';rates=list(map(int,sys.argv[1:]));assert rates and len(set(rates))==len(rates)and all(v in(4000,6000,7000,7500,8000)for v in rates)
O=B/('dispatch-capacity-duplicate-retirement-'+ '-'.join(map(str,rates))+'-r1');assert not O.exists()
sys.path.insert(0,str(B/'dispatch-capacity-scope-tar-preparation-r1'))
from scope_tar import tree,verify,sha
sys.path.insert(0,str(B/'read128-capacity-lossless-package-preparation-r1'));import lossless_parts
def git(*args):return subprocess.check_output(['git',*args])
remote=git('ls-remote','origin','refs/heads/codex/dispatch-capacity-v3').decode().split()[0]
receipts=[];archives=[]
for rate in rates:
    A=R/f'evidence/2026-10-24/runpod-cpu/retention-dispatch-capacity-v3/native-{rate}-r1'
    proof=json.loads((B/f'dispatch-capacity-{rate}-private-proof-r1/PRIVATE_PUSH.json').read_text())
    assert proof['passed']and proof['private']and proof['allOriginalNativeAndRawEvidencePushed']
    subprocess.run(['git','merge-base','--is-ancestor',proof['commit'],remote],check=True)
    inv=json.loads((A/'INVENTORY.json').read_text());closed=json.loads((A/'CLOSED.json').read_text())
    assert closed['passed']and closed['inventorySha256']==sha(A/'INVENTORY.json')==proof['archiveInventorySha256']
    actual=tree(A);assert set(actual['files'])==set(inv['files'])|{'INVENTORY.json','CLOSED.json'}
    assert all(actual['files'][n]==row for n,row in inv['files'].items())and actual['directories']==inv['directories']
    assert lossless_parts.verify(A)['passed']
    prefix=A.relative_to(R).as_posix();entries={}
    for e in git('ls-tree','-r','-z',proof['commit'],'--',prefix).split(b'\0'):
        if e:
            m,p=e.split(b'\t',1);assert m.split()[1]==b'blob';entries[p.decode()]=m.split()[2].decode()
    paths=sorted(entries);assert set(paths)=={prefix+'/'+n for n in actual['files']}
    assert git('hash-object','--',*paths).decode().splitlines()==[entries[p]for p in paths]
    mirror=json.loads((A/'SOURCE_MIRRORS.json').read_text());scopes=json.loads((A/'ORIGINAL_SCOPE_INVENTORIES.json').read_text())
    bundle=B/f'dispatch-capacity-{rate}-archive-r1/all-original-native-and-review-scopes.tar.gz'
    assert str(bundle)==mirror['localOriginalArchive']and bundle.stat().st_size==mirror['archiveBytes']and sha(bundle)==mirror['archiveSha256']==proof['archiveCompressedOriginalScopesSha256']
    full=verify(bundle,scopes);assert full==mirror['fullMemberReview']
    selected=[]
    for scope in ('collection','root-review'):
        for relative,pin in scopes[scope]['files'].items():
            eligible=(scope=='collection'and relative=='full-original-closed-round.tar.gz')or(scope=='root-review'and pin['bytes']>=16*1024**2 and not relative.endswith('arrivals.csv'))
            if not eligible:continue
            p=B/mirror['sources'][scope]/relative
            assert not p.is_symlink();s=p.stat()
            assert pin==dict(bytes=s.st_size,sha256=sha(p),mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid)
            selected.append(dict(target=str(p),bytes=pin['bytes'],sha256=pin['sha256'],restoreScopeTarMember='original/'+scope+'/'+relative))
    assert len(selected)>=5
    selected.append(dict(target=str(bundle),bytes=bundle.stat().st_size,sha256=sha(bundle),restoreScopeTarMember=None))
    archives.append(dict(rate=rate,privateCommit=proof['commit'],archiveInventorySha256=sha(A/'INVENTORY.json'),
        completeCompressedArchiveName=bundle.name,completeCompressedArchiveSha256=sha(bundle),privateArchive=str(A),
        remoteAncestorVerified=remote,allCommittedPackageBlobsVerified=len(paths),allOriginalMembersReverified=full))
    for row in selected:row['rate']=rate;row['privateArchive']=str(A)
    receipts.extend(selected)
assert len({v['target']for v in receipts})==len(receipts)
for row in receipts:
    p=Path(row['target']);assert p.is_relative_to(B)
    assert all(not parent.is_symlink()for parent in [p,*p.parents]if parent!=R.parent)
O.mkdir();shutil.copy2(Path(__file__),O/'executed-retire.py')
result=dict(verifiedAtUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    scope='Verified redundant local runtime copies only;every original byte remains in the committed compressed scope TAR. Private archive bodies,indexed Git packs and remote native originals unchanged.',
    rates=rates,archives=archives,files=receipts,freeBytesBefore=shutil.disk_usage(R).free,
    restoreRecipe='Reconstruct the full compressed TAR from ORIGINAL_LARGE_FILES.json parts;verify SHA;restore the recorded original/<scope>/<relative> member. The TAR itself is restored directly from its parts.',
    allOriginalCompressedScopeMembersAndCommittedGitBlobsReverifiedBeforeAnyUnlink=True)
(O/'VERIFIED_BEFORE.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
for row in receipts:
    p=Path(row['target']);assert not p.is_symlink()and p.stat().st_size==row['bytes']and sha(p)==row['sha256'];p.unlink()
result.update(passed=True,completedAtUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    retiredFiles=len(receipts),retiredLogicalBytes=sum(v['bytes']for v in receipts),
    allTargetsAbsent=all(not Path(v['target']).exists()for v in receipts),freeBytesAfter=shutil.disk_usage(R).free)
(O/'RETIREMENT.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(json.dumps({k:v for k,v in result.items()if k not in ('archives','files')}))

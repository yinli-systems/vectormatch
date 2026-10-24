"""LOCAL ONLY: bind a real completed stage and explicit source allowlist; no SSH at import or CLI."""
from pathlib import Path,PurePosixPath
import argparse,datetime,hashlib,importlib.util,json,shutil,stat,tarfile
HERE=Path(__file__).resolve().parent
PREP='/opt/vectormatch-cpu/preparation/window-cloud-abab-r1'
RELEASE='2a31b6f0d6b08c6863aef422a2bafa12d67a6ad11b651cbd2377b7b863943bed'
ROOT_FREEZE='6033e6119e2ba04608716974b3b13b1b6c46025bc88b2e12c2f1ada50a18e685'
PREPARATION='a1c00b76d064eca9d7d4f357894b5c6c8019248978acc515253e33d18010e36d'
CONTROLLER='be513acb641e7fd836b05720ee3a274ee815f7d69335008aa4ff38f898c4ba31'
PROTECTED='6769aa2590668ba69692b17565c3463cc274b1fa2a777129d742c1e04899f753'
REMOTE='0922e32bee55b1e47503880e763fcf112626649d31f037bb62e5c4ceb588bb73'
def require(ok,msg):
 if not ok:raise ValueError(msg)
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def no_links(p):
 p=Path(p).absolute()
 require(not any(q.is_symlink() for q in [p]+list(p.parents)),'Symlink input refused');return p

def reference(p,h):
 p=no_links(p);require(p.is_file() and p.stat().st_size<=32*1024**2 and sha(p)==h,'Missing, oversized or changed reference');return p

def read(p):return json.loads(Path(p).read_text())
def save(p,x):
 with p.open('x') as f:json.dump(x,f,indent=2,sort_keys=True);f.write('\n')
def frozen_sources():
 root=HERE/'frozen';reference(root/'LOCAL_PREPARATION_FROZEN.json',PREPARATION);f=read(root/'LOCAL_PREPARATION_FROZEN.json')
 require(len(f['files'])==16,'Exactly16 reviewed sources')
 for n,r in f['files'].items():
  p=reference(root/n,r['sha256']);require(p.stat().st_size==r['bytes'] and stat.S_IMODE(p.stat().st_mode)==r['mode'],'Frozen source size/mode differs')
 return f

def stage_inputs(path,expected_sha):
 path=reference(path,expected_sha);require(path.name=='STAGE_SUCCESS.json','Actual STAGE_SUCCESS receipt required');s=read(path);f=frozen_sources()
 keys={'passed','rootVerifiedFreezeSha256','releaseSha256','stageBundleSha256','remotePrep','controllerSha256','protectedManifestSha256','stagedFiles','localSourcePaths','remoteHelper','linuxGuardTests','readOnlyPreflightPassed','applicationStarted','resourceCreated'}
 require(set(s)==keys,'Unknown or missing stage receipt field')
 require(s['passed'] is True and s['rootVerifiedFreezeSha256']==ROOT_FREEZE and s['releaseSha256']==RELEASE and s['remotePrep']==PREP and s['controllerSha256']==CONTROLLER and s['protectedManifestSha256']==PROTECTED,'Stage identity/freeze differs')
 require(s['linuxGuardTests']==122 and s['readOnlyPreflightPassed'] is True and s['applicationStarted'] is False and s['resourceCreated'] is False,'Stage guards/preflight incomplete')
 names=set(f['files'])|{'LOCAL_PREPARATION_FROZEN.json','release/release.json','release/current-stopped-original-state.json'}|{'release/lib/'+n for n in ['cluster-0.1.0-SNAPSHOT.jar','core-0.1.0-SNAPSHOT.jar','aeron-all-1.53.3.jar','agrona-2.6.1.jar']}
 require(len(names)==23 and set(s['stagedFiles'])==set(s['localSourcePaths'])==names,'All and only23 staged sources required')
 for n,r in s['stagedFiles'].items():
  q=PurePosixPath(n);require(str(q)==n and not q.is_absolute() and '..' not in q.parts,'Unsafe staged path')
  require(set(r)=={'bytes','sha256','mode'} and type(r['bytes']) is int and 0<r['bytes']<=32*1024**2,'Invalid staged row')
  p=reference(s['localSourcePaths'][n],r['sha256']);require(p.stat().st_size==r['bytes'] and stat.S_IMODE(p.stat().st_mode)==r['mode'],'Actual staged local source size/mode')
  if n in f['files']:require(r==f['files'][n],'Reviewed16 source differs')
 require(s['stagedFiles']['LOCAL_PREPARATION_FROZEN.json']['sha256']==PREPARATION,'Staged preparation manifest differs')
 require(s['stagedFiles']['release/release.json']['sha256']==RELEASE and s['stagedFiles']['release/current-stopped-original-state.json']['sha256']==PROTECTED,'Staged release/protected identity differs')
 release=read(s['localSourcePaths']['release/release.json']);require(release['releaseReady'] is True and release['controllerSha256']==CONTROLLER,'Root ready release required')
 bundle=reference(path.parent/'stage-bundle.tar.gz',s['stageBundleSha256']);seen=set()
 with tarfile.open(bundle,'r:gz') as tar:
  for m in tar:
   require(m.isfile() and m.name in names and m.name not in seen,'Unexpected/duplicate stage bundle member');r=s['stagedFiles'][m.name]
   require((m.size,m.mode)==(r['bytes'],r['mode']) and hashlib.sha256(tar.extractfile(m).read()).hexdigest()==r['sha256'],'Stage bundle bytes/mode differs');seen.add(m.name)
 require(seen==names,'Stage bundle missing source')
 helper=s['remoteHelper'];require(set(helper)=={'path','sha256'} and helper['sha256']==REMOTE,'Explicit frozen remote helper reference required');reference(helper['path'],helper['sha256'])
 return s,release

def prior(round_number,path,expected_sha):
 if round_number==1:require(path is None and expected_sha is None,'Round1 cannot use future gate');return None
 require(round_number==2 and path is not None and expected_sha is not None,'Round2 requires explicit root round1 gate')
 p=reference(path,expected_sha);g=read(p)
 require(g['schemaVersion']==1 and g['scope']=='ROOT_VERIFIED_CLOSED_WINDOW_ROUND_1_COLLECTION' and g['collectionComplete'] is True and g['round']==1 and g['frozenReleaseSha256']==RELEASE and g['controllerSha256']==CONTROLLER,'Wrong/incomplete prior root gate')
 require(g['localFullMemberShaBytesModesOwnersEmptyDirsVerified'] is True and g['allRawInputsAndFailuresRetained'] is True,'Prior closure lacks complete raw/member retention')
 for k in ['independentLocalCollectionReceiptSha256','closedArchiveSha256','closedNativeInventorySha256']:require(isinstance(g[k],str) and len(g[k])==64 and all(x in '0123456789abcdef' for x in g[k]),'Missing prior evidence SHA')
 return p

def build(stage,stage_sha,round_number,output,gate=None,gate_sha=None):
 s,r=stage_inputs(stage,stage_sha);g=prior(round_number,gate,gate_sha);require(round_number in (1,2),'Onlyround1/2');output=no_links(output);require(not output.exists(),'Fresh output only; preserve failures');output.mkdir(parents=True,mode=0o700);inputs=output/'inputs';inputs.mkdir()
 for source,name in [(Path(stage),'STAGE_SUCCESS.json'),(Path(stage).parent/'stage-bundle.tar.gz','stage-bundle.tar.gz'),(Path(s['localSourcePaths']['release/release.json']),'release.json'),(Path(s['localSourcePaths']['release/current-stopped-original-state.json']),'protected-reference.json')]:shutil.copy2(source,inputs/name)
 if g:shutil.copy2(g,inputs/'round-1-collection-gate.json')
 config={'schemaVersion':1,'round':round_number,'remotePrep':PREP,'host':'ed6c0673f5cb','releaseLocal':str((inputs/'release.json').resolve()),'releaseSha256':RELEASE,'stagingReceipt':str((inputs/'STAGE_SUCCESS.json').resolve()),'stagingReceiptSha256':stage_sha,'protectedReference':str((inputs/'protected-reference.json').resolve()),'protectedReferenceSha256':PROTECTED,'executionMetadata':['round-%d-execution-register.json'%round_number,'round-%d-execution.stdout'%round_number,'round-%d-execution.stderr'%round_number],'round1GateLocal':str((inputs/'round-1-collection-gate.json').resolve()) if g else None,'round1GateSha256':gate_sha if g else None}
 save(output/'collector-config.json',config)
 spec=importlib.util.spec_from_file_location('bound_window_common',HERE/'frozen/common.py');common=importlib.util.module_from_spec(spec);spec.loader.exec_module(common);c,release,expected,allow=common.load_config(output/'collector-config.json')
 require(len(expected)==23+(1 if g else 0) and len(allow)==26+(1 if g else 0),'Exact source plus3 opaque metadata allowlist')
 receipt={'createdAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'passed':True,'round':round_number,'configSha256':sha(output/'collector-config.json'),'actualStageReceiptSha256':stage_sha,'originalStageReceipt':str(Path(stage).resolve()),'stageBundleSha256':s['stageBundleSha256'],'sourceAllowlist':allow,'stageSourceCount':23,'opaqueExecutionMetadataCount':3,'registerJsonIsOpaqueJsonl':True,'round2OnlyAdditionalFile':'release/round-1-collection-gate.json' if g else None,'frozenPreparationSha256':PREPARATION,'remoteAccessed':False,'actualClosedControllerProofStillRequiredBeforeCollection':True};save(output/'CONFIG_BOUND.json',receipt);return receipt

def main():
 p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False);p.add_argument('--stage-success',required=True,type=Path);p.add_argument('--stage-success-sha256',required=True);p.add_argument('--round',required=True,type=int,choices=[1,2]);p.add_argument('--output',required=True,type=Path);p.add_argument('--round1-gate',type=Path);p.add_argument('--round1-gate-sha256');a=p.parse_args();print(json.dumps(build(a.stage_success,a.stage_success_sha256,a.round,a.output,a.round1_gate,a.round1_gate_sha256),indent=2))
if __name__=='__main__':main()

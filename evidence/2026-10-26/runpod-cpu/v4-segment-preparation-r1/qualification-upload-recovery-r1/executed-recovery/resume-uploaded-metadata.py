"""Read-only metadata recovery after a completed upload;never uploads or replays native work."""
from pathlib import Path
import sys,json,hashlib,subprocess,datetime,shutil,os
R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';W=B/'interbank-v4-worktree';P=Path(__file__).resolve().parent
factor=sys.argv[1];rate=int(sys.argv[2]);arm=sys.argv[3];case=factor+'-'+str(rate)+'-'+arm
C=B/('v4-segment-'+case+'-closure-r1');A=W/('evidence/2026-10-26/runpod-cpu/v4-segment-preparation-r1/'+case+'-native-r1');T=B/('v4-segment-'+case+'-archive-r1');assert not A.exists()
O=B/('v4-segment-'+case+'-archive-metadata-recovery-r1');assert not O.exists();O.mkdir()
sys.path.insert(0,str(B/'dispatch-capacity-scope-tar-preparation-r1'));from scope_tar import sha,tree,verify
manifest=json.loads((C/'remote-manifest.json').read_text());closed=json.loads((C/'VERIFIED.json').read_text());analysis=json.loads((C/'ANALYSIS.json').read_text());audit=json.loads((C/'AUDIT.json').read_text())
assert closed['nativePassed']and closed['independentAuditPassed']and closed['analysisPassed']and analysis['passed']and audit['passed']
bundle=T/('v4-segment-'+case+'-complete-original-scopes-r1.tar.gz');original=C/'complete-native-point-and-independent-audit.tar.gz';registration=json.loads((T/'UPLOAD_REGISTRATION.json').read_text())
assert json.loads((T/'UPLOAD_EXECUTION.json').read_text())['exitCode']==0 and bundle.stat().st_size==registration['bytes']and sha(bundle)==sha(original)==registration['sha256']
review=verify(bundle,manifest['sourceScopes']);assert review==manifest['everyOriginalMemberVerified']
repo='yinli-systems/vectormatch';release_id=423510304;tag='evidence-private-20261025'
def api(path):return json.loads(subprocess.check_output(['gh','api',path],env={**os.environ,'GODEBUG':'http2client=0'}))
source=(P/'archive.py').read_text();start=source.index("release=api('repos/'+repo+'/releases/'+str(release_id));matches=");suffix=source[start:]
record=dict(atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),passedUploadExitCode=0,assetName=bundle.name,bytes=bundle.stat().st_size,sha256=sha(bundle),reason='TCP connection refused during post-upload release metadata GET',readOnlyMetadataRetryOnly=True,noUploadOrNativeReplay=True,originalArchiveSourceSha256=hashlib.sha256(source.encode()).hexdigest(),postUploadSuffixSha256=hashlib.sha256(suffix.encode()).hexdigest())
(O/'REGISTRATION.json').write_text(json.dumps(record,indent=2,sort_keys=True)+'\n');shutil.copy2(Path(__file__),O/'resume-uploaded-metadata.py')
exec(compile(suffix,str(P/'archive.py')+':post-upload-only','exec'),globals())
(O/'RESULT.json').write_text(json.dumps(dict(passed=True,onlyPostUploadMetadataAndLocalManifestPublicationResumed=True,noUploadOrNativeReplay=True,closedPackage=str(A)),indent=2,sort_keys=True)+'\n')

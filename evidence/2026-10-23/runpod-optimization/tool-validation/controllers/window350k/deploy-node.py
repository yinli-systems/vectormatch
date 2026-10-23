"""Upload/check a new immutable release and run launcher tests; never start nodes."""
import json
import shlex
import campaign as c


REMOTE_VERIFY = '''import pathlib,hashlib,tarfile,json,subprocess,sys
base=pathlib.Path(RELEASE)
manifest=base/'DEPLOYMENT.json'
if not manifest.exists():
 assert {p.name for p in base.iterdir()} <= {'bundle.tar.gz.part'}
 part=base/'bundle.tar.gz.part';assert hashlib.sha256(part.read_bytes()).hexdigest()==EXPECTED
 with tarfile.open(part) as archive:
  for member in archive.getmembers():
   q=pathlib.PurePosixPath(member.name)
   assert not q.is_absolute() and '..' not in q.parts and (member.isfile() or member.isdir())
  archive.extractall(base)
 part.replace(base/'bundle.tar.gz')
assert hashlib.sha256((base/'bundle.tar.gz').read_bytes()).hexdigest()==EXPECTED
d=json.loads(manifest.read_text());assert d==MANIFEST
for name,digest in d['files'].items():assert hashlib.sha256((base/name).read_bytes()).hexdigest()==digest
p=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',str(base/'deploy'),'-p','test_remote_service.py'],capture_output=True,text=True,timeout=40)
print(json.dumps({'verified':p.returncode==0,'nodeRevision':d['revision'],'files':d['files'],'launcherTest':{'exitCode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}}))
raise SystemExit(p.returncode)
'''


def main():
    identity = c.artifact_inputs(require_upload=False)
    node = identity['node']
    target = c.EVIDENCE / 'window350k/node-upload-receipt.json'
    assert not target.exists(), 'Upload receipt exists; validate/resume it explicitly, never overwrite'
    manifest = c.archive_manifest(node)

    def one(member):
        # Upload only to the separate commit-named immutable release directory.
        release = node['root']
        assert release.startswith('/opt/vectormatch/optimization-node-releases/')
        result = c.remote.run(member, 'mkdir -p ' + shlex.quote(release))
        assert result.returncode == 0
        inspect = ('import pathlib,json\np=pathlib.Path(' + repr(release) + ')\n'
                   'print(json.dumps({"manifestPresent":(p/"DEPLOYMENT.json").exists()}))')
        existing = json.loads(c.py(member, inspect, 20))
        if not existing['manifestPresent']:
            transfer = c.remote.upload(member, node['archive'], release + '/bundle.tar.gz.part')
            assert transfer.returncode == 0, 'Node bundle transfer failed'
        code = ('RELEASE=' + repr(release) + '\nEXPECTED=' + repr(node['bundleSha256'])
                + '\nMANIFEST=' + repr(manifest) + '\n' + REMOTE_VERIFY)
        receipt = json.loads(c.py(member, code, 65))
        receipt['node'] = member
        return receipt

    rows = c.parallel(one)
    assert len(rows) == 3 and all(row['verified'] for row in rows)
    c.exclusive_save(target, {'timestamp': c.now(), 'bundleSha256': node['bundleSha256'],
                            'nodes': rows, 'scope': 'Immutable new release transfer/hash and Linux launcher unit tests only; no node, load, original service or kernel setting is started/stopped/changed.'})
    print('WINDOW350K_NODE_UPLOAD_VERIFIED', node['revision'], flush=True)


if __name__ == '__main__':
    main()

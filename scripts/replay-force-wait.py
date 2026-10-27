#!/usr/bin/env python3
"""Independently recompute force joins after authenticated archive retrieval."""
from pathlib import Path
import argparse,json,hashlib,importlib.util

def replay(root,thin):
 root=Path(root);thin=Path(thin);receipt=json.loads((root/'FETCH_VERIFIED.json').read_text());manifest=json.loads((root/'ARCHIVE_MEMBER_MANIFEST.json').read_text())
 assert receipt['allMembersVerified']==len(manifest['files']) and receipt['onlySelectedMembersExtracted']
 for n in receipt['selectedFiles']:
  b=(root/n).read_bytes();v=manifest['files'][n];assert len(b)==v['bytes'] and hashlib.sha256(b).hexdigest()==v['sha256'],n
 expected=json.loads((thin/'AUDIT.json').read_text())['forceWait']
 spec=importlib.util.spec_from_file_location('force',Path(__file__).with_name('audit-force-wait.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 actual=module.audit_wait(root);assert actual==expected
 b=(root/'force-attribution.csv').read_bytes();v=manifest['files']['force-attribution.csv'];assert len(b)==v['bytes'] and hashlib.sha256(b).hexdigest()==v['sha256']
 return {'allSelectedInputsVerified':True,'allOriginalArchiveMembersPreviouslyVerified':receipt['allMembersVerified'],'forceAttributionRecomputedByteIdentical':True,'forceAuditRecomputedEqual':True,'originals':actual['allOriginalsJoined'],'assetId':receipt['assetId'],'archiveSha256':receipt['archiveSha256'],'recomputedCsvSha256':v['sha256']}

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('thin',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();v=replay(a.root,a.thin);a.output.write_text(json.dumps(v,indent=2)+'\n');print(json.dumps(v))

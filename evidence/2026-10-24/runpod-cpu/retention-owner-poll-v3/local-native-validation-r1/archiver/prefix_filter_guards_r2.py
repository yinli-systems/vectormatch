"""Pure in-memory equivalence cases; synthetic marker strings assembled, never credentials."""
from pathlib import Path
import hashlib,importlib.util,io,json
HERE=Path(__file__).resolve().parent
source=HERE/'review_resume_r2.py'
spec=importlib.util.spec_from_file_location('_owner_archive_review_r2',source);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
def matches(pattern,data):return[(v.lastgroup,v.start(),v.end())for v in pattern.finditer(data)]
def main():
 tokens=[b'-----BEGIN '+b'OPENSSH '+b'PRIVATE KEY-----',b'gh'+b'p_'+b'A'*40,b'AK'+b'IA'+b'B'*16,b'AS'+b'IA'+b'C'*16,b'rpa'+b'_'+b'D'*30,b'sk'+b'-'+b'E'*40,b'xox'+b'b-'+b'F'*30]
 corpus=b'\x00'.join(tokens)
 assert matches(module.ORIGINAL_PATTERN,corpus)==matches(module.PATTERN,corpus)and len(matches(module.PATTERN,corpus))==7
 zero=b'\x00'*(2*1024**2+7);module.SCANNED.clear();module.FINDINGS.clear();result=module.scan(io.BytesIO(zero),'synthetic-zero')
 assert result['bytes']==len(zero)and result['sha256']==hashlib.sha256(zero).hexdigest()and not module.FINDINGS
 for token in tokens:
  data=b'\x00'*(1024**2-3)+token+b'\x00'*17
  module.FINDINGS.clear();module.scan(io.BytesIO(data),'synthetic-boundary')
  assert {v['kind']for v in module.FINDINGS}=={v[0]for v in matches(module.ORIGINAL_PATTERN,data)}
 result={'passed':True,'cases':3,'syntheticClasses':7,'boundaryCases':len(tokens),'originalRegexSourcePreserved':True,'necessaryPrefixFilterEquivalentForAllRegexAlternatives':True,'zeroStreamStillFullyHashedAndCounted':True,'sourceSha256':hashlib.sha256(source.read_bytes()).hexdigest(),'fixtureSourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'noActualNativeReadOrProcess':True}
 with(HERE/'PREFIX_FILTER_GUARDS_R2.json').open('x')as f:json.dump(result,f,indent=2);f.write('\n')
 print(json.dumps(result))
if __name__=='__main__':main()

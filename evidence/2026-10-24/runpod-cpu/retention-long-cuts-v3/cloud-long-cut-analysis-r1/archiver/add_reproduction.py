from pathlib import Path
import datetime,hashlib,json,shutil,stat
HERE=Path(__file__).resolve().parent
WORKSPACE=HERE.parents[3]
OUT=WORKSPACE/'evidence/2026-10-24/runpod-cpu/retention-long-cuts-v3/cloud-long-cut-analysis-r1'
SOURCE=HERE.parent/'long-cut-portable-reproduction-r1'
def row(p):
 s=p.lstat();assert stat.S_ISREG(s.st_mode);return {'bytes':s.st_size,'mode':s.st_mode&0o777,'uid':s.st_uid,'gid':s.st_gid,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def census(root):
 files={};dirs={}
 for p in [root]+sorted(root.rglob('*')):
  assert not p.is_symlink()
  if p.is_dir():s=p.stat();dirs[str(p.relative_to(root))or'.']={'mode':s.st_mode&0o777,'uid':s.st_uid,'gid':s.st_gid}
  else:files[str(p.relative_to(root))]=row(p)
 return files,dirs
def save(p,v):
 with p.open('x')as f:json.dump(v,f,indent=2);f.write('\n')
def main():
 assert not(OUT/'CLOSED.json').exists();closed=json.loads((SOURCE/'CLOSED.json').read_text());assert closed['passed']is True and closed['singleAnalyzerExecution']is True
 files,dirs=census(SOURCE);dst=OUT/'portable-reproduction-r1';assert not dst.exists()
 for rel,meta in dirs.items():p=dst if rel=='.'else dst/rel;p.mkdir(parents=True,exist_ok=True);p.chmod(meta['mode'])
 for rel,pin in files.items():shutil.copy2(SOURCE/rel,dst/rel);assert row(dst/rel)==pin
 assert census(SOURCE)==(files,dirs)==census(dst)
 comparison=json.loads((dst/'RESULT_COMPARISON.json').read_text());assert comparison['allOtherFieldsExactlyEqualIncludingInputBytesAndSha']is True and comparison['allSourceConfigOriginalAnd18InputsUnchanged']is True and comparison['rawArchiveClosureUnchanged']is True
 assert row(OUT/'REPRODUCTION_CONFIG.json')==json.loads((dst/'INPUTS_AFTER.json').read_text())['config']
 save(OUT/'PORTABLE_REPRODUCTION_COPY_BINDINGS.json',{'passed':True,'sourceRoot':str(SOURCE),'files':files,'directories':dirs,'allFilesShaSizeModesOwnersAndEmptyDirectoryClosureEqual':True,'sourceBeforeAfterEqual':True,'onlyOneAnalyzerExecution':True,'exactNonPathNonConfigResultComparisonPassed':True,'originalAnalysisAndRawParentUnchanged':True,'noRawInputsCopied':True})
 # This evidence directory is not closed yet; update only newly authored explanatory metadata.
 p=OUT/'ARCHIVED_INPUT_BINDINGS.json';d=json.loads(p.read_text());d['note']='Original derivation config/results remain byte-exact with runtime paths. Separate reproduction config relocates18paths to closed archive payloads. One subsequently root-authorized portable reproduction passed; see portable-reproduction-r1. No raw payload copied.';p.write_text(json.dumps(d,indent=2)+'\n')
 p=OUT/'DERIVATION_AND_QUALIFICATION_REVIEW.json';d=json.loads(p.read_text());d.pop('newAnalyzerOrRawAuditorExecution');d['initialArchiveBindingExecutedNoAnalyzerOrRawAuditor']=True;d['subsequentAuthorizedPortableReproduction']={'executions':1,'closedSha256':row(dst/'CLOSED.json')['sha256'],'comparisonSha256':row(dst/'RESULT_COMPARISON.json')['sha256'],'allNonPathNonConfigFieldsExactlyEqual':True};p.write_text(json.dumps(d,indent=2)+'\n')
 p=OUT/'README.md';text=p.read_text();text=text.replace('no byte-identical rerun is claimed.','the raw result JSON differs in those path/config metadata fields only.');text=text.replace('This task rehashed only the18archived input payloads to bind the reproduction map; it did not repeat the analyzer, root bucket calculation, raw wire auditor, guards, Java, SSH, Git or any cloud action.','The initial archive step rehashed the18archived input payloads to bind the reproduction map. Root then authorized ONE portable local analyzer execution, preserved in portable-reproduction-r1. All fields except configSha256 and the18inputClosure.path values matched the original exactly, including every input byte/SHA, cut count, latency, conservation bucket and interpretation flag. Source/config/original result/18inputs and closed raw inventory/closure were unchanged before/after. No root bucket calculation, raw wire auditor, guards, Java, SSH, Git or cloud action was repeated.');p.write_text(text)
 save(HERE/'REPRODUCTION_ADDED.json',{'passed':True,'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sourceFiles':len(files),'sourceBytes':sum(r['bytes']for r in files.values()),'sourceClosedSha256':files['CLOSED.json']['sha256'],'reproductionComparisonSha256':files['RESULT_COMPARISON.json']['sha256'],'reproductionResultSha256':files['derived/result.json']['sha256'],'allCopiesAndSourceDirectoryMetadataEqual':True,'scope':'Archive already closed authorized reproduction; no analyzer rerun here'});print((HERE/'REPRODUCTION_ADDED.json').read_text())
if __name__=='__main__':main()

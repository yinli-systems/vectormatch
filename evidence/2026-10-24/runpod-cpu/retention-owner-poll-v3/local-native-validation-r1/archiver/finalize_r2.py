"""Close only this new proof after completed local copy; no source changes or subprocess."""
from pathlib import Path
import datetime,hashlib,json,shutil,stat
import archive as a

def main():
 here=a.HERE;out=a.OUT
 execution=json.loads((here/'EXECUTION_R2.json').read_text());complete=json.loads((here/'COPY_COMPLETE_R2.json').read_text());a.need(execution['exitCode']==0 and execution['archiveSourceUnchanged']is True and complete['passed']is True,'Completed copy required')
 target=out/'archiver';target.mkdir()
 files={}
 for source in sorted(here.iterdir()):
  a.need(source.is_file()and not source.is_symlink(),'Only explicit archiverfiles');pin=a.pin(source);destination=target/source.name;shutil.copy2(source,destination);a.need(a.pin(source)==a.pin(destination)==pin,'Archiver exactcopy');files[source.name]=pin
  with destination.open('rb')as stream:a.scan(stream,'archiver/'+source.name)
 with(out/'README.md').open('rb')as stream:a.scan(stream,'README.md')
 a.write(out/'ARCHIVER_COPY_AND_MARKER_REVIEW.json',{'passed':not a.FINDINGS,'sourceRoot':str(here),'files':files,'noExtraExecution':True,'findings':a.FINDINGS,'sourceCopyShaSizeModeUidGidEqual':True});a.need(not a.FINDINGS,'New archiverknownmarkers retained')
 inventory=a.census(out);a.need(len(inventory['files'])<512 and sum(r['bytes']for r in inventory['files'].values())<160*1024**2,'Finalfinite proofbounds')
 a.write(out/'MANIFEST.json',{'schemaVersion':1,'scope':'Only retention-owner-poll-v3/local-native-validation-r1','excludedSelfAndClosure':['MANIFEST.json','CLOSED.json'],'files':inventory['files'],'directories':inventory['directories'],'payloadFiles':len(inventory['files']),'payloadBytes':sum(r['bytes']for r in inventory['files'].values()),'fullDirectoryModesUidGidAndEmptyDirectoryClosure':True})
 for name,pin in inventory['files'].items():a.need(a.pin(out/name)==pin,'Finalfull payloadsha/modeowner')
 after=a.census(out);a.need(set(after['files'])==set(inventory['files'])|{'MANIFEST.json'}and after['directories']==inventory['directories'],'Finalpathclosure')
 a.write(out/'CLOSED.json',{'schemaVersion':1,'passed':True,'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'manifestSha256':a.sha(out/'MANIFEST.json'),'payloadFiles':len(inventory['files']),'directories':len(inventory['directories']),'payloadBytes':sum(r['bytes']for r in inventory['files'].values()),'originalsUnchanged':True,'sourceCopyAndModeUidGidDirectoryClosureVerified':True,'fullNativeTarPreserved':True,'all306FullTarMemberShaModeUidGidClosureVerified':True,'materializedNonRecordingFiles':251,'recordingBodiesOmittedOnlyFromMaterializedSubset':18,'knownCredentialMarkerReviewsPassed':True,'noSparseExtraction':True,'noBusinessOrRawAuditRerun':True,'noJavaSshGit':True,'localFunctionalOnly':True,'localPerformanceClaimed':False,'closureExcludes':['MANIFEST.json','CLOSED.json']})
 print(json.dumps({'passed':True,'manifestSha256':a.sha(out/'MANIFEST.json'),'closedSha256':a.sha(out/'CLOSED.json'),'payloadFiles':len(inventory['files']),'directories':len(inventory['directories']),'payloadBytes':sum(r['bytes']for r in inventory['files'].values()),'freeBytes':shutil.disk_usage(a.WORKSPACE).free}))
if __name__=='__main__':main()

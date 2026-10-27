#!/usr/bin/env python3
"""Build a diagnostic-only Aeron 1.53.3 overlay with exact-source, additive trace hooks."""
from pathlib import Path
import argparse,urllib.request,hashlib,json,subprocess,difflib

SOURCES={
 'ConsensusModuleAgent.java':('aeron-cluster/src/main/java/io/aeron/cluster/','f5dd4a0f4e3bb57cc7022e0ea1038171cb8c71d87f3b6d725cce2e6a677bf743'),
 'LogPublisher.java':('aeron-cluster/src/main/java/io/aeron/cluster/','31ba0139a3880aa8a34c28cf6c4de6bd817502463ba683565cd04c1713a30bd8'),
 'RecordingSession.java':('aeron-archive/src/main/java/io/aeron/archive/','b447c6102219a62cf17b5b102fe7fa09f14c31d4450be5da583077533b7b0a73'),
 'RecordingWriter.java':('aeron-archive/src/main/java/io/aeron/archive/','d86b3cefbc41fc1e115ba5354423add7cade8cfb5a759041d7b91177cb259a50')}
def once(s,old,new):
 assert s.count(old)==1,(old[:100],s.count(old));return s.replace(old,new)
def patch(name,s,preallocation=False):
 assert '\nimport io.aeron.' in s
 s=s.replace('\nimport io.aeron.','\nimport io.vectormatch.cluster.StageTrace;\nimport io.aeron.',1)
 if name=='LogPublisher.java':
  a=s.index('    long appendMessage(');b=s.index('\n    }\n',a)+7;part=s[a:b]
  part=once(part,'        sessionHeaderEncoder\n','        final long traceStart = StageTrace.ENABLED ? StageTrace.clock() : 0;\n        sessionHeaderEncoder\n')
  part=once(part,'        return position;','        if (StageTrace.ENABLED) StageTrace.event(StageTrace.APPEND, traceStart, StageTrace.clock(), clusterSessionId, StageTrace.correlation(buffer, offset, length), position, publication.sessionId());\n        return position;');s=s[:a]+part+s[b:]
 elif name=='ConsensusModuleAgent.java':
  a=s.index('    ControlledFragmentAssembler.Action onIngressMessage(');b=s.index('\n    void onSessionKeepAlive',a);part=s[a:b]
  part=once(part,'\n    {\n','\n    {\n        if (StageTrace.ENABLED) StageTrace.point(StageTrace.INGRESS, clusterSessionId, StageTrace.correlation(buffer, offset, length), leadershipTermId, memberId);\n');s=s[:a]+part+s[b:]
  old='''    void updateMemberLogPosition(final ClusterMember member, final long leadershipTermId, final long logPosition)
    {'''
  s=once(s,old,old+'\n        if (StageTrace.ENABLED) StageTrace.point(StageTrace.ACK, member.id(), leadershipTermId, logPosition, 0);')
  s=once(s,'            commitPosition.proposeMaxRelease(quorumPosition);','''            final long traceCommit = StageTrace.ENABLED ? StageTrace.clock() : 0;
            commitPosition.proposeMaxRelease(quorumPosition);
            if (StageTrace.ENABLED) StageTrace.event(StageTrace.COMMIT, traceCommit, StageTrace.clock(), memberId, leadershipTermId, quorumPosition, appendPosition);''')
 elif name=='RecordingWriter.java':
  a=s.index('    public void onBlock(');b=s.index('\n    /**',a);part=s[a:b]
  part=once(part,'\n    {\n','\n    {\n        final long traceStart = StageTrace.ENABLED ? StageTrace.clock() : 0;\n        final long tracePosition = position();\n')
  part=once(part,'            if (forceWrites)\n','            if (StageTrace.ENABLED) StageTrace.event(StageTrace.WRITE, traceStart, StageTrace.clock(), recordingId, sessionId, tracePosition, tracePosition + length);\n\n            if (forceWrites)\n')
  part=once(part,'                recordingFileChannel.force(forceMetadata);','''                final long traceForce = StageTrace.ENABLED ? StageTrace.clock() : 0;
                recordingFileChannel.force(forceMetadata);
                if (StageTrace.ENABLED) StageTrace.event(StageTrace.FORCE, traceForce, StageTrace.clock(), recordingId, sessionId, tracePosition, tracePosition + length);''');s=s[:a]+part+s[b:]
 elif name=='RecordingSession.java':
  s=once(s,'                this.position.setRelease(recordingWriter.position());','''                final long tracePublish = StageTrace.ENABLED ? StageTrace.clock() : 0;
                this.position.setRelease(recordingWriter.position());
                if (StageTrace.ENABLED) StageTrace.event(StageTrace.RECORDED, tracePublish, StageTrace.clock(), recordingId, image.sessionId(), recordingWriter.position(), 0);''')
 if name=='RecordingWriter.java' and preallocation:
  s=once(s,'            recordingFile.setLength(segmentLength);','''            recordingFile.setLength(segmentLength);
            if (Boolean.getBoolean("vectormatch.stage.preallocate"))
            {
                StageTrace.reserveRecording(segmentFile.getAbsolutePath(), segmentLength);
            }''')
 return s

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path);p.add_argument('--jdk',type=Path,required=True);p.add_argument('--classpath',required=True);p.add_argument('--preallocation',action='store_true');a=p.parse_args()
 a.output.mkdir(parents=True,exist_ok=False);original=a.output/'original';modified=a.output/'modified';classes=a.output/'classes'
 for d in [original,modified,classes]:d.mkdir()
 manifest={};diff=[]
 for name,(directory,digest)in SOURCES.items():
  url='https://raw.githubusercontent.com/aeron-io/aeron/1.53.3/'+directory+name
  raw=urllib.request.urlopen(url,timeout=30).read();assert hashlib.sha256(raw).hexdigest()==digest,name
  (original/name).write_bytes(raw);text=patch(name,raw.decode(),a.preallocation);(modified/name).write_text(text)
  manifest[name]={'url':url,'originalSha256':digest,'patchedSha256':hashlib.sha256(text.encode()).hexdigest()}
  diff.extend(difflib.unified_diff(raw.decode().splitlines(True),text.splitlines(True),fromfile='original/'+name,tofile='modified/'+name))
 (a.output/'instrumentation.patch').write_text(''.join(diff))
 subprocess.run([str(a.jdk/'bin/javac'),'--release','21','-cp',a.classpath,'-d',str(classes),*[str(x)for x in modified.glob('*.java')]],check=True)
 jar=a.output/'stage-patch.jar';subprocess.run([str(a.jdk/'bin/jar'),'--create','--file',str(jar),'-C',str(classes),'.'],check=True)
 (a.output/'MANIFEST.json').write_text(json.dumps({'pinnedAeron':'1.53.3','diagnosticOnly':True,'preallocationOptIn':a.preallocation,'sources':manifest,'jarSha256':hashlib.sha256(jar.read_bytes()).hexdigest()},indent=2)+'\n')
 print(json.dumps({'jar':str(jar),'sha256':hashlib.sha256(jar.read_bytes()).hexdigest()}))
if __name__=='__main__':main()

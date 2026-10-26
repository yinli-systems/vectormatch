"""Exact child argv derived from the actual qualified class origins used by the Java launcher."""
from pathlib import PurePosixPath
CLASSES=('io.vectormatch.cluster.RetentionNodeMainV3','io.vectormatch.core.MatchingEngine','io.aeron.driver.MediaDriver','org.agrona.DirectBuffer')
def child_classpath(origins,lib):
 paths={row['class']:row['path']for row in origins};ordered=[]
 for name in CLASSES:
  path=paths[name]
  if str(PurePosixPath(path).parent)!=lib or not path.endswith('.jar'):raise ValueError('class origin outside the qualified runtime')
  if path not in ordered:ordered.append(path)
 return ':'.join(ordered)
def expected_node_arguments(java,classpath,member,state,registration,profile,fingerprint,idle_max_park_ns=None):
 if type(member)is not int or member not in(0,1,2):raise ValueError('exact cluster member0..2 required')
 if registration['profile']!=profile or registration['code']!=fingerprint:raise ValueError('native profile/artifact registration differs')
 actual=registration.get('retentionIdleSelection')
 if idle_max_park_ns is None:
  if actual is not None:raise ValueError('Unexpected explicit idle selection')
 else:
  if type(idle_max_park_ns)is not int or idle_max_park_ns not in(100000,1000000):raise ValueError('Exact supported idle maximum required')
  expected=dict(schema='retention-idle-selection-v1',property='vectormatch.retention.idleMaxParkNs',maximumParkNs=idle_max_park_ns,factor='maximum requested park only')
  if actual!=expected:raise ValueError('Actual native registration differs from frozen idle selection')
 argv=[java,'--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED','--add-opens=java.base/java.util.zip=ALL-UNNAMED','-Xmx256m','-Daeron.cluster.appointed.leader.id=0','-cp',classpath,'io.vectormatch.cluster.RetentionNodeMainV3',str(member),state,str(registration['ports']),'2','finite-batch-load-v3-v1',registration['lineage'],profile,fingerprint,'bounded-maintenance-v1']
 if idle_max_park_ns is not None:argv.insert(1,'-Dvectormatch.retention.idleMaxParkNs='+str(idle_max_park_ns))
 return argv

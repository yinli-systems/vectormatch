"""Root's local worktree validation; starts no cloud node or load."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

root = Path.cwd()
out = Path(__file__).resolve().parent
files = ['cluster/src/main/java/io/vectormatch/cluster/ClusterNodeMain.java',
         'cluster/src/test/java/io/vectormatch/cluster/NodeDataPathIdlePolicyTest.java',
         'deploy/remote_service.py', 'scripts/verify-capacity-config.py',
         'scripts/tests/test_node_data_path_config.py']
before = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in files}
command = [str(root / '.tools/gradle/bin/gradle'), '--no-daemon', ':cluster:test',
           '--tests', 'io.vectormatch.cluster.NodeDataPathIdlePolicyTest']
environment = dict(os.environ)
environment.update(JAVA_HOME=str(root / '.tools/jdk'), GRADLE_USER_HOME=str(root / '.tools/gradle-user-home'))
environment['PATH'] = str(root / '.tools/jdk/bin') + ':' + environment['PATH']
started = datetime.datetime.now(datetime.timezone.utc).isoformat()
with (out / 'node-idle-java-context.log').open('x') as log:
    result = subprocess.run(command, cwd=root, env=environment, stdout=log, stderr=subprocess.STDOUT)
suite = root / 'cluster/build/test-results/test/TEST-io.vectormatch.cluster.NodeDataPathIdlePolicyTest.xml'
counts = None
if suite.exists():
    counts = {key: int(ET.parse(suite).getroot().get(key, '0')) for key in ('tests', 'failures', 'errors', 'skipped')}
after = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in files}
passed = result.returncode == 0 and counts == {'tests': 4, 'failures': 0, 'errors': 0, 'skipped': 0} and before == after
receipt = {'passed': passed, 'command': command, 'startedAtUtc': started,
           'completedAtUtc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
           'exitCode': result.returncode, 'counts': counts, 'sourceSha256': before,
           'sourcesUnchanged': before == after,
           'scope': 'Four pure Java context/instance/default-policy tests in local worktree; no cloud or throughput assertion.'}
with (out / 'node-idle-java-context.json').open('x') as stream:
    json.dump(receipt, stream, indent=2)
    stream.write('\n')
print(json.dumps(receipt), flush=True)
raise SystemExit(0 if passed else 1)

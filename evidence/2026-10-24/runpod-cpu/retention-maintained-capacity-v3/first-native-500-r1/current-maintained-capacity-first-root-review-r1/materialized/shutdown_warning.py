"""Pure, deliberately narrow candidate classification for this fresh single-arm pilot.

It never changes native results or authorizes a later run. Caller must separately
prove all functional/raw/archive/owned-stop gates. Line order is not signal time.
"""
import hashlib
import json
import re

MAX_LOG_BYTES = 4 * 1024**2
EVENT_LINE = 'io.aeron.cluster.client.ClusterEvent: WARN - log recording stopped: eos=true'


def require(value, message):
    if not value:
        raise ValueError(message)


def classify(data, *, node, pid, profile, lineage, code, final_hash, idle_actual, ports=42000):
    require(isinstance(data, bytes) and 0 < len(data) <= MAX_LOG_BYTES, 'Bounded nonempty original node log required')
    require(type(node) is int and node in [0, 1, 2] and type(pid) is int and pid > 1, 'Exact original node identity required')
    require(all(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value)
                for value in [profile, code, final_hash]), 'Exact code/profile/final snapshot SHA required')
    require(isinstance(lineage, str) and 1 <= len(lineage.encode('utf8')) <= 64
            and '\n' not in lineage and '\r' not in lineage, 'Bounded exact lineage required')
    require(ports == 42000, 'This candidate scope is the fixed42000 fresh pilot')
    text = data.decode('utf8', 'strict'); lines = text.splitlines()
    require(data.endswith(b'\n') and len(lines) <= 256, 'Complete bounded original log lines required')
    members = '|'.join(str(n) + ',' + ','.join('127.0.0.1:' + str(ports+n*100+o)
                       for o in [2, 3, 4, 5, 1]) for n in range(3))
    ready = ('VECTOR_V3_NODE_READY node=%d pid=%d profile=%s lineage=%s code=%s members=%s '
             'sync=2 mtu=1248 preparedArchiveCacheEnabled=true') % (node, pid, profile, lineage, code, members)
    service = re.compile(r'VECTOR_V3_SERVICE_READY profile=' + re.escape(profile)
                         + r' lineage=' + re.escape(lineage) + r' restored=false hash=[0-9a-f]{64}')
    snapshot = re.compile(r'VECTOR_V3_SNAPSHOT_WRITTEN profile=' + re.escape(profile)
                          + r' lineage=' + re.escape(lineage) + r' hash=' + re.escape(final_hash)
                          + r' bytes=[1-9][0-9]*')
    checkpoints = [i for i, line in enumerate(lines) if snapshot.fullmatch(line)]
    require(len(checkpoints) == 1, 'Exactly one matching final profile/lineage/hash checkpoint required')
    checkpoint = checkpoints[0]
    seen = {'ready': 0, 'service': 0, 'idle': 0, 'leader': 0}
    warnings = []; i = 0
    byte_offsets = []; total = 0
    for raw_line in data.splitlines(keepends=True):
        byte_offsets.append(total); total += len(raw_line)
    while i < len(lines):
        line = lines[i]
        if line == ready:
            seen['ready'] += 1
        elif service.fullmatch(line):
            seen['service'] += 1
        elif line.startswith('VECTOR_V3_IDLE_ATTESTATION '):
            value = json.loads(line[len('VECTOR_V3_IDLE_ATTESTATION '):])
            require(value == idle_actual and value['node'] == node and value['pid'] == pid,
                    'Exact separately validated actual idle artifact/log binding differs')
            seen['idle'] += 1
        elif snapshot.fullmatch(line):
            pass
        elif node == 0 and line == 'VECTOR_V3_ROLE role=LEADER' and i < checkpoint:
            seen['leader'] += 1
        elif line == 'VECTOR_V3_ERROR node=' + str(node):
            require(node in [1, 2] and i > checkpoint and not warnings,
                    'Only one follower EOS warning pair after matching checkpoint is a candidate')
            require(i + 1 < len(lines) and lines[i+1] == EVENT_LINE and i + 2 == len(lines),
                    'Exact terminal two-line ClusterEvent WARN EOS pair required; no exception/extra warning tail')
            start = byte_offsets[i]; payload = data[start:]
            warnings.append({'node': node, 'markerLine1Based': i+1, 'eventLine1Based': i+2,
                'matchingCheckpointLine1Based': checkpoint+1, 'byteOffset': start,
                'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest(),
                'marker': line, 'event': lines[i+1],
                'phase': 'AFTER_MATCHING_FINAL_CHECKPOINT_BY_NODE_LOG_ORDER',
                'afterSigtermWallTimeProven': False, 'underlyingCategory': 'WARN',
                'sourceEventCanInitiateElection': True})
            i += 1
        else:
            raise ValueError('Unclassified line%d retained as failure: %s' % (i+1, line[:512]))
        i += 1
    require(seen == {'ready': 1, 'service': 1, 'idle': 1, 'leader': int(node == 0)},
            'Fresh fixed-leader single-launch log closure differs')
    return {'candidateClassification': ('POST_CHECKPOINT_FOLLOWER_EOS_WARN' if warnings else 'NO_LOG_WARNINGS'),
            'node': node, 'pid': pid, 'logBytes': len(data), 'logSha256': hashlib.sha256(data).hexdigest(),
            'lineCount': len(lines), 'matchingFinalCheckpointLine1Based': checkpoint+1,
            'warningPairs': warnings, 'warningPairCount': len(warnings),
            'allLogLinesClassifiedAndRetained': True,
            'originalStrictWrapperResultChanged': False, 'rawFunctionalGatePerformedHere': False,
            'nextRunAuthorized': False, 'afterSigtermWallTimeProven': False}

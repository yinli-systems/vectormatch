"""Explicit closed arm archive contract; no IO or benchmark calculations."""
SOURCE='d92301d3058acc83cb85d5bc5b4fd2e3f0ed4df8'
CODE='87a7ccd092f4d3c890bf8cc8bd7c6ffcd18900838699cd2b873fd1931cddb6aa'
RELEASE='0ebad5d1ae1bd7900fc6dad7d78994d11ec3281f4077cfb7eba9b1bb3f506d59'
CONTROLLER='eb84eed09cad46c5097c32d980a1629f7c7c7fec3759e904544f7ef9e91e3100'
CLOSE='67fcfe5bd15efb8bdc488d25b156534b34878ce6584e5cb2ec3cf95ebeb2b5f2'
PAGES=(16,32,16,32)

def need(ok,message):
    if not ok:raise AssertionError(message)

def selected_page(arm):
    need(type(arm)is int and arm in (2,3,4),'Explicit closed arm2..4 only')
    return PAGES[arm-1]

def hexsha(value):
    return isinstance(value,str)and len(value)==64 and all(c in '0123456789abcdef'for c in value)

def validate_identity(plan):
    page=selected_page(plan['arm'])
    need(plan['schemaVersion']==2 and plan['eventFetchCount']==page and plan['sourceCommit']==SOURCE
         and plan['codeFingerprint']==CODE and plan['releaseSha256']==RELEASE and plan['controllerSha256']==CONTROLLER
         and plan['closeProbeSha256']==CLOSE and hexsha(plan['rootReviewSha256']),'Exact same new artifact and explicit selected arm/page')
    return page

def render_readme(plan,review,collection_inventory,probes):
    arm=plan['arm'];page=selected_page(arm);m=review['arms'][0]
    count=len(collection_inventory['files']);size=sum(r['bytes']for r in collection_inventory['files'].values())
    observations=', '.join(row['scope']+'='+str(row['state']) for row in probes)
    return f'''# Closed Event Fetch arm{arm}, page{page} evidence

One finite one-host loopback LONG lineage:33792 scheduled arrivals at500/s over67.584s,12maintenance cycles/24read phases. Source{SOURCE}/actualcode{CODE}, controller{CONTROLLER}, release{RELEASE}; selected page{page}, fixedowner maximumpark1000000ns/server-driver100000ns, read8/businesscap4/chunk6144/leader0term0/sync2. Configured maximumpark is not actual OS sleep duration or a hard realtime guarantee.

The actual independent root receipt reports all-arrival scheduled-to-reply nearest-rankp99 {m['allArrivalP99Ns']}ns, acceptedwithinarrivalwindow{m['acceptedWithinArrivalWindow']}, windowgoodput{m['arrivalWindowGoodputPerSecond']}/s, summed maintenancecyclewall{m['maintenanceCycleWallNs']}ns, offeredhighwater{m['offeredHighWater']}, retainedWARNpairs{m['retainedPostCheckpointEosWarningPairs']}. These are copied receipt values, not recomputation. This finite arm alone is not a16/32speedup, sustainedcapacity, upperbound, zero-latency or100M proof and does not start/authorize anotherarm. Matching threecheckpointlogs is not independent binarysnapshot-record decoding.

Entire original current collection ({count}files/{size}bytes) is copied without exclusions: completeouter+innerTARs, every tape/CSV/writer/reference, source/auditor/config/receipt/error, actualstagedsource/JAR/proof rows insidefullouter and materialized runtimeJARs. Root verified{review['outerFiles']}outerfiles/{review['outerDirectories']}directories/{review['outerLogicalBytes']}logicalbytes/{review['rawInputFiles']}rawinputs. Original remoteTAR metadata remains in its originalmanifest; localcopiedfile UID/GID is separately recorded.

All actual current launch/config/collection/rootexecution and closedgate records are retained. Exactly{len(probes)}actuallyexistingcloseattempts are copied: {observations}. No missingACTIVE attempt is invented. Failed/nonJSON probe stdout is preserved without treating it as successful; the actual rootclosedgate must bind a real CLOSED_PASS_CONTROL_PLANE observation. Historical source-generation fields and failures remain unchanged.

The explicit continuation scopes preserve actual precedingarm priorpair/freeze/upload/executions, private visibility and Gitblob readback, plus new helper/source/guard and independent archive-review failures/successes. Firstinline/AST preparation or wrapper failures retain only artifacts that actually existed; missing invaliddrafts or rawstderr are never fabricated. Only capture.py is copied from the generic execution helper directory. Shared deployment and prior helper provenance archives are referenced by exactINVENTORY/CLOSED; fullactualstagedrows and allpriorpairs remain inside this arm's outerTAR.

AllsourceSHA/size/mode/uid/gid/emptydirectory before/after and recursive rawfile/TAR/ZIP/JAR/tape knownmarker scans are retained. Large native.rec leaves stream in boundedmemory with no nativeextraction. Namedmarker scans are bounded, not universal secretabsence. No business/auditor/collector/test/JVM/Gradle/SSH/network/Git rerun, launch/signals/resources/cleanup/deletion occurred. Original absolute paths remain intact; portablebindings map them to copiedbodies or exactsharedreceipts. INVENTORY excludes onlyitself andCLOSED; CLOSED bindsit.
'''

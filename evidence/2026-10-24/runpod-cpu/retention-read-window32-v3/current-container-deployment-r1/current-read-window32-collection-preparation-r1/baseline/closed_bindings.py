"""Explicit remote-archive metadata to materialized-local file bindings, never an owner substitution claim."""
import hashlib
import os
from pathlib import Path,PurePosixPath
import stat
from common import require,sha

TAPES={'job/idle-arm/load/'+name for name in ('physical-requests.bin','physical-replies.bin','maintenance/logical-rpc-requests.bin','maintenance/logical-rpc-replies.bin')}


def materialize(name,size,plan,*,allow_tapes=True):
    require(plan['maximumRawTraceBytes']==182433396,'Exact actual-JAR long trace bound required')
    if name in TAPES:
        return allow_tapes and 0<=size<=plan['maximumRawTraceBytes']
    return size<=32*1024**2 and not name.endswith(('.rec','.dat','.catalog','.jar','.class','.gz','.zip'))


def validate_tape_budget(files,plan):
    require(plan['maximumRawTraceBytes']==182433396,'Exact actual-JAR long trace bound required')
    total=sum(row['bytes']for name,row in files.items()if name in TAPES)
    return {'passed':total<=plan['maximumRawTraceBytes'],'totalOriginalTapeBytes':total,
        'materializationLimitBytes':plan['maximumRawTraceBytes'],
        'failurePolicy':'If exceeded, retain complete outer/nested TAR payloads and metadata; do not truncate or materialize overbudget tapes; strict raw audit must fail diagnostics-only.'}


def project(collection,outer,receipt,native_report):
    require(receipt['passed']is True and receipt['allOuterFileFullShaSizeModeOwnerAndEmptyDirClosureVerified']is True
        and sha(collection/'remote-inventory.stdout.json')==receipt['outerInventorySha256'],'Verified exact full outer manifest required')
    require(receipt['rawTapeMaterializationBudget']['passed']is True,'Overbudget original tapes retained in full TAR; strict raw admission refused')
    require(native_report['passed']is True and native_report['allNestedFullShaBytesModeOwnerAndEmptyDirClosureVerified']is True
        and native_report['allNestedFilesExactlyBoundToOuterArchive']is True,'Verified full nested mode/owner closure required')
    projected={};bindings={}
    for name,original in outer['files'].items():
        rel=PurePosixPath(name)
        require(str(rel)==name and not rel.is_absolute()and'..'not in rel.parts,'Unsafe original manifest path')
        path=collection/'raw-files'/name
        if not path.exists():continue
        require(not any(p.is_symlink()for p in [path]+list(path.parents)),'Materialized symlink ancestor refused')
        st=path.lstat();require(stat.S_ISREG(st.st_mode)and st.st_nlink==1 and st.st_uid==os.geteuid(),'Materialized input must be an exclusively owned regular local file')
        require(st.st_size==original['bytes']and sha(path)==original['sha256'],'Materialized input differs from verified original payload')
        local={'mode':stat.S_IMODE(st.st_mode),'uid':st.st_uid,'gid':st.st_gid}
        key='raw-files/'+name
        projected[key]={'bytes':original['bytes'],'sha256':original['sha256'],**local}
        bindings[key]={'originalArchiveMetadata':{k:original[k]for k in ('bytes','sha256','mode','uid','gid')},'materializedLocalMetadata':local,
            'payloadExact':True,'archiveOwnerIsNotLocalOwnerClaim':True}
    require(projected,'No verified materialized parser inputs')
    return projected,bindings

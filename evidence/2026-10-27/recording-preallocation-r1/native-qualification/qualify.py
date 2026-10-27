from pathlib import Path
import subprocess,base64,hashlib,json,os,ctypes,time,shutil
p=Path('/opt/vectormatch-cpu/experiments/recording-preallocation-build-20261027-r1')
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='8d765c71-dbfa-4354-8db0-6c392e701e6f'
for f in Path('/proc').glob('[0-9]*/comm'):
 try:assert f.read_text().strip()!='java'
 except(FileNotFoundError,ProcessLookupError):pass
def digest(file):
 h=hashlib.sha256()
 with file.open('rb')as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
size=128*1024*1024;first=p/'qualification.rec'
assert first.stat().st_size==size+1
failure={'reason':'First allocation preflight used size-15 for a 16-byte tail sentinel and its final size assertion correctly failed. No trading workload ran. The original file is retained.','originalSize':first.stat().st_size,'originalSha256':digest(first),'dataRecipe':'128 MiB zero file, 16-byte VECTORMATCH-HEAD at 0 and 16-byte VECTORMATCH-TAIL at size-15, yielding size+1.'}
(p/'FIRST_QUALIFICATION_FAILURE.json').open('x').write(json.dumps(failure,indent=2))
file=p/'qualification-r2.rec';fd=os.open(file,os.O_RDWR|os.O_CREAT|os.O_EXCL,0o600);os.ftruncate(fd,size)
head=b'VECTORMATCH-HEAD';tail=b'VECTORMATCH-TAIL'
os.pwrite(fd,head,0);os.pwrite(fd,tail,size-len(tail));os.fsync(fd)
before=os.fstat(fd);shaBefore=digest(file);assert before.st_size==size
libc=ctypes.CDLL(None,use_errno=True);libc.fallocate.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_longlong,ctypes.c_longlong];libc.fallocate.restype=ctypes.c_int
start=time.monotonic_ns();rc=libc.fallocate(fd,1,0,size);duration=time.monotonic_ns()-start;assert rc==0,ctypes.get_errno()
os.fsync(fd);after=os.fstat(fd);os.close(fd);shaAfter=digest(file)
assert before.st_size==after.st_size==size and before.st_ino==after.st_ino and shaBefore==shaAfter and after.st_blocks*512>=size
lib=(p/'libvmclock.so').read_bytes();jdk=Path('/opt/vectormatch-cpu/experiments/soak-20261026-r1/tools/jdk-21.0.13+9')
cmd=['gcc','-O2','-fPIC','-shared','-Wall','-Wextra','-Werror','-I'+str(jdk/'include'),'-I'+str(jdk/'include/linux'),str(p/'clock.c'),'-o',str(p/'libvmclock.so')]
proof={'sourceSha256':digest(p/'clock.c'),'librarySha256':hashlib.sha256(lib).hexdigest(),'command':cmd,'compiler':subprocess.check_output(['gcc','--version'],text=True).splitlines()[0],'boot':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'timeNamespace':os.readlink('/proc/self/ns/time'),'noJavaBeforeQualification':True,'originalFailure':failure,'qualification':{'file':str(file),'logicalBytes':size,'allocatedBeforeBytes':before.st_blocks*512,'allocatedAfterBytes':after.st_blocks*512,'sha256Before':shaBefore,'sha256After':shaAfter,'fallocateDurationNs':duration,'keepSizeFlag':1,'dataRecipe':'128 MiB zero file; 16-byte VECTORMATCH-HEAD at 0; 16-byte VECTORMATCH-TAIL at size-16','freeAfterBytes':shutil.disk_usage('/').free}}
(p/'BUILD.json').open('x').write(json.dumps(proof,indent=2))
print(json.dumps({'proof':proof,'libraryBase64':base64.b64encode(lib).decode()}))

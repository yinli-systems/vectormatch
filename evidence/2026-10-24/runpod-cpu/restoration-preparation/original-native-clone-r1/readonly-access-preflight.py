import pathlib,platform,shutil,subprocess,json,stat
assert platform.node()=='ed6c0673f5cb'
pg=pathlib.Path('/opt/vectormatch-cpu/restorations/original-native-r1/node2/runtime/postgres18')
paths=[pg]+list(pg.parents)
metadata=[{'path':str(p),'uid':p.stat().st_uid,'gid':p.stat().st_gid,'mode':oct(stat.S_IMODE(p.stat().st_mode)),'symlink':p.is_symlink()} for p in paths]
commands={name:shutil.which(name) for name in ('getfacl','setfacl','getent','runuser','setpriv','useradd','groupadd')}
users={}
for name in ('vectormatch-pg','postgres'):
 r=subprocess.run(['/usr/bin/getent','passwd',name],capture_output=True,text=True,timeout=5);users[name]={'exitCode':r.returncode,'entry':r.stdout.strip()}
out={'hostname':platform.node(),'readOnly':True,'ancestors':metadata,'tools':commands,'users':users,'databaseServerStarted':False}
print(json.dumps(out))

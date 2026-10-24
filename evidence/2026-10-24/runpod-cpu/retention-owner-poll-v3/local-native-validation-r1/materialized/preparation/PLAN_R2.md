# Derived capture/audit R2 compatibility repair

The already-closed native pair is not rerun. Python3.9 rejected compresslevel on streaming tar mode before any native body was archived. The original two failed closure files remain untouched and are included under prior-derived-failures/capture-r1, outside the native/ business namespace. Every closed-originals* top-level path is excluded from native/.

R2 uses gzip.GzipFile(compresslevel=1) around tarfile mode w|. The compressed256MiB, logical8GiB,4096-entry limits and streaming full SHA/mode/uid/gid/empty-directory readback remain unchanged. Existing25 sources and both original freezes remain exact. Original4 runtime helpers/config and all SHORT/LONG parser bodies are unchanged. R2 source and complete guard attempts are captured as inputs. New closure closed-originals-r2 and audit sibling owner-poll-native-raw-audit-r2 preserve every previous attempt.

Three new real temporary-fixture tests cover stream roundtrip, SHA/mode/owner/empty directories, all closure exclusions and separate failure preservation, compressed cap/partial preservation/no overwrite. They do not open native business data or launch any process. Historical14+4 guard results remain preserved as historical proof; tests of unchanged adapter bindings continue to refer to the original adapter bytes, with R2 adapter changed only for output/closure/freeze path literals.

Local pair remains functional only: A scheduler valid, B40 late/invalid; no local performance claim. No new UNKNOWN failure injection or business replay. CPU uses strict LONG parser separately.

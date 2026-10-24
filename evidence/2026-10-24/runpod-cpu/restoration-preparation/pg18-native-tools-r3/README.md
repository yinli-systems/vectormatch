# CPU-native PostgreSQL18.6 inspection tools

Only pg_controldata and pg_config were built from the pinned official18.6 source on the existing CPU. All native commands succeeded and their owned process groups were empty afterward;exact generated8KiB block/WAL,1GiB segment,64bit alignment andPG_CONTROL_VERSION1800 were checked. Output ELF/version/SHA and complete logs are retained. pg_config describes this new tool build,not the originalZonky server.

The r1 build failed because PostgreSQL18 requires a library argument for explicit --with-ssl;omitting the option uses its defaultno. The r2 configure passed but leaf -j2 compilation raced generated utils/errcodes.h. r3 explicitly completes src/backend generated-headers before either leaf. Both original failed directories/logs remain;no attempt identity was reused.20localguards pass for the correctedbuilder.

Build dependencies bison/flex/m4/libsigsegv2 were pinned and installed without upgrades/removals. The firstpostinstall assertion rejected architecture-qualified libsigsegv2:amd64;allinstallcommands had succeeded. A distinct read-only Package/Version/Architecture query verified all4 without reinstalling. See ../pg18-dependencies-r1.

No PGDATA,initdb,PostgreSQL server or original application was started. Binary readiness is not database recovery or lineage validation.

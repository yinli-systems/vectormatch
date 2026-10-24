# 原应用迁移至 CPU：进展与恢复计划（业务恢复尚未验收）

准备进展：原e1db源的85路径应用包已同源重建；固定Linux PostgreSQL18.6制品已在CPU上通过file/readelf/ldd及`postgres --version`。收据在[恢复准备](../evidence/2026-10-24/runpod-cpu/restoration-preparation/root-scope.json)和[实际加载探针](../evidence/2026-10-24/runpod-cpu/restoration-preparation/loader-probe-r1/receipt.json)。此减缩PG制品没有`pg_controldata`/`pg_config`，已另行原生构建两工具。数据库已完成一次实际启动及正常关闭，但只读审计停在首个设置断言；原集群、gateway与projector仍未启动，业务恢复尚未完成。

隔离原生副本已实际恢复到`/opt/vectormatch-cpu/restorations/original-native-r1`：三份固定SHA备份的1041文件、3,701,302,583逻辑字节全部通过源内容及完整恢复文件SHA校验；初始稀疏分配93,749,248字节。原备份保留。随后只将已完整验证的PGDATA迁移到专用963:963，并对五个固定父目录授予该UID执行权限；[访问准备证据](../evidence/2026-10-24/runpod-cpu/restoration-preparation/pg-access-r1/README.md)记录全部前后置检查及一次局部失败。只读`pg_controldata18.6`验证控制版本1800、原数据库systemId7699920832388303129和`shut down`，检查前后关键SHA不变。[完整副本和控制检查证据](../evidence/2026-10-24/runpod-cpu/restoration-preparation/original-native-clone-r1/README.md)。

第一次PG-only实际探针已启动原物理库，随后定向SIGINT正常关闭。JDBC事务实际只读，但readOnlyMode=always在切换autocommit时将会话默认只读设置改为off，触发首个检查断言；本次未验证ledger或cursor。原始失败、完整停止态副本及物理差异在[首次探针证据](../evidence/2026-10-24/runpod-cpu/restoration-preparation/pg-readonly-r1/README.md)。PG启动产生预期内部写入，当前989文件的派生基线另存，不能再要求它逐字节等于启动前备份。

另已完整离线解码三份原备份的最新service checkpoint，canonical及outbox字节全相等：command4539/event6106/market6086/exported6106/pending0。[离线证明及在线恢复计划](../evidence/2026-10-24/runpod-cpu/restoration-preparation/original-cluster-probe-preparation-r1/RESTORATION_PROBE_PLAN.md)区分了checkpoint、尾部重放和leader回复；它不证明CPU上三节点已恢复。locale、数据库内容/cursor与source lineage、三节点恢复、HTTP及WS仍未验收。

新增准备：固定官方18.6源码的两个工具已在CPU原生构建成功，20项离线守卫及每个原生命令/输出版本/格式宏检查通过；[r3证据](../evidence/2026-10-24/runpod-cpu/restoration-preparation/pg18-native-tools-r3/README.md)保留源码/二进制SHA、全部日志和前两次失败的原因。`pg_config`描述此次工具构建，不描述原Zonky服务器。依赖安装没有升级/移除既有包，未启动数据库。源码来源在[工具准备](../evidence/2026-10-24/runpod-cpu/restoration-preparation/pg18-tools-source/README.md)。无损稀疏解包器此前已在空闲CPU通过10项微型合成文件测试，含实际Linux稀疏分配与完整字节读回；[Linux守卫](../evidence/2026-10-24/runpod-cpu/restoration-preparation/sparse-native-guards-r1/receipt.json)和本次完整副本检查分开保留。它们不是运行中数据库或业务恢复证明。

此文是已核验备份和源码后的执行计划，不是恢复成功收据。**只能在 CPU 上所有 benchmark、容量负载及其采集/归档作业结束并确认进程停止后执行**。恢复另登记唯一 job、配置、源版本和制品 SHA；不复用容量试验目录或控制器，不修改原始备份与既有证据。CPU 仍是同一台主机上的三个 JVM，不能称为三台独立机器或跨机网络恢复。

## 备份与版本基线

本地新鲜备份位于 `runtime/cloud/optimization-20261024/gpu-to-cpu/backups/`。停机状态与逐文件 SHA 收据为 `evidence/2026-10-23/runpod-optimization/gpu-to-cpu/migration-backups.json`，时间 `2026-10-24T01:27:15.873985+00:00`。原收据已证明压缩包解压后的每个文件与已停机源一致；**尚未证明它们能在 CPU 上冷恢复**。

| 原始压缩包 | SHA-256 |
|---|---|
| `node0-original-state.tar.gz` | `066c3b54a445e16461115f7324f6f9201d1cb4a33195246d0fab4134579a418a` |
| `node1-original-state.tar.gz` | `d3458616f0e59d8861b5ba6a073db51fe6bac7656f627d78d8ca5821fe0e180b` |
| `node2-original-state.tar.gz` | `dd04517a84ec035f0a804979cc4d45b0f67192a7729c907ba2f367f35a03105b` |

包内目录相对原 `/opt/vectormatch`：三份 `runtime/cloud-20261023-01/node-N/archive` 与 `.../cluster`；node2 另含完整 `runtime/postgres18`。没有应用/JDK/PG 工具制品、driver、进程记录或完整环境。原路径为 `/opt/vectormatch/runtime/cloud-20261023-01` 与 `/opt/vectormatch/runtime/postgres18`。

原最后验证的应用源是 **`e1db2e755a834234efb60b7a1ed291b31ce33c16`**，原 release 为 `/opt/vectormatch/releases/e1db2e755a834234efb60b7a1ed291b31ce33c16`；85 件制品清单在 `evidence/2026-10-23/runpod-egress/deployment/DEPLOYMENT.json`。`runtime/cloud/runpod-20261023/current-release.json` 与现 bundle 后来已变为容量版本 b6f，不能当作原应用版本；CPU 433 release 当前只有 cluster、supervisor、telemetry，不能当作已部署 HTTP/PG。

只读核对时，现 bundle 与原清单 79 件相同、6 件不同：三处 cluster JAR、`web/dist/index.html`、supervisor 与其测试。未发现原 cluster JAR SHA `0e64ec28c01c8a4ed7255283295784cb57b4b00e76d55e994ba48f3e15ebae90` 的现存副本。优先找不可变原制品；否则在隔离 e1db checkout 构建 `:cluster:installDist :server:installDist :projector:installDist`，按该版本锁文件运行 web 的 `npm ci`/`npm run build`，登记新制品 SHA、依赖与构建来源，明确这是同源重建，不声称二进制原样恢复。

## 存储和停止前置

三包合计逻辑文件大小 **3,701,302,583 B**；Aeron 每节点有 9 个 128MiB `.rec` 文件。压缩包没有 sparse headers，普通解包会把压缩零块实分配，不能按十几 MiB 压缩大小估算 5GB 根盘需求。

恢复至独立 overlay 路径，例如 `/opt/vectormatch-cpu/restorations/<job>/`，先核验真实文件系统、剩余空间与现存容量状态占用。准备有界、拒绝绝对路径/`..`/符号链接/特殊文件的 allowlist 解包器；若恢复稀疏文件，零块 seek/truncate 后必须重读逐文件完整 SHA 和字节数，与原停机收据逐项相等。采用预先登记的空间余量和运行中磁盘 guard；空间不足则停止，不自动删除 benchmark 原生状态。`/workspace` 是 FUSE 归档位置，未经明确声明不能作为本地 NVMe 的测量存储。

原脚本部分使用 `Path.is_relative_to`、`tarfile.extractall(filter=...)`，不能原封不动在 CPU 的 Python 3.8 执行。新适配器须单独审计并登记 SHA；不得为兼容而跳过安全解包或身份验证。

## PostgreSQL 18.6 兼容性纠正与恢复

GPU 主机虽是 Ubuntu 24，**实际 PG 并不是 Ubuntu 24 编译件**。`runpod-workbench/postgres-settings.json` 明确显示 PostgreSQL 18.6、x86_64、gcc `Ubuntu 7.5.0-3ubuntu1~18.04`。`scripts/bootstrap-postgres.py` 使用 Zonky Maven 制品 `io.zonky.test.postgres:embedded-postgres-binaries-linux-amd64:18.6.0`，原 JAR SHA：

`008ee189eaa7ca2b58bd01dd950291e638b998392cf982297acd4779ec898ac1`

原安装日志显示自带 `libssl.so.1.1`、`libcrypto.so.1.1`、ICU60 等库。因此不能仅凭源主机 Ubuntu24、目标 Ubuntu20 就宣布不兼容；也不能未经运行依赖检查宣布可用。原二进制不在 fresh native 备份中，本地 `.tools/postgres/bin/postgres` 是 Mach-O，不能上传作 Linux 服务。

在 benchmark 完成后，优先核验原 Linux 制品 SHA，用 `file`/`readelf`/`ldd` 与 `postgres --version`、`pg_config` 检查目标 CPU ABI、动态库和构建配置；只读运行 `pg_controldata` 检查原 PGDATA 的 major18、system identifier、关闭状态、块大小、WAL/校验设置。若原便携二进制不兼容，可按[官方源码构建流程](https://www.postgresql.org/docs/18/install-make.html)在 Ubuntu20 编译固定 PG18.6 至独立前缀，核对数据格式相关构建参数与 ICU/locale 依赖；必要时在兼容 PG18 的独立还原副本上导出逻辑备份再恢复。当前 [PGDG Ubuntu 支持列表](https://www.postgresql.org/download/linux/ubuntu/)没有20.04，不能盲装默认 PostgreSQL 或拿 Ubuntu24 包直接覆盖。

完整 PGDATA 恢复到克隆目录，恢复 OS 用户 `vectormatch-pg` 的所有权与0700权限，服务以非 root 启动；**不得对原物理 PGDATA 执行 initdb**。保留完整 WAL、控制、提交日志与所有数据库，遵守[官方完整停机文件系统恢复约束](https://www.postgresql.org/docs/18/backup-file.html)。[同 major 的 minor 不改变内部存储格式](https://www.postgresql.org/docs/18/upgrading.html)，这不替代目标二进制/locale/依赖核验。

原配置：PG 二进制 `/opt/vectormatch/.tools/postgres/bin`；PGDATA `/opt/vectormatch/runtime/postgres18`；DB `postgres`，DB role `vectormatch`；只监听 `127.0.0.1:55432`，Unix socket `/opt/vectormatch/runtime/pg-socket`；`fsync=on`、`synchronous_commit=on`、`max_connections=30` 为原启动覆盖值。新克隆位置要显式映射，连接信息通过受控环境注入，不打印密码或完整环境。开始写入前检查数据库默认 collation 与实际库版本；若有不匹配，先重建受影响对象再 refresh，不能仅消除警告。[官方 collation 迁移约束](https://www.postgresql.org/docs/18/sql-altercollation.html)

## 三 JVM UDP 地址迁移

原成员 IP 为 `10.0.212.169`、`10.1.60.60`、`10.1.81.207`，base19000；各节点偏移100，archive/ingress/consensus/log/catchup 分别加1/2/3/4/5，因此节点0为19001–19005，节点1为19101–19105，节点2为19201–19205。CPU 恢复使用三个 `127.0.0.1`、不同端口，和容量试验 base23000 隔离。

三节点必须全停后用完整克隆，保留 member ID0/1/2、所有 archive recordings/catalog、`recording.log`、`node-state.dat`，不把空集群播种冒充恢复。旧 mark 文件和 catalog 含原地址；旧客户端 session 的 response channel 也可能持久化。**旧地址字符串存在不等于活动成员配置仍旧**：[固定 Aeron1.53.3源码](https://github.com/aeron-io/aeron/blob/1.53.3/aeron-cluster/src/main/java/io/aeron/cluster/ConsensusModuleAgent.java)的 activeMembers 来自 `ctx.clusterMembers()`。全停迁移与保留原始记录后，仍必须实际验证恢复行为，不能靠这一点推定成功。[官方备份/成员恢复说明](https://aeron.io/docs/aeron-cluster/cluster-backup/)

原 remote supervisor 要求三个 distinct IP；CPU capacity_v2 的 adapter 只允许 node，不能直接用来启动 gateway/projector。新建单独、明确声明 single-host scope 的**三角色** adapter：只允许 `127.0.0.1,127.0.0.1,127.0.0.1`、egress127、MTU1248、固定端口和指定克隆目录；拒绝 mixed/remote/未声明输入。在同进程 import 已固定 SHA 的 supervisor，仅适配 network builder，保持其他启动参数、配置指纹、PID/startTicks/argvSHA 身份逻辑。CPU Python3.8 停止进程沿用已实测的 pidfd syscall434/424兼容，不降级为裸 PID kill。

先仅启动三 node，保存每个真实 PID/参数/配置；检查官方 `ClusterTool` 的 `recording-log`、`recovery-plan`、`describe`、`list-members`、`errors` 与启动日志。活动 membership、consensus、log、catchup、archive 和新 client egress 必须全部证实为预期 loopback端点；固定 ID、term、恢复位置和三节点权威 canonical hash/command/event/outbox/exported 水位要一致。若活动目标仍指向旧 IP，**fail closed** 保存日志并停确切 owned 进程；不 hex 改 catalog、不删 recording.log、不盲目失效快照。仅在克隆上对已证明是运行期元数据的 mark 文件作有依据处理。旧 client session 允许过期，新 gateway/projector 必须新建连接。[ClusterTool 官方使用说明](https://aeron.io/docs/aeron-cluster/operating-aeron-cluster/)

## PG lineage、HTTP 与行情验收

先在 gateway 未启动时冻结原 cluster 的恢复基线，再启动 PG 并只读核对 `VM_CLUSTER_ID=runpod-cloud-20261023-01` 的 cursor、event/market最大序号、事件/成交数量、payload SHA 与 canonical source 的一致性。PG cursor 落后时只有 source outbox 仍保留所需事件才能追平；如果 source 的 exportedSeq 已超过 PG cursor，原 ReliableProjector 会拒绝并要求匹配的数据库 lineage。不得强置 cursor、改 clusterId、重建空库或跳过 gap/conflict 校验来制造成功。确认完整 lineage 后再启动 projector `watch` 并追平。

原 gateway 绑定 **127.0.0.1:8000**；8011 是本地 tunnel/代理入口。原静态资源配置 `VECTOR_WEB_DIR=/opt/vectormatch/web/dist`，新恢复必须指向该 e1db release 对应 web/dist。gateway/projector 均配置同一固定 clusterId、base19000、loopback egress；先禁人工操作与自动流量。

**原 Workbench 的 flowEnabled 默认 true，停前的 false 不持久化。**构造后每100ms tick，初始化还会按稳定 identity 重放 bootstrap命令。因此原样启动不能保证 tip 零新增。先保存恢复基线，gateway 可访问后立即显式 POST `/api/control/flow` 为 false，并记录启动期间可能产生的合成 flow 命令；若要求严格零新增，须另做并审计默认禁 flow 的启动选项，登记其独立源版本，不把它说成原二进制。

验收保存 `/api/state`、`/api/health`、`/api/metrics`、`/api/control/replay` 一致性结果；验证 HTTP place、相同 identity 重试、冲突 payload、cancel、余额恢复及 PG cursor 追平。可使用 `scripts/verify-replicated-workbench.py http://127.0.0.1:8000 <独立新输出目录>`，**不传旧三独立 IP deployment manifest**；默认验证器会诚实声明同一主机和功能 smoke，不冒称容量测量。WebSocket `/ws` 检查初始快照、更新序号、断线重连和镜像/投影 freshness。原产品是 **5Hz 全量 state snapshot**，不是逐事件行情分发；恢复功能 smoke 不证明行情带宽、持续吞吐或端到端延迟。

可参考最后已验证历史 checkpoint（`runpod-egress/final-release-verification.json`，2026-10-23 18:35）：core command4539/event6106/market6086，PG6106 events/1519 trades/lag0，state hash `4450df5dc1a6662fec3c8addd55452657ee6fd1ccd0aeae92cc6dbb7e18c780b`。**这不是 fresh物理备份 tip 的独立证明**；最终必须以实际恢复的原始 canonical 与 PG 状态核验，不能硬套旧的2896events/722trades等过期数字。

只有 native恢复、三节点canonical、PG lineage、HTTP幂等和WS验收全部有新收据，才能声明 CPU 应用恢复完成。

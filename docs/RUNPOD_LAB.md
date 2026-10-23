# Runpod 三节点 UDP 实验记录

2026-10-23，本项目在 Runpod `EU-RO-1` 实际创建了三个开启 Global Networking 的 GPU Pod。私网 UDP 全互连、初始撮合、修复后两轮 leader SIGKILL 和重复全 JVM 冷重启均已通过对应检查；冷重启后又完成一轮 900 个测量命令和 300 笔成交。六组原始 client/server 报告、三台身份/网络/cgroup 预检及文件 SHA-256 汇总见 [runpod-network/summary.json](../evidence/2026-10-23/runpod-network/summary.json)。[故障时间线](../evidence/2026-10-23/runpod-cluster/fault-timeline.json)完整保留初次失败、补丁和复测。随后恢复 outbox 到 PostgreSQL、HTTP 业务 smoke、三帧 WebSocket 状态及 SQL 账本连续性也分别取得通过证据。离线备份已完成；用户选择三台再保留运行 6 小时，服务已恢复，Pod 计费继续。

## 实际资源与预算

| 节点 | Pod ID / 私网地址 | 控制台 GPU | 控制台 CPU / RAM | 可见 CPU quota 上界 | 可见内存上界 | GPU + 临时盘报价 |
|---|---|---|---|---:|---:|---:|
| 0 | `aykai4bhv4zdf9` / `10.0.212.169` | RTX 2000 Ada | 6 vCPU / 31GB | 5.1 | 30,999,998,464 B | $0.240 + 约 $0.007/h |
| 1 | `9zt5cl1tpc7zt7` / `10.1.60.60` | RTX PRO 4000 | 12 vCPU / 31GB | 10.2 | 30,999,998,464 B | $0.570 + 约 $0.007/h |
| 2 | `h21wqh0s7g26bk` / `10.1.81.207` | RTX PRO 4500 | 28 vCPU / 62GB | 23.8 | 61,999,996,928 B | $0.720 + 约 $0.007/h |

三台运行报价按上述分项合计 **$1.551/h**，规划时上调为 **约 $1.56/h**。本项目总预算是 **$20**，不是账户自动停机上限。资源状态记录时，按各 Pod 估算启动时间计算的本项目累计费用约 **$1.17**，保守规划约 **$1.35**；这些是估算值，尚未与提供方账单结算，不包括其他任务或账户余额信息。用户已明确选择再保留运行 6 小时，三台均未执行 Stop，计费继续。按当前费率估计，到提醒时项目累计约 **$10.5–11**，后续配置、运行时长和实际账单仍可能影响费用。

GPU 不是撮合算法的计算资源。本轮使用这些有货的 NVIDIA GPU Pod，是为了获得已经实际验证的私网连接和 CPU 运行环境。这里的 CPU quota 是当前进程可见 cgroup 的 CPU 时间上界，不是独占物理核心，也不是持续性能保证。node 0/1 能看到 48 个宿主逻辑 CPU，node 2 能看到 112 个，但它们分别受到上述更低配额限制；隐藏的上级 cgroup 或共享调度仍可能进一步限制资源。完整解释保留在每台 `nodeN-preflight.json` 中。

三台均为 Linux x86-64，已运行 Temurin JDK `21.0.13+9`。当前每台配置 **50GB 临时 container disk**，预检看到的容量为 53,687,091,200 字节；没有挂载其他持久卷。本轮先验证同一运行 Pod 内的 Java 进程恢复，直接使用临时盘开展功能验证。根据 [Runpod 存储说明](https://docs.runpod.io/pods/storage/types)，container disk 不提供 Pod 停止或重启后的持久性保证。必须把源日志、快照、数据库和测试证据导出后再结束资源。

## 原生私网 UDP 全互连结果

[Runpod 公网端口文档](https://docs.runpod.io/pods/configuration/expose-ports)描述的公网暴露方式不支持 UDP；本次没有通过 HTTP 代理、TCP 转发或 TCP 隧道承载 Aeron 数据。三个实际 Pod 的 `podnet1` 都具有私网 IPv4 地址，接口和 peer route 报告的 MTU 均为 **1300**。本次直接在这些私网地址之间发送和接收 IPv4 UDP。

[Global Networking 官方文档](https://docs.runpod.io/pods/networking)列出 NVIDIA GPU Pods、`EU-RO-1` 和 Pod 间标称 **100 Mbps**。本次用下面的低速、有界测试验证这三台实例的实际 UDP 行为，没有测试达到该带宽的能力，也没有把它推导为其他机房、CPU Pod 或未来调度实例的保证。

测试使用 `scripts/udp-preflight.py`，工具版本 **`08729f2`**。该版本源码 SHA-256 为：

```text
6db40df778f80d99594e4af4920c76cb9895a40d6ccf56926bafbccec85abd13
```

本地该版本源码与三台 `nodeN-network.json` 中记录的脚本 SHA 全部一致。每个有向节点对使用独立 run ID 和共享随机密钥做 HMAC-SHA256 校验；校验期望源 IP/端口、序号及载荷大小。密钥不进入报告或仓库。

- 六个有向节点对，每组发送 3,000 个 request，并接收对应 echo。
- 每组依次覆盖 **96 / 512 / 1248 字节 UDP 载荷**，每种 1,000 个；配置速率为 **200 request/s**，结束后留 2 秒接收尾部响应。
- 所有探针设置 IPv4 DF；载荷字节数不含 20 字节 IPv4 和 8 字节 UDP 头。最大测试 IP 数据报为 **1276 字节**，低于 1300 MTU。
- 合计 **18,000 次 request/echo 往返、36,000 个已发送 UDP 数据报**。两端报告均为零未发送、零丢失、零重复、零乱序；逐样本返回源地址与对应 server endpoint 一致。

下表方向按照实际 **client request → server** 的绑定地址确定。原文件名 `udp-A-to-B` 中 A 是 server、B 是 client，因此不能直接把文件名当请求方向。

| 实际请求方向 | 样本数 | RTT p50 | RTT p99 | RTT 最大值 | 丢失 |
|---|---:|---:|---:|---:|---:|
| node 0 → node 1 | 3,000 | 0.650706 ms | 1.392543 ms | 4.090468 ms | 0 |
| node 0 → node 2 | 3,000 | 0.704567 ms | 1.273890 ms | 4.288653 ms | 0 |
| node 1 → node 0 | 3,000 | 0.632439 ms | 1.284368 ms | 37.712394 ms | 0 |
| node 1 → node 2 | 3,000 | 0.695269 ms | 1.255688 ms | 2.863606 ms | 0 |
| node 2 → node 0 | 3,000 | 0.627463 ms | 1.802357 ms | 39.338844 ms | 0 |
| node 2 → node 1 | 3,000 | 0.628243 ms | 1.164074 ms | 38.423991 ms | 0 |

把全部 18,000 个实际返回样本合并并重新排序后，RTT **p50 = 0.653665 ms、p99 = 1.298711 ms、p99.9 = 9.909679 ms、max = 39.338844 ms**。使用 nearest-rank 分位数；这里没有平均各方向的 p99，也没有剔除冷启动尾部样本。按载荷大小分组的全量统计和每个方向的原始样本均保存在证据中。

这是 client 单调时钟测得的应用层 echo 往返时间，包含 Python 调度和网络路径；不是单向网络延迟、撮合耗时、复制提交 RTT，也不是百万并发容量。有限样本中没有观察到丢包，不代表未来永远零丢包。

## 节点隔离证据的边界

三个 Pod ID、容器主机名和 kernel boot ID 均不同，外部 SSH 接入端点也分别建立连接。node 0/1 报告 CPU 为 AMD EPYC 7352，node 2 为 AMD EPYC 7663。上述信息是不同运行上下文的证据；它不足以证明提供方的物理反亲和或独立供电域。

本次 Pod-scoped 凭据请求自身 Pod REST 信息返回 **403**，因此没有取得提供方 `machineId`。`summary.json` 明确保留 `providerMachineIdsObtained=false` 和 `physicalAntiAffinityVerified=false`。没有找到并验证 Spread 调度承诺，不将这三个 Pod 描述成已认证的三台独占裸金属机器。

## 当前应用部署与后续验收

初始撮合基线使用 **`924ecdd`**；其分发包和源码校验清单保存在 [DEPLOYMENT.json](../evidence/2026-10-23/runpod-cluster/DEPLOYMENT.json)，初始启动记录位于同目录 `startup/`。后续恢复及冷重启采用两个明确分开的版本：**Java 不可变 release `2597bc3b849d8e042c8bbe67f0a5142580871a5b`**，以及根目录下的 **Python launcher `e1972ed1842b8d333163d8313ccfea7fd0f96dcd`**。Java release 修复新客户端 bootstrap，launcher 单独修复启动身份建立窗口；不能把只升级 Python 描述成替换了 Java 构件。部署和升级过程记录在故障时间线中，冷重启后每台 `processRecord.arguments` 记录了实际使用的不可变 release classpath。

最终 egress 修复又将 Java 构件升级到不可变 release **`e1db2e755a834234efb60b7a1ed291b31ce33c16`**，Python launcher 仍为 **`e1972ed`**；原版本和所有测试报告继续保留，升级实测见本页末节。三台使用同一有序成员列表、端口 base `19000`、sync level **2**、outbox capacity **65536**、Aeron MTU **1248**。部署根目录为 `/opt/vectormatch`，JDK 位于 `/opt/vectormatch/tools/jdk`，本代状态目录为 `/opt/vectormatch/runtime/cloud-20261023-01`。

```sh
cd /opt/vectormatch
export JAVA_HOME=/opt/vectormatch/tools/jdk
export VECTOR_DIST_ROOT=/opt/vectormatch/releases/e1db2e755a834234efb60b7a1ed291b31ce33c16/dist
export VECTOR_STATE_DIR=/opt/vectormatch/runtime/cloud-20261023-01
export VECTOR_CLUSTER_HOSTS='10.0.212.169,10.1.60.60,10.1.81.207'
export VECTOR_PORT_BASE=19000
export VECTOR_AERON_MTU_LENGTH=1248
export VECTOR_SYNC_LEVEL=2

# 在各自宿主环境运行对应编号，保留同一代持久状态目录：
bash deploy/remote-node.sh start 0  # node 0；另外两台分别为 1、2
bash deploy/remote-node.sh status 0
```

可审计的 launcher、分发包结构、pidfd 精确停止、各角色日志位置及 SSH 隧道方式见 [deploy/REMOTE.md](../deploy/REMOTE.md)。cluster client 必须设置本机可路由的 `VECTOR_CLIENT_EGRESS_HOST`；三个节点不能共用同一嵌入式 driver 目录。创建状态新代时相应更换 `VM_CLUSTER_ID`，不能用重置后的源覆盖旧 lineage。

正常业务测试已确认 **900 个 measured command、300 笔成交、1,200 lot 成交量、零业务拒绝、零 unknown timeout**；另有 2 笔 deposit 和 90 个预热 command，不计入测量。执行结果和序号逐笔与由初始 snapshot 恢复的本地 reference 比较，最终 canonical snapshot bytes、状态 hash、不变量及最后一笔同 key 重放均通过。

该次 single-inflight closed-loop 测量历时 **9.458770483 秒**，confirmed goodput 为 **95.149787 command/s**，execute RTT **p50 = 9.148866 ms、p99 = 12.361379 ms、p99.9 / max = 526.493987 ms**。900 个样本的 nearest-rank p99.9 恰好落在最大样本，不能把它当作大样本容量结论；测量期记录 902 个 accepted transport attempt，其中 2 个为重发。所有实际 RTT 均保留，没有删去这些尾部样本。goodput 的分母包含 reference 验证和记录样本的开销；RTT 计时只包围 `execute` 调用，包括自动重试。

重复全 JVM 冷重启并验证保存状态后，另一次相同规模 smoke 也通过了逐命令 reference、canonical bytes、不变量及同 key 重放检查。两次分开的运行并列保存，不合并分位数或用较快结果覆盖基线：

| 运行 | Java 版本 | 测量命令 / 成交 | goodput | RTT p50 / p99 / max | accepted resend / unknown |
|---|---|---:|---:|---|---:|
| [初始基线](../evidence/2026-10-23/runpod-cluster/runs/cloud-3nodes-01/result.json) | `924ecdd` | 900 / 300 | 95.149787 command/s | 9.148866 / 12.361379 / **526.493987 ms** | 2 / 0 |
| [冷重启后](../evidence/2026-10-23/runpod-cluster/runs/cloud-after-cold-final/result.json) | `2597bc3` | 900 / 300 | 96.849023 command/s | 9.124065 / 12.295407 / **524.124121 ms** | 2 / 0 |

冷重启后运行的测量期为 **9.292814470 秒**，同样排除 2 笔 deposit 和 90 个预热命令，成交量为 1,200 lot；902 个 accepted attempt 中有 2 个重发，另有 3 个 unaccepted offer。该次运行结束时 command/event/market 序号为 **2174 / 2896 / 2888**，hash 为 `bfbc71cfe6261ee53e90fec15c32401ed37bf4baa88e93f8bfd626aad7610f52`。这里的差异只是两次有限观察，没有同步 trace 来确定尾延迟原因，也不是容量或补丁加速结论。

负载生成器运行在 **node 2**，与一个集群成员共享资源；这不是第四台独立压测机，也没有采用 open-loop 到达模型或寻找饱和容量。节点 0/1/2 的 32 次 4KiB flush+fsync 预检分别观察到 p50 **0.101603 / 6.919250 / 2.563550 ms**，这只是有限文件同步探针，既不是磁盘容量结论，也不证明设备断电语义。

PostgreSQL 18.6 在 node 2 以非 root OS 用户、loopback 监听方式运行，已记录 `fsync=on`、`synchronous_commit=on`。网关和数据库均与该成员共享 CPU、磁盘和故障域，数据库没有配置复制或 HA。

[恢复 outbox 到 PostgreSQL 的记录](../evidence/2026-10-23/runpod-workbench/outbox-to-postgres-summary.json)确认，在启动网关的新业务前，恢复出的 1574 个 pending event 与后续冷重启后交易事件已一并投影：**cursor / eventsStored = 2896、tradesStored = 722、marketSeq = 2888、观察 lag = 0**。这些是整代数据的累计计数，包含各轮预热和业务事件，不等于某一轮 300 笔 measured trade。事务导出遵循 commit-before-ack 契约。

网关初次 HTTP 探针发生 ConnectionReset，留下的 `http-smoke/trace.json` 为空；[失败说明](../evidence/2026-10-23/runpod-workbench/http-smoke/failure.json)记录为 readiness 阶段、发送业务命令数为 0。随后 [readiness 记录](../evidence/2026-10-23/runpod-workbench/gateway-readiness.json)确认网关 UP，[重新执行的 HTTP smoke](../evidence/2026-10-23/runpod-workbench/http-smoke-ready/summary.json)验证真实 place、同 key retry、变更 payload conflict、cancel、余额恢复以及 mirror 与 replicated canonical snapshot 一致。该 smoke 本身有 **2 个新业务命令、0 笔新成交**；完成时异步数据库观察为 **cursor / eventsStored = 3300、tradesStored = 819、lag = 0**，这些仍是累计数据库状态。

[WebSocket 记录](../evidence/2026-10-23/runpod-workbench/websocket.json)确认经本地 SSH tunnel 收到连续 **3 帧 full-state snapshot**，各帧 health 为 UP、projection cursor 为 3300、观察 lag 为 0。它验证的是状态展示通路，没有验证逐事件可靠送达、推送容量或 WebSocket 延迟。

[PgAudit.java](../evidence/2026-10-23/runpod-workbench/PgAudit.java) 通过一个只读 repeatable-read JDBC 事务审计了完整 SQL 账本：[postgres-ledger.json](../evidence/2026-10-23/runpod-workbench/postgres-ledger.json)在该时点记录 **eventSeq 1..3300、非零 marketSeq 1..3286 全部连续，TRADE 行数 819 与 durable cursor/counters 一致**。这验证数据库内连续性与计数一致性，没有独立验证全部 payload 语义或与源逐事件相等。该审计与前述 HTTP 观察属于较早的 3300/819 时点，不能用后续恢复运行后的 3327/825 覆盖。

网关报告的 PostgreSQL cursor 是后台采样并缓存的观察值，lag 是最后观察到的 source high-water mark 减 durable cursor；不能将其描述成原子 source/database snapshot 或当前不可见源位置的实时度量。上述功能通过不证明 PostgreSQL HA、数据库机器故障恢复或 Pod 生命周期后的持久性。

| 验收项 | 本页写入时的状态 | 证据要求 |
|---|---|---|
| 六方向原生 UDP、DF、源地址、RTT | **PASS** | 本页引用的 21 份原始 JSON 及网络 summary |
| 三成员启动与一致配置 | **PASS** | 各节点 startup/launch record、构建与文件校验记录 |
| 正常交易与规范状态一致 | **PASS** | 初始和冷重启后分开的两次 900 measured command / 300 成交结果 |
| 外部停止 leader 后保持正确状态 | **PASS，限定进程故障模型** | 修复后两轮 SIGKILL、不同新 leader、同 key 重放和随后新交易均验证 |
| 三个 Java 进程全部重启恢复 | **PASS，限定同一运行 Pod/临时盘** | 快照、待导出 outbox、规范状态逐字节核对；修复 launcher 后重复全停/全起通过 |
| 恢复 outbox 到 PostgreSQL | **PASS，限定本次单节点数据库** | 2896 个累计事件、722 个累计成交、观察 lag 0 |
| HTTP 业务与 mirror/DB 观察 | **PASS，功能 smoke** | place / retry / conflict / cancel、余额与 canonical snapshot；观察 cursor 3300 |
| WebSocket 状态展示 | **PASS，3 帧 full-state snapshot** | SSH tunnel、health UP；没有逐事件或延迟保证 |
| SQL 账本连续性 | **PASS，该次只读事务时点** | event 1..3300、非零 market 1..3286、TRADE 819 与持久化计数一致 |
| 离线备份与清单 | **PASS，备份创建及本地校验** | 三份归档的大小、SHA-256 和路径已校验；未演练从这些副本恢复 |
| Pod 保留与计费 | **用户选择三台再运行 6 小时** | 未执行 Pod Stop；服务已恢复、合成 flow 已暂停，计费继续 |
| 最终停止 / 费用结算 | 未执行 / 未结算 | 到期仅提醒；没有自动 Stop 或清盘 |

`RemoteClusterExperiment run` 的默认计划是两笔 deposit、30 个预热 cycle、300 个测量 cycle；每 cycle 包含 maker 10 lot、IOC taker 4 lot 和撤销 maker 余量，共 900 个 measured command、300 笔期望成交。`verify` 读取保存的预期 snapshot 与最后一笔命令，检查故障后的状态、相同身份重放和冲突拒绝。它本身不杀成员，调用耗时也不能冒充从外部故障开始计算的完整恢复耗时。

本轮故障模型限定在**运行中 Pod 的 Java 进程停止/终止/重启，以及同一临时磁盘可用时的日志恢复**。sync level 2 和 fsync 调用不证明设备断电持久性；本轮也不证明 Pod 停止、重建、宿主断电或临时盘消失后的数据可恢复。需要这些保证时，再单独设计存储、独立故障域和备份恢复试验。

## 故障发现、修复与实际恢复证据

首轮故障暴露了客户端问题：终止 node 0 后，官方 ClusterTool 确认 node 2 已成为新 leader，node 1/2 的日志位置相同；但新建客户端仍卡在失效旧入口并于 20 秒超时。Java release `2597bc3` 部署后，**原 leader 仍保持停止**时，新客户端已验证原规范状态及相同身份重放。随后才重新加入原成员。原始失败及 `post-first-failed-bootstrap/` 全部保留。

在该修复版本上又完成两轮 leader SIGKILL，分别观察到新的 leader、相同 checkpoint 的客户端验证、随后新的业务写入和成交、被终止成员重入追平。时间线记录的编排总体耗时分别为 **28.451178 秒**和 **31.386420 秒**，包含 SSH 建连、信号分发、新客户端 JVM 启动、连接、快照与重放核对；它们不是首次新写入的恢复延迟，也不构成 failover SLA。

快照后首次全停三个 JVM 的操作成功，但首次重新启动出现 `Process identity was not established`。该失败与 `cold-start-failed/` 保留。Python launcher `e1972ed` 将单次身份采样改为最多 2 秒的有界建立窗口，持续检查子进程存活并保持 exact startTicks / argv SHA 和 pidfd 停止验证；三台均通过 18 项 launcher 测试。升级 launcher 后补起并核对，再次**全部停止三个 JVM、重新启动三个 JVM**的完整复测通过。该补丁的成功复测不意味着已证明最初 `/proc` 采样失败的全部底层成因。

[冷重启后的三台记录](../evidence/2026-10-23/runpod-cluster/after-cold-restart/)各自包含恢复日志：`commands=1182 exported=0 pending=1574`，恢复 hash 均为：

```text
296778015e702417f40a705afbdf4598926ec2f3ee239fb52d3b8e871a656fae
```

同一 checkpoint 的客户端 canonical bytes 与重放检查通过，官方 ClusterTool 随后列出的三个成员均处于 **term 6、logPosition 909632**。这验证了在相同 Pod 和临时盘仍可用时，核心状态和 **1574 个尚未导出的 outbox 事件**可跨 JVM 全停/全起恢复。接着才运行前述冷重启后的新 900-command 工作负载；不能混淆恢复时 checkpoint 和新交易后的最终状态。

用户已明确授权将本次纯合成测试的原始证据保存本地并推送到本私有仓库；不包含任何私钥或 API 密钥。

## 离线备份、恢复保留服务与到期提醒

备份前，三个成员写入了同一最终 checkpoint：**commands=2440、exported=3300、pending=0**，hash 为 `0425728d6119c011db1d45d0607c5370a3a156969ba740ba6044a23183b26abd`，见 [final-before-archive](../evidence/2026-10-23/runpod-cluster/final-before-archive/)。随后网关、projector、三个 JVM 和 PostgreSQL 均优雅停止，针对静止数据制作三份离线归档并导出到本地。node 0/1 归档各自的 Archive/Cluster 数据，node 2 还包括 PostgreSQL 数据目录。

[离线备份摘要](../evidence/2026-10-23/runpod-cleanup/offline-backups-summary.json)及 [node 0](../evidence/2026-10-23/runpod-cleanup/node0-archive-manifest.json)、[node 1](../evidence/2026-10-23/runpod-cleanup/node1-archive-manifest.json)、[node 2](../evidence/2026-10-23/runpod-cleanup/node2-archive-manifest.json)清单记录了本地归档位置、字节大小、SHA-256、允许的成员路径与版本；这些清单和摘要已推送到私有仓库。归档创建和本地校验已完成，尚未从这些本地副本进行恢复演练。

用户随后选择保留运行，停止 Pod 的弹窗已取消，**三个 Pod 没有 Stop，也没有清空临时盘**。集群、PostgreSQL、projector 和网关在原始、未替换的数据目录上恢复服务，离线归档仍代表先前静止时点，并未用备份覆盖线上数据。[保留平台 readiness](../evidence/2026-10-23/runpod-cleanup/retained-platform-readiness.json)记录 health UP、recoveredCommands **2440**；恢复后 mirror 为 **2454 commands / 3327 events**，数据库观察为 **cursor 3327、marketSeq 3313、tradesStored 825、lag 0**，并已将 synthetic flow 暂停。上述新观察不是对旧 3300/819 SQL 审计的重写，也不代表执行过 Pod 重启或备份恢复。

用户已选择**再保留 6 小时**。一次性到期提醒已创建并检查，automation ID 为 `vectormatch`，创建时间 **2026-10-23 18:23:59.656 UTC**；到期约为 **2026-10-24 00:24 UTC / 迪拜 04:24**。它只提醒，不自动 Stop、不清空磁盘，也不执行预算封顶。三台继续按约 $1.56/h 计费，最终停止资源和实际账单结算尚未发生。

## 最终 egress 修复、对照实测与新版本恢复

本地真实 embedded MediaDriver/UDP 测试复现了 64KiB term rotation 返回 `Publication.ADMIN_ACTION` 时，旧服务单次 `offer` 未重试、目标回复未送达的路径。相同边界用例在旧代码下 3 项失败，修复后连同发送次数边界共 7 项通过，见 [RED/GREEN 记录](../evidence/2026-10-23/runpod-egress/validation/summary.json)。修复仅对 `ADMIN_ACTION` 最多发送 **3 次相同编码回复**；其他结果立即结束，不引入无界等待、额外队列或重复业务 apply。旧云样本未记录每次 service offer 的返回码，因此不能逐条断言历史 500ms 尾部的直接原因。

包含真实 loopback PostgreSQL 的完整本地验证为 **79 tests、0 skipped、0 failures、0 errors**，见 [完整验证摘要](../evidence/2026-10-23/runpod-egress/validation/full-validation-summary.json)及同目录 JUnit/log/hash 证据。它是本地 macOS 验证；后续云端记录单独验收。最终 release 的源码、构件校验和各 Pod 上传/部署记录保存在 [egress DEPLOYMENT](../evidence/2026-10-23/runpod-egress/deployment/DEPLOYMENT.json)和 [rollout checksums](../evidence/2026-10-23/runpod-egress/deployment/rollout-checksums.json)。

升级前暂停 gateway/projector，使用旧 release 在现有状态上运行对照；升级到 `e1db2e7` 后，先核对对照结束 checkpoint 的 canonical bytes/hash 仍为 `6519aeaa2fe96b75d7160ee13e3c0f0dfb0951f8a5919976b72c5552fc7ae695`，再运行同规模新测试。

| 运行 | Java 版本 / leader | measured command / trade | goodput | RTT p50 / p99 / max | accepted resend / unknown |
|---|---|---:|---:|---|---:|
| [egress 对照](../evidence/2026-10-23/runpod-cluster/runs/cloud-egress-control/result.json) | `2597bc3` / 2 | 900 / 300 | 122.508728 command/s | 5.962113 / 9.115065 / **521.332590 ms** | 3 / 0 |
| [ADMIN_ACTION 有界重试](../evidence/2026-10-23/runpod-cluster/runs/cloud-egress-admin-retry/result.json) | `e1db2e7` / 0 | 900 / 300 | 111.766404 command/s | 9.099175 / 11.268264 / **12.352948 ms** | 0 / 0 |

两次都是 single-inflight closed-loop、各一次 trial，leader 不同，负载生成器仍共享集群成员。新版本这次观察到零 accepted resend、最大 RTT 12.352948ms；对照的中位数、p99 和 goodput 反而更好，因此不作吞吐提速或完整延迟分布改善的因果结论，也不把单次无 500ms 样本扩展为 tail SLA。初始 526.493987ms、冷重启后 524.124121ms 及新对照 521.332590ms 的原始报告全部保留。

最终 release 又完成一次外部 leader **0 → 2** 的 SIGKILL 验证：同 key 重放、冲突拒绝、canonical bytes 一致；随后 [新业务 smoke](../evidence/2026-10-23/runpod-cluster/runs/cloud-egress-after-fault/result.json)确认 3 个 measured command / 1 笔成交，另有 2 笔 setup deposit 和 90 个预热 command。被终止成员重入后，官方成员列表显示三台 **term 9、logPosition 4408544**。时间线中的 **34.375435 秒**包含 SSH、信号分发、新 verifier JVM、bootstrap 和状态核对，是编排总体耗时，不是纯选举时间、first-new-write latency 或 RTO。

[最终 release 验证](../evidence/2026-10-23/runpod-egress/final-release-verification.json)记录了重新启动 PostgreSQL/projector/gateway 后的一个新时点：网关 health UP、flow 已暂停、mirror **4539 commands / 6106 events**，PostgreSQL 观察 **cursor 6106、marketSeq 6086、tradesStored 1519、lag 0**，mirror 与 authoritative snapshot 的 hash 均为 `4450df5dc1a6662fec3c8addd55452657ee6fd1ccd0aeae92cc6dbb7e18c780b`。这不覆盖之前 SQL 审计的 3300/819、首次保留服务的 3327/825 或离线备份时点；升级后的新业务也没有自动写回原先的离线备份副本。保留 6 小时及 00:24 UTC 的提醒时间不变。

随后在 `e1db2e7` 上重新完成 [最终 HTTP smoke](../evidence/2026-10-23/runpod-egress/http-smoke/summary.json)：**2 个新业务命令、0 笔新成交**，验证 place / 同 key retry / payload conflict / cancel、余额恢复以及 replicated canonical mirror；该次完成时观察到 **cursor / eventsStored 6108、marketSeq 6088、tradesStored 1519、lag 0**。这是发生在前述 6106 时点之后的新观察，不覆盖旧记录。

[最终 SQL 账本审计](../evidence/2026-10-23/runpod-egress/postgres-ledger.json)在一个只读 repeatable-read JDBC 事务中逐行验证 **eventSeq 1..6108、正 marketSeq 1..6088 连续，TRADE 行数 1519 与持久化 cursor/counters 一致**；它仍限于数据库内连续性与计数一致性。[最终 WebSocket 记录](../evidence/2026-10-23/runpod-egress/websocket.json)又收到 **3 帧 full-state snapshot**，各帧 health UP、mode `CLUSTER_REPLICATED`，projection cursor **6108**、trades **1519**、观察 lag **0**。这些功能通过没有扩展为逐事件可靠分发、容量、SQL payload 独立语义或物理故障域证明；六小时保留和原定到期提醒不变。

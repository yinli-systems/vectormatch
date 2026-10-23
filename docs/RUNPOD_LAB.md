# Runpod 三节点 UDP 实验记录

2026-10-23，本项目在 Runpod `EU-RO-1` 实际创建了三个开启 Global Networking 的 GPU Pod。私网 UDP 全互连预检和随后三成员真实撮合 smoke 均已通过。六组原始 client/server 报告、三台身份/网络/cgroup 预检及文件 SHA-256 汇总见 [runpod-network/summary.json](../evidence/2026-10-23/runpod-network/summary.json)；业务测试单独见 [runpod-cluster/result.json](../evidence/2026-10-23/runpod-cluster/result.json)。故障恢复、数据库投影和资源收尾逐项验收，不由网络 PASS 推定。

## 实际资源与预算

| 节点 | Pod ID / 私网地址 | 控制台 GPU | 控制台 CPU / RAM | 可见 CPU quota 上界 | 可见内存上界 | GPU + 临时盘报价 |
|---|---|---|---|---:|---:|---:|
| 0 | `aykai4bhv4zdf9` / `10.0.212.169` | RTX 2000 Ada | 6 vCPU / 31GB | 5.1 | 30,999,998,464 B | $0.240 + 约 $0.007/h |
| 1 | `9zt5cl1tpc7zt7` / `10.1.60.60` | RTX PRO 4000 | 12 vCPU / 31GB | 10.2 | 30,999,998,464 B | $0.570 + 约 $0.007/h |
| 2 | `h21wqh0s7g26bk` / `10.1.81.207` | RTX PRO 4500 | 28 vCPU / 62GB | 23.8 | 61,999,996,928 B | $0.720 + 约 $0.007/h |

三台运行报价按上述分项合计 **$1.551/h**，规划时上调为 **约 $1.56/h**。本项目总预算是 **$20**。这不是已经发生的扣费金额；三台启动时间不同，实际费用必须在实验结束后按各 Pod 的运行时长和提供方账单核对。目前没有账户余额或其他既有任务的费用信息，不能把此项目预算描述成账户自动停机上限。收尾时先导出证据，再结束本项目新增资源；当前收尾状态保留为待完成。

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

三台已按源码版本 **`924ecdd`** 启动各自的 Aeron 成员，使用同一有序成员列表、端口 base `19000`、sync level **2**、outbox capacity **65536**、Aeron MTU **1248**。分发包和源码校验清单保存在 [DEPLOYMENT.json](../evidence/2026-10-23/runpod-cluster/DEPLOYMENT.json)，启动记录保存在同目录的 `startup/`。部署根目录为 `/opt/vectormatch`，JDK 位于 `/opt/vectormatch/tools/jdk`，本代状态目录为 `/opt/vectormatch/runtime/cloud-20261023-01`。

```sh
cd /opt/vectormatch
export JAVA_HOME=/opt/vectormatch/tools/jdk
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

负载生成器运行在 **node 2**，与一个集群成员共享资源；这不是第四台独立压测机，也没有采用 open-loop 到达模型或寻找饱和容量。节点 0/1/2 的 32 次 4KiB flush+fsync 预检分别观察到 p50 **0.101603 / 6.919250 / 2.563550 ms**，这只是有限文件同步探针，既不是磁盘容量结论，也不证明设备断电语义。

PostgreSQL 已在 node 2 以非 root OS 用户、loopback 监听方式启动。事务投影采用 commit-before-ack 契约；它的真实游标、重复与故障恢复验证仍须由独立应用证据确认，不能由数据库进程存活推定。

| 验收项 | 本页写入时的状态 | 证据要求 |
|---|---|---|
| 六方向原生 UDP、DF、源地址、RTT | **PASS** | 本页引用的 21 份原始 JSON 及网络 summary |
| 三成员启动与一致配置 | **PASS** | 各节点 startup/launch record、构建与文件校验记录 |
| 正常交易与规范状态一致 | **PASS** | `runpod-cluster/result.json`：900 measured command、300 成交、规范状态一致 |
| 外部停止 leader 后保持正确状态 | 待验证 | 精确故障时间与成员、实际新 leader、同 key 重放不增序号 |
| 三个 Java 进程全部重启恢复 | 待验证 | 相同运行 Pod/数据目录、恢复日志和保存状态逐字节核对 |
| 网关与 PostgreSQL 事务投影 | 已部署部分组件，待验收 | HTTP/WS 业务响应、真实 DB cursor、commit/ack 与无 gap |
| 导出证据、结束新增资源、费用结算 | 待完成 | 证据导出清单、各 Pod 生命周期与账单 |

`RemoteClusterExperiment run` 的默认计划是两笔 deposit、30 个预热 cycle、300 个测量 cycle；每 cycle 包含 maker 10 lot、IOC taker 4 lot 和撤销 maker 余量，共 900 个 measured command、300 笔期望成交。`verify` 读取保存的预期 snapshot 与最后一笔命令，检查故障后的状态、相同身份重放和冲突拒绝。它本身不杀成员，调用耗时也不能冒充从外部故障开始计算的完整恢复耗时。

本轮故障模型限定在**运行中 Pod 的 Java 进程停止/终止/重启，以及同一临时磁盘可用时的日志恢复**。sync level 2 和 fsync 调用不证明设备断电持久性；本轮也不证明 Pod 停止、重建、宿主断电或临时盘消失后的数据可恢复。需要这些保证时，再单独设计存储、独立故障域和备份恢复试验。

首轮故障还暴露了真实客户端问题：终止 node 0 后，官方 ClusterTool 确认 node 2 已成为新 leader，node 1/2 的日志位置相同；但新建客户端仍卡在失效旧入口并于 20 秒超时。[原始失败时间线](../evidence/2026-10-23/runpod-cluster/fault-timeline.json)和 `post-first-failed-bootstrap/` 被完整保留。启动入口轮换补丁已通过本地真实三进程回归，云端复测尚在继续；此时不将最终故障恢复标为 PASS。用户已明确授权将本次纯合成测试的原始证据保存本地并推送到本私有仓库；不包含任何私钥或 API 密钥。

# 一次 409 条周期尾延迟的定位：Aeron egress term 轮转

2026-10-23，VectorMatch 的三成员 Runpod UDP 实验暴露了周期性的约 500 ms 请求尾延迟。核心状态与幂等结果核对通过，但服务发送回复时只调用一次 `ClientSession.offer`，忽略了需要重试的 `ADMIN_ACTION`。随后用真实 Aeron UDP publication 复现回复丢失，再加入最多三次、仅针对该返回码的重试。修复后云端运行的 **900 个测量命令**中 accepted resend 为 0，最大 RTT 为 **12.352948 ms**；它的吞吐低于紧邻的旧版对照，不能据此宣称吞吐或主体 RTT 因果改善。

本记录区分三类证据：历史云样本提供线索，隔离的真实 UDP 回归直接验证代码缺陷，新云运行验证部署后的有限观察。历史云服务没有记录逐次回复 `offer` 返回码和 term offset，因此不能把旧样本逐条写成已经直接观测到的轮转丢回复。

最早两组各 900 个测量命令中，超过 500 ms 的样本分别位于零起始索引 **90 / 499** 和 **189 / 598**，各自间隔均为 **409**。每组都有 2 次 accepted transport resend，慢样本均返回 `replayed=true`，unknown timeout 为 0。随后旧版对照的索引 **77 / 486 / 895** 再次出现相同间隔，对应 3 次 resend。原始逐请求记录分别见 [初始样本](../evidence/2026-10-23/runpod-cluster/runs/cloud-3nodes-01/samples.csv)、[冷重启后样本](../evidence/2026-10-23/runpod-cluster/runs/cloud-after-cold-final/samples.csv)和[旧版对照样本](../evidence/2026-10-23/runpod-cluster/runs/cloud-egress-control/samples.csv)。

固定间隔首先指向回复端的字节边界。[CommandCodec.reply](../cluster/src/main/java/io/vectormatch/cluster/CommandCodec.java) 对成功 Place 编码 90 字节，对 Cancel 编码 91 字节。Place 的 `tradeCount` 无论为 0 还是 1，都只是同一个四字节整数；回复中不附带成交事件列表，因此两种 Place 的长度一致。90 字节由 15 字节 envelope、1 字节结果存在标记、1 字节 code、12 字节 reason（长度字段加 `accepted`）、24 字节结果 long、4 字节 tradeCount、1 字节 replay 标记、24 字节序号及两个空字符串长度字段组成。

Aeron 1.53.3 的 [cluster session header](https://github.com/aeron-io/aeron/blob/1.53.3/aeron-cluster/src/main/java/io/aeron/cluster/client/AeronCluster.java#L99) 为 32 字节；[DATA header](https://github.com/aeron-io/aeron/blob/1.53.3/aeron-client/src/main/java/io/aeron/protocol/DataHeaderFlyweight.java#L38) 为 32 字节，[frame alignment](https://github.com/aeron-io/aeron/blob/1.53.3/aeron-client/src/main/java/io/aeron/logbuffer/FrameDescriptor.java#L66) 也是 32 字节。这里计算的是 Aeron term 内的帧占用，不包含 IP/UDP 头：

```text
Place reply: align32(90 + 32 + 32) = 160 bytes
Cancel reply: align32(91 + 32 + 32) = 160 bytes
64 KiB term: 65536 = 409 × 160 + 96 bytes
```

[ClientEndpoint.channel](../cluster/src/main/java/io/vectormatch/cluster/ClientEndpoint.java) 显式指定回复 channel 的 `term-length=64k`。连续 409 个上述成功回复之后，只剩 96 字节，下一条 160 字节的帧无法放入当前 term。官方 [Publication 1.53.3](https://github.com/aeron-io/aeron/blob/1.53.3/aeron-client/src/main/java/io/aeron/Publication.java#L59) 将 `ADMIN_ACTION=-3` 定义为需要重试的发送失败，term 轮转是其适用场景。该版本 [ConcurrentPublication.handleEndOfLog](https://github.com/aeron-io/aeron/blob/1.53.3/aeron-client/src/main/java/io/aeron/ConcurrentPublication.java#L743) 会写入剩余 padding、轮转日志，然后返回 `ADMIN_ACTION`；它没有把本次应用消息自动发送到新 term。

官方 `ContainerClientSession.offer` 经 `ClusteredServiceAgent.offer` 也只是执行一次 publication offer，没有隐藏的重试。旧版 [生产源码副本](../evidence/2026-10-23/runpod-egress/validation/red-production-source.java) 的 `respond` 同样只调用一次并忽略结果。于是业务可能已经在复制状态机中执行并提交，回复却没有进入传输；客户端在 [ClusterClient.exchange](../cluster/src/main/java/io/vectormatch/cluster/ClusterClient.java) 规定的 500 ms 间隔后，重发相同业务身份并获得缓存结果。这个机制能解释固定间隔、约 500 ms 尾部与 `replayed=true` 同时出现，而不要求业务重复执行。

入口请求的长度随 producer 和 clientOrderId 变化，最早两组的 Place 入站帧分别对齐到 224 和 256 字节，Cancel 则均为 160 字节，且入口还承载 keepalive 和重发；相同的 409-command 周期更吻合固定大小的回复。测量前的快照读取、两笔 deposit 和预热也会消耗回复 term 空间，因此第一处测量索引可以改变；历史现场没有记录该起始 offset，不将相位变化推导成已测出的绝对 term 位置。

为直接检验缺陷，新增 [MatchingClusteredServiceEgressRotationTest](../cluster/src/test/java/io/vectormatch/cluster/MatchingClusteredServiceEgressRotationTest.java)。测试启动真实嵌入式 MediaDriver、UDP publication/subscription，使用与官方服务包装相同的 32 字节 session header，通过 ClientSession 适配器调用实际服务回调。它先等待真实连接，再持续收取填充消息以打开消费窗口，核对 publication position 恰为 **65440**、剩余 **96** 字节，最后调用目标回复路径。这样可以区分 term 轮转与未连接或消费窗口背压；快照接收使用 FragmentAssembler 校验完整消息。

旧实现下，普通业务回复、轻量 position 控制回复和分片快照回复三项测试全部失败：真实目标 offer 均返回 **`[-3]`**，随后没有收到目标回复。完整 [RED 日志](../evidence/2026-10-23/runpod-egress/validation/red.log)和 [RED JUnit](../evidence/2026-10-23/runpod-egress/validation/red-junit/TEST-io.vectormatch.cluster.MatchingClusteredServiceEgressRotationTest.xml)保留该结果。这是本地真实 UDP 发送路径的隔离回归，没有把它描述成三节点复制或 Linux 云性能测试。

修复集中在 [MatchingClusteredService.respond](../cluster/src/main/java/io/vectormatch/cluster/MatchingClusteredService.java)：复用同一份已编码回复，最多执行 **3 次总 offer**；只有结果为 `ADMIN_ACTION` 才立即重试。成功、`BACK_PRESSURED`、`NOT_CONNECTED`、`CLOSED`、`MAX_POSITION_EXCEEDED` 均立即返回。三次仍为 `ADMIN_ACTION` 时也返回，保留已有的客户端同 key 恢复流程。没有 sleep、无限等待、待发队列或再次调用核心引擎。普通回复、position、fetch/ack 和 snapshot 原本就统一经过此方法。

相同真实轮转测试修复后得到以下结果。正值是成功写入后的 publication position；快照回复确实通过三个 Aeron fragment 传输并重组。

| 目标回复 | 实际 offer 返回序列 | 收到的 fragment 数 |
|---|---|---:|
| 普通业务 | `[-3, 65696]` | 1 |
| position 控制 | `[-3, 65664]` | 1 |
| snapshot 首块 | `[-3, 68864]` | 3 |

另有 [4 项边界测试](../cluster/src/test/java/io/vectormatch/cluster/MatchingClusteredServiceResponseBoundTest.java)验证：持续 ADMIN_ACTION 只尝试三次且同 key 可恢复原结果；其他负返回只尝试一次；ADMIN_ACTION 后遇到背压立即停止；首次接受后不再重试。合计 **7 项 GREEN，零跳过、零失败**，见 [GREEN 日志](../evidence/2026-10-23/runpod-egress/validation/green.log)、[真实轮转 JUnit](../evidence/2026-10-23/runpod-egress/validation/green-junit/TEST-io.vectormatch.cluster.MatchingClusteredServiceEgressRotationTest.xml)与[边界 JUnit](../evidence/2026-10-23/runpod-egress/validation/green-junit/TEST-io.vectormatch.cluster.MatchingClusteredServiceResponseBoundTest.xml)。最终 fixture 另补了初始化失败清理，RED/GREEN 的目标断言、边界和帧路径保持一致；源码哈希与过程说明见 [validation/summary.json](../evidence/2026-10-23/runpod-egress/validation/summary.json)。

随后完整 `check` 和 cluster/server/projector 分发构建通过：**79 项 Java 测试，零跳过、零失败、零错误**，其中已包含上述 7 项。原始各模块 JUnit 和构建范围见 [full-validation-summary.json](../evidence/2026-10-23/runpod-egress/validation/full-validation-summary.json)及 [full-junit](../evidence/2026-10-23/runpod-egress/validation/full-junit/)。这些检查在 macOS 使用真实本地 UDP 和 loopback PostgreSQL 完成，不是 Linux CI 或云容量结果。

云端升级使用不可变 Java release **`e1db2e755a834234efb60b7a1ed291b31ce33c16`**，三台构件与源码校验见 [DEPLOYMENT.json](../evidence/2026-10-23/runpod-egress/deployment/DEPLOYMENT.json)和 [rollout-checksums.json](../evidence/2026-10-23/runpod-egress/deployment/rollout-checksums.json)。旧版对照结束后先保存 checkpoint，再停止三个 JVM、升级构件并保留原状态目录，升级后验证同一 checkpoint 的 canonical bytes、同 key 重放及冲突拒绝，再开始新业务。全过程见 [故障时间线](../evidence/2026-10-23/runpod-cluster/fault-timeline.json)。

四组云端运行均为三成员、sync level **2**、UDP MTU **1248**、单客户端单在途的 closed-loop 工作负载。每组测量 **900 个已确认命令、300 笔成交、1200 lot**，另有 2 笔 deposit 和 90 个预热命令不计入测量。各组逐笔 reference、最终 canonical snapshot bytes、hash、不变量与同 key 重放均通过。下表 RTT 单位为 ms，goodput 单位为已确认 command/s；leader 来自时间线和对应验证记录，而非 `result.json` 中不存在的 leader 字段。

| 运行 / 原始结果 | Java release | leader | goodput | RTT p50 | RTT p99 | RTT p99.9 / max | accepted resend / unknown |
|---|---|---:|---:|---:|---:|---:|---:|
| [初始基线](../evidence/2026-10-23/runpod-cluster/runs/cloud-3nodes-01/result.json) | `924ecdd` | 0 | 95.149787 | 9.148866 | 12.361379 | 526.493987 | 2 / 0 |
| [冷重启后](../evidence/2026-10-23/runpod-cluster/runs/cloud-after-cold-final/result.json) | `2597bc3` | 0 | 96.849023 | 9.124065 | 12.295407 | 524.124121 | 2 / 0 |
| [升级前旧版对照](../evidence/2026-10-23/runpod-cluster/runs/cloud-egress-control/result.json) | `2597bc3` | 2 | 122.508728 | 5.962113 | 9.115065 | 521.332590 | 3 / 0 |
| [ADMIN_ACTION 重试修复后](../evidence/2026-10-23/runpod-cluster/runs/cloud-egress-admin-retry/result.json) | `e1db2e7` | 0 | 111.766404 | 9.099175 | 11.268264 | 12.352948 | 0 / 0 |

最新两组的 accepted transport attempt 分别是 **903** 和 **900**；两组都还有 **3 个 unaccepted offer**。这说明修复后的测量并非“所有 offer 都一次成功”，也不能把入口 unaccepted offer 与服务回复 ADMIN_ACTION 混为一个指标。[修复后全部 900 条样本](../evidence/2026-10-23/runpod-cluster/runs/cloud-egress-admin-retry/samples.csv)没有超过 500 ms 的请求；保留了所有样本，没有删去旧组慢请求或把四组混合计算分位数。

这不是同 leader、同初始状态、随机顺序的配对 A/B。尤其旧版对照 leader 为 **2**，修复后为 **0**；负载生成器位于 node 2，leader 切换也改变了共机资源和网络路径。状态沿同一世代继续增长，初始 snapshot 大小分别为 **120 / 429722 / 877233 / 1257783 字节**；没有把四组重置到相同初始快照。云端调度、文件同步和运行顺序也未被隔离。可报告本次修复后未观察到重发尾部，不能据此宣称总体吞吐提升或 p50/p99 因果改善；表中旧版对照的吞吐和 p50/p99 实际更好。

execute RTT 包括编码、UDP、复制提交、撮合、回复和自动重试；goodput 的分母还包含 reference 匹配、验证和样本记录，排除 setup、warmup 与最终快照核对。900 个样本使用 nearest-rank 时，p99.9 落在第 900 条，正好等于最大值，不能作为高置信极尾或 SLA 证明。单在途短 smoke 没有开放到达率、并发饱和曲线或独立负载机，不是平台容量、零延迟、物理故障域或断电持久性结论。[Runpod 实验记录](RUNPOD_LAB.md)保留了资源与存储边界。

同一最终 release 还进行了一次外部 leader 进程故障验证：SIGKILL node 0 后，新客户端在 node 2 成为 leader 时，通过原 canonical snapshot、相同 key 重放、变更 payload 冲突拒绝和不变量核对，见 [故障后 verify](../evidence/2026-10-23/runpod-cluster/runs/cloud-egress-admin-retry/verify-1792780449211-31e9b1a8.json)。随后 [故障后新业务 smoke](../evidence/2026-10-23/runpod-cluster/runs/cloud-egress-after-fault/result.json)完成 **3 个 measured command / 1 笔成交**，另有自身 setup 和 warmup；它不并入四组 900-command 数据。

原成员重入后，官方 ClusterTool 观察到三成员均处于 **term 9、logPosition 4408544**，leader 为 2。SIGKILL 到验证结束的 **34.375435458 秒**是包含 SSH、信号分发、新 verifier JVM、bootstrap 和核对的编排区间，不是纯选举时间、首次新写入恢复时间或 RTO。最终 release 的恢复与平台通路证据见 [final-release-verification.json](../evidence/2026-10-23/runpod-egress/final-release-verification.json)；故障模型仍限定为同一运行 Pod 和原文件系统可用时的 Java 进程终止及恢复。

恢复后的最终 [HTTP 验收](../evidence/2026-10-23/runpod-egress/http-smoke/summary.json)通过下单、重试、冲突拒绝、撤单、镜像核对和数据库游标检查。[只读 PostgreSQL 全账本](../evidence/2026-10-23/runpod-egress/postgres-ledger.json)确认 eventSeq 连续至 **6108**、正 marketSeq 连续至 **6088**、TRADE 共 **1519** 条，游标与计数一致；[WebSocket](../evidence/2026-10-23/runpod-egress/websocket.json)收到三个真实 full-state 快照。机器可读汇总见 [summary.json](../evidence/2026-10-23/runpod-egress/summary.json)。这些是功能和账本连续性证据，不扩大为逐事件投递、数据库 HA 或容量结论。

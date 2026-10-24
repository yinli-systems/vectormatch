# 单一 lineage 的一亿笔新订单：实现前置条件

这是当前源码审查后的设计与验收计划；已有独立本地Cluster功能原型，完整云端接入、持久归档与流式harness尚未验收。目标计数为同一个连续状态中，首次 `ACCEPTED Place` 的唯一订单数；重试、拒绝、充值、取消和重建后的独立试验均不增加此计数。累计一亿笔、一亿笔/秒、一亿连接是三项独立目标，均未被当前证据证明。

核心基础已有独立候选：[codex/core-retention-v3@109ae](https://github.com/yinli-systems/vectormatch/tree/109ae1800f0b76620af344a3dd7543849ffffd69)提供显式V3身份、有界完整历史、精确前缀ACK后的终态回收与64MiB独立快照。Root完整检查140项通过、11项PG集成测试因无DBfixture跳过；14项V3专项测试覆盖cap4连续100笔、归档/恢复、FIFO/资产、永久producer高水位与各类背压。完整源码/fixture SHA与验证记录在[核心候选证据](../evidence/2026-10-24/runpod-cpu/core-retention-v3/source-validation/README.md)。它未部署到当前CPU测量集群，不是百万/一亿、持久性或新增性能证明。下一阶段的[独立Cluster接入设计](CLUSTER_RETENTION_V3_DESIGN.md)明确区分业务、维护、历史归档、PG事件ACK与Aeron日志位置。

## 当前实现的硬边界

独立[codex/retention-aeron-v3@9fda247](https://github.com/yinli-systems/vectormatch/tree/9fda247d392432761a670de7c4d8040c7caff283)已加入V3专用Aeron服务/节点/单请求客户端、有界reply/event fetch/archive chunk与按实际profile限额的快照传输。Root完整检查178项通过、11项PGfixture跳过、0失败；本地三个JVM使用sync2，在同一个小lineage内完成47业务命令、49事件和4笔首次接受订单，验证不可变历史前缀、三节点一致checkpoint、全部停机后恢复并继续下单。源码和三个阶段的完整原生归档见[独立证据](../evidence/2026-10-24/runpod-cpu/retention-aeron-v3/source-validation/README.md)。它没有部署到云端容量集群；外部归档读回/故障恢复、持续事件投影、安全Aeron日志回收、长跑profile的维护journal寿命及一亿订单验收仍待完成。

`MatchingEngine` 会永久保留终态订单和 `(accountId, clientOrderId)` 索引，历史订单查询也从这些内存对象读取。`capacity-350k-v1` 的热状态限额为360,000订单，snapshot条目有10,000,000的额外硬界。不能靠增大一项常量承载一亿笔真实订单，直接删除终态则会改变历史ID复用拒绝、查询和旧订单取消的行为。

当前 `ORDER_ACCEPTED` 事件不含完整的 producer/request/client-order identity，现有 PostgreSQL events 表无法单独重建精确历史 clientID 索引。任意历史 clientID 永不复用的契约，需要保存完整键的精确冷索引；Bloom filter和短hash只能加速，不能代替精确判断。确定性服务也不能根据各节点自行读取外部数据库的结果作交易裁决。

相关源码： [核心状态、执行与快照](../core/src/main/java/io/vectormatch/core/MatchingEngine.java)、[Cluster限额](../cluster/src/main/java/io/vectormatch/cluster/ClusterCapacity.java)、[全量checkpoint](../cluster/src/main/java/io/vectormatch/cluster/ClusterStateSnapshot.java)、[快照传输](../cluster/src/main/java/io/vectormatch/cluster/SnapshotTransport.java)。

## 新版本的状态与身份契约

采用独立的新协议/profile与新试验 lineage，保留旧版本的读取和显式迁移边界。新订单的业务身份使用 `(account, stable producer, requestSeq)`，clientID由该身份唯一推导，producer身份和high-water不得回收或重置。旧任意clientID仍属于legacy协议，不能悄然按新契约解释。这个选择减少历史字符串的热索引需求，但必须在API中明确公布版本差异。

热状态保留活跃订单、必要的近期终态、账户资产、producer high-water、有界重试结果、全部全局long序号以及历史归档锚点。历史查询改为有界分页的冷历史接口；已归档订单的取消语义须版本化，或经过精确历史查询后返回旧契约结果。现有过期结果返回 `STALE_SEQUENCE` 且不重执行的有限重试契约须保留；未决UNKNOWN不能越过已保证的结果保留水位。

通过复制的 `ArchiveCommit / CompactThrough` 命令选择确定切点。只有终态订单的完整身份、订单结果和事件历史已经密封、读回校验，并与确定性摘要匹配，才允许回收对应热对象。禁止本地timer各自删状态。压缩必须保持活跃订单的价格/FIFO顺序、资产和reserved守恒、high-water、全局订单与事件序号；重启后不得重新使用旧身份。

新checkpoint编码有界热状态、重试水位、归档manifest/hash chain和compaction水位，采用有上限的分块/流式传输，验证截断、重排、块校验及整摘要。当前实现的多次整 `byte[]` 拷贝和256/512MiB限额不能直接放大到multiGB。

## 日志、outbox与空间

一亿笔单成交订单会产生约两亿条业务事件。必须持续导出outbox，保持数据库事务commit之后才发送复制ACK的顺序及连续性/冲突校验。当前每批最多16事件的同步调用要另行做有界批量协议对照；不能无限增大队列或取消背压。

5GiB根盘只承担滚动热日志和至少两代可恢复checkpoint。密封历史及原始测量流持续归档至现有FUSE挂载并读回SHA验证；FUSE仍只作为当前已披露的归档介质，不获得额外持久性或独立故障域保证。归档落后或空间不足必须背压/停止。完整JSONB事件历史加索引无法假定放进5GiB根盘，新冷历史与有界PG投影必须明确其保存契约。

只有checkpoint恢复、归档验证和所有需要追赶的副本水位都已越过相应位置，才能通过Aeron安全接口清理精确日志segment。不能直接删除 `.rec` 或 `recording.log`。新策略须分别证明leader重启、落后副本追赶和全部进程冷恢复。

相关源码：[outbox](../cluster/src/main/java/io/vectormatch/cluster/ReplicatedOutbox.java)、[可靠导出器](../projector/src/main/java/io/vectormatch/projector/ReliableProjector.java)、[数据库事务](../projector/src/main/java/io/vectormatch/projector/PostgresEventStore.java)。

## 验收顺序

1. 小模型差分测试新身份、重试/冲突、归档终态、FIFO、余额、压缩与恢复。旧profile和原始备份不作隐式升级。
2. 同一lineage接受一百万笔新订单，越过旧360k边界，至少两次compaction，完成checkpoint恢复与继续交易验证。
3. 连续一千万笔，测量heap/GC、积压、日志空间、归档吞吐和慢消费者背压；保存失败和全部原始延迟分段。
4. 资源与证据闭合后执行一亿笔。以10k/s计算纯到达时间约2小时46分40秒，13k/s约2小时8分12秒；实际吞吐与总耗时尚未知。

新harness必须流式生成和记录，使用连续全局/producer序号、有界inflight及滚动SHA manifests，不预分配一亿个Sample或reference Order。分段独立replay与checkpoint hash chain贯穿同一lineage；每段校验接受数、资产、活跃FIFO、历史身份和事件确认。当前 `RemoteCapacityExperiment` 强制空状态、最多350k样本、禁止外部ACK和保留订单数增量等于accepted，这些条件与长期压缩不兼容，应新建harness而非放宽现有350k证据规则。

一亿/秒和一亿连接需各自的负载模型、拓扑与资源证明，不能由上述累计订单测试推导。

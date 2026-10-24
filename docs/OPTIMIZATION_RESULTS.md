# 受控优化与瓶颈归因

本轮首先检验负载端资源布局：在同一三节点撮合集群上，将 **128 个客户端 MediaDriver 改为一个共享 MediaDriver**，保留 128 个独立 Aeron 客户端、session、worker 与单请求在途窗口。预先登记的 A/B/A/B 已完成：客户端资源节省可重复，但四轮 15k/s 均未达到稳定标准；当前没有提高稳定吞吐上限的证据。节点接收缓冲、线程调度的交替对照均没有建立新的稳定边界。350k并发配置对照在第二轮W256失稳时停止，原256个unknown已获明确授权并独立恢复，原容量结果仍为INVALID。随后完成的NAK延迟四轮对照消除了两轮B的最终unknown，但仍然过载。完整历史容量结果见 [CAPACITY_RESULTS.md](CAPACITY_RESULTS.md)，本轮方案见 [OPTIMIZATION_CAMPAIGN.md](OPTIMIZATION_CAMPAIGN.md)。

## 为什么先检查负载端

此前固定 128 客户端、2 GiB 节点、sync2 的长窗试验中，13k/s 两次通过稳定窗口标准，15k/s 两次未通过，14k/s 一稳一非稳。这是直接客户端加复制撮合路径的有限窗口结果。

对历史 [long arrivals 原始数据](../evidence/2026-10-23/runpod-capacity-long/runs/) 的每条 API 执行区间与到达窗口求交，再求区间总长除以窗口长度，可重算平均活跃请求数。13k 两轮约为 **109.28 / 109.54**；15k 两轮为 **127.90 / 127.93**，16k 为 **127.93**，接近 128 个同步槽位的上限。15k 两轮平均 API RTT 约为 8.744 / 8.909 ms，对应 `128 / mean RTT` 约 14,639 / 14,368 次每秒，与实际 goodput 接近。这个恒等关系支持同步窗口直接限制调用路径，不能进一步证明 RTT 的唯一来源。

历史 [telemetry](../evidence/2026-10-23/runpod-capacity-long/analysis/telemetry-summary.json) 显示，负载进程在这些窗口约有 423–425 个线程，平均消耗约 8.9–9.4 个 CPU 等价量；每个原客户端都拥有自己的嵌入式 driver 和 Aeron 连接。共址的 member 2 与发生器相互影响仍是限制。node1 Archive recorder 的 write-path wall-time 占比约为 0.99，计时包含写入与 `force`，也可能包含调度等待；它不是磁盘设备利用率，更不能单独证明落盘是唯一瓶颈。

## 对照协议与不可变配置

| 因素 | A：isolated | B：shared |
|---|---|---|
| 负载阶段 MediaDriver 数量 | 128，每客户端一个 | 1，由负载阶段统一持有 |
| Aeron / ClusterClient / session / worker | 各 128 | 各 128 |
| 每 worker 在途请求 / FIFO | 1 / 64 | 1 / 64 |
| 负载端源与 bundle | 同一新 artifact | 同一新 artifact |
| 节点源、heap、sync、leader、MTU、socket、idle | 固定 | 与 A 相同 |

主序列登记为 **A15k-r1 → B15k-r1 → A15k-r2 → B15k-r2**，每轮计划 190,000 条命令，窗口 12.666666666 秒。先运行 B 的 8k/s、20k arrivals smoke，仅验证连接、正确性与归档路径；其 2.5 秒窗口不具备正式容量判定时长。只有完成的原始数据、固定 leader、配置身份和终态校验都通过后，才纳入结论。

两种模式使用相同 producer/request/client-order 身份、绝对时间调度和原始超时重试策略。共享 driver 不共享 Aeron 实例；每个响应入口使用独立解析的临时 UDP 端口。客户端只关闭自己持有的 Aeron/session，负载阶段在全部客户端退出后统一关闭共享 driver。连接建立、12 秒 session 清理等待、准备与终态验证均在测量窗外。

节点版本固定为 `b6f6c5cd165110e330d409e2ff51ee4574a3720b`，node bundle SHA 为 `0c17626c6aed8061a71915e4dd784887ed9221f7fb3ba56d7fbf1f96985c062d`。A/B 的新负载版本均为 `bdfe09a2907d9b953309e9e870d6f61f28c5e054`，见 [artifact 清单](../evidence/2026-10-23/runpod-optimization/loadgen-deployment-manifest.json) 与 [上传校验](../evidence/2026-10-23/runpod-optimization/loadgen-upload-receipt.json)。新 bundle 中除 ClusterClient/RemoteCapacityExperiment 外的 cluster class 与依赖内容均与固定节点发行包核对；节点 JVM 继续引用原发行目录。

组内准备 SHA 保持 `2247db9c15b0043a0b28172c5bfa2d9e4f20b5748f6a16424d881e296102655f`：64 个买方各 1.9B quote、380k lot 单价 10,000 ticks 的 maker、100 条预热单。每个测量命令为一 lot IOC 买单，成功产生一笔成交。节点与发生器 heap 均为 2 GiB，sync2、leader0、MTU1248、128 KiB UDP 收发缓冲、SHARED driver/archive、默认 Backoff、session 上限128、outbox524288、200k retained orders、512 MiB full checkpoint 均不改变。原 gateway/projector 在测量窗暂停；负载仍与 member 2 共用已有 Pod。

A/B 分别保留 [isolated 登记](../evidence/2026-10-23/runpod-optimization/isolated/campaign.json) 与 [shared 登记](../evidence/2026-10-23/runpod-optimization/shared/campaign.json)。实际 JVM 属性、运行模式/driver 数/Aeron 所有权、node/load revision 和 bundle、准备 SHA 都进入校验与比较身份；两个模式保留独立曲线，不把不同 driver 数的样本混成一个 p99。

## 结果与判定口径

四个主测量点均完成正确性、终态、固定 leader/term0 和配置验证；它们也均有效且非稳定。所有过载点保留。

| 顺序 | 客户端模式 | 窗口 goodput /s | 已接受请求的计划到确认 p99 ms | 未发送 | 排空 ms | 稳定判定 |
|---|---|---:|---:|---:|---:|---|
| A1 | isolated，128 drivers | 14,176.579 | 664.706 | 2,200 | 635.988 | 未通过 |
| B1 | shared，1 driver | 14,336.211 | 575.981 | 451 | 585.641 | 未通过 |
| A2 | isolated，128 drivers | 14,192.132 | 623.971 | 1,986 | 623.372 | 未通过 |
| B2 | shared，1 driver | 14,552.921 | 440.259 | 0 | 450.614 | 未通过 |

每轮均计划 190,000 条、15,000/s；初次与最终 unknown、业务拒绝和 server error 均为 0。前三轮有未发送请求，全量接受 p99 不可用；表中条件 p99 不能代表这些未成功请求的延迟。B2 最终全部接受，但仍因排空和后半段积压增长未通过原稳定标准。不能把排空后的成功计入窗口吞吐。按对应轮次，B 的 goodput 仅提高约 1.1% / 2.5%，条件 p99 下降约 13.3% / 29.4%；这些有限窗口变化没有建立新的稳定边界。

同样的严格内部采样重复显示 [负载端资源下降](../evidence/2026-10-23/runpod-optimization/analysis/attribution-summary.json)：A 平均约 8.83–9.12 核、420 线程、256 个自有 UDP sockets、RSS 中位数 6,343–6,366 MiB；B 为 4.12–4.36 核、293 线程、129 sockets、RSS 中位数 521–532 MiB。两轮 CPU 节省约 52% / 53%。内存含大量文件映射，不能把 RSS 节省等同 Java heap 的减少。

四轮 node0 的一个 driver 一致性命名线程仍为约 0.957–0.965 核，node1 日志 socket 在严格匹配窗口内 drop 增量为 116–186。每秒采样不能捕捉全部瞬时队列峰值；丢包计数也不等于业务丢单。当前证据支持继续检验节点网络处理与复制接收路径，不能断言唯一瓶颈已经确定。

网络对照已另行 [登记](../evidence/2026-10-23/runpod-optimization/network/plan.json)：同一新节点 artifact、相同 shared 客户端，按 128 KiB → 1 MiB → 128 KiB → 1 MiB 的接收请求运行 15k/s。新版本仅 ClusterNodeMain 类内容相对前一构建变化，业务 core/dependencies 不变；两个缓冲组均用该新版本。每轮负载窗外通过 verified PID/startTicks/FD/inode 和已知本机端口过滤的 ss，核验内核实际 rb/tb，避免把请求值当成生效值。send buffer、sync2、leader、heap、MTU、idle、状态 profile、队列与独立身份保持一致。四轮均已完成且非稳定，结果如下。

| 顺序 | 节点接收请求 | 窗口 goodput /s | 已接受条件 p99 ms | 未发送 | 排空 ms | node1 日志 socket 窗口 drops |
|---|---|---:|---:|---:|---:|---:|
| A1 | 128 KiB | 14,215.816 | 623.427 | 1,739 | 493.570 | 218 |
| B1 | 1 MiB | 14,348.605 | 631.623 | 1,074 | 465.073 | 0 |
| A2 | 128 KiB | 14,602.974 | 408.282 | 0 | 454.672 | 205 |
| B2 | 1 MiB | 13,928.921 | 619.682 | 5,790 | 592.137 | 0 |

[逐行与 socket 审计](../evidence/2026-10-23/runpod-optimization/network/README.md) 复核 760,000 个计划到达为 751,397 个最终接受和 8,603 个明确未发送。初次/最终 unknown、业务拒绝和 server error 均为零。A2 全量接受 p99 可定义，其余三轮只报告已接受条件 p99。128 KiB 自身重复的吞吐与 p99 变化较大；两对结果不能证明 1 MiB 导致性能回退，也不能将目标 socket 丢包归零说成整个网络无丢包。各轮 leader 热线程仍约 0.96 核，其他 NAK 信号和 follower Archive 写入路径等待仍存在。

基于这组结果，后续线程对照固定回原 131,072 字节请求，避免叠加未证实有益的缓冲设置。该选择是下一实验基线；原 e1db 应用的运行配置没有在本轮被升级。

已完成的 [shared smoke](../evidence/2026-10-23/runpod-optimization/shared/runs/o-smoke-shared-8000-w128/) 计划 20,000 条命令，在 2.5 秒窗口内确认 19,947 条，对应窗口 goodput **7,978.8/s**；最终 20,000 条全部接受，计划到达至确认 p99 **17.223594 ms**，零未发送、业务拒绝、server error 和初次/最终 unknown。终态与 leader0/term0 校验通过，但正式分类为 `INSUFFICIENT_WINDOW_OBSERVATIONS`，只列为功能验证。

吞吐仅计计划到达窗口内确认的成功新命令，排空后的确认不回填窗口 goodput。p99 从计划时刻计到确认，含调度与 FIFO 等待；任一计划请求未被接受时，全量接受 p99 记为不可用，已接受回复的条件 p99 单列。队列满未发送、业务拒绝、server error、首次 unknown 和最终 unknown 分别计数；原身份重试不增加成功新命令数。

稳定窗口标准沿用容量轮次：至少 10 秒，全部计划命令接受、零首次/最终 unknown、终态与 leader 校验通过，窗口 goodput 达目标的 95%，排空不超过 `max(100 ms, 窗口的 1%)`，后半程 outstanding 拟合增长不超过 `max(2, arrivals 的 1%)`。这允许有限正漂移，不证明长期稳定；p99 没有被事后增加为筛选门槛。

需要同时比较初次 API RTT、FIFO 等待、活跃槽位、排空、CPU/RSS/线程、Aeron 修复和记录/提交/服务位置。新增相同的只读观察器按 PID/startTicks/命令摘要验证进程，采集其线程及所拥有 UDP inode 的队列/丢包；不抓包、不读环境、不做 JVM attach。namespace UDP 重叠计数不相加，`wchan=0`、缺失 sysctl 或零 schedstat 不解释为没有等待，采样队列字节不等于有效 payload 或实际 SO_RCVBUF。具体限制保留于 [观察器部署与范围](../evidence/2026-10-23/runpod-optimization/attribution-deployment.json)。

## 线程调度对照

[预登记计划](../evidence/2026-10-23/runpod-optimization/threading/plan.json) 固定新节点源 `33e6ab32d9a736eaacd8e4060af8036c614b6fe2` / bundle `c043d263521343572fdfbef7fcc1feeb3ef6769a016a550a76d6070019c5c5ea`，按节点 SHARED → DEDICATED → SHARED → DEDICATED 运行 15k/s、190k 到达、W128。客户端仍是一个 shared driver 加 128 个独立 Aeron/session/worker，节点两组使用同一 artifact，原 128 KiB 缓冲前后独立核验。Archive 仍为 SHARED，所有 sync2 设置保留。

Aeron 的默认角色等待参数与原显式 Agrona 默认存在差别，直接改 threadingMode 会混入等待策略变化。这里在同一新 artifact 中，为 shared/sender/receiver/conductor/native-resource 各自建立独立、参数相同的 Backoff(10 spins,5 yields,1000ns min park,1000000ns max park)，并在启动日志记录。DEDICATED 是四个 driver runners，相比共享 composite 多三个，不代表撮合逻辑并行化。CPU、节流、丢包、排空和原正确性规则继续记录。四轮均有效且非稳定，DEDICATED 没有性能收益。

| 顺序 | 节点模式 | 窗口 goodput /s | 已接受条件 p99 ms | 未发送 | 排空 ms |
|---|---|---:|---:|---:|---:|
| S1 | SHARED | 14,411.684 | 541.591 | 19 | 567.278 |
| D1 | DEDICATED | 13,115.763 | 729.875 | 15,642 | 604.966 |
| S2 | SHARED | 14,273.526 | 615.179 | 1,037 | 626.578 |
| D2 | DEDICATED | 13,535.289 | 666.773 | 10,277 | 632.898 |

[完整逐行审计](../evidence/2026-10-23/runpod-optimization/threading/README.md) 复核 760,000 个计划到达为 733,025 个最终接受、26,975 个明确未发送；四轮全量接受 p99 均不可用，unknown、业务拒绝和 server error 均为零。两个 DEDICATED goodput 相对对应控制分别低约 8.99% / 5.17%，条件 p99 高约 34.77% / 8.39%。这些结果保留，下一轮采用节点 SHARED。

node0 JVM CPU 由 S 的 2.528 / 2.577 核增加为 D 的 3.055 / 2.992 核，线程由 28 到 31。严格窗口内 cgroup 累计限流时间分别为 S：0 / 32.52μs，D：369.17 / 80.59ms。它不是单请求暂停时间；均值 CPU 未满配额也不能排除周期内限流。日志 socket drops 294/365 对比 0/15，NAK 与限流时序不完全重合，不能声称限流解释了全部退化。

## 下一组并发配置与全量 pilot

独立新 profile `capacity-350k-v1` / `extended-350k-256` 将 retained 上限固定为 360,000、outbox800,000、全量 checkpoint512MiB、core-view256MiB，其余账户/producer/缓存限制与业务撮合规则保留。新源 `52fbf7fa46ed274891a2bbf0d9fba9d87456d1f5` 的完整 117 项 Java tests 通过；匹配 core、依赖、ClusterClient 和 NodeMain class 内容相对前一发行包逐项一致，仅容量 profile/负载选项类变化。这不是已经测得的容量。

先以 W128、10,000/s、350,000 个计划到达执行 35 秒云端 pilot，核对完整 canonical MatchingEngine core view、逐条 reply、资产与 outbox 水位，验证原600秒进程期限与2GiB heap可用。这项检查不触发 Aeron full replicated checkpoint，也不独立证明完整 outbox 的 checkpoint/冷重启恢复；注册文件中的历史 phase 名 `full-checkpoint-pilot` 不能扩大其验证范围。512MiB 是显式 checkpoint 上限与静态预算，小夹具恢复测试也不冒充350k云端恢复。pilot完成后才登记 W128/W256/W128/W256 交替对照；双方统一 maxSessions256、节点SHARED、原128KiB接收、sync2、相同新 artifact 与准备 SHA。

每 worker FIFO保持64意味着总FIFO为8,192/16,384；它是整个并发配置的比较，不将全部变化归给纯在途窗口。每轮350k原始CSV保留在本地，Git保存无损 `arrivals.csv.gz` 与原始/压缩 bytes/SHA 清单；`python3 scripts/archive-capacity-arrivals.py restore RUN_DIR` 可精确恢复再运行原分析器。旧轮次原CSV不改写。所有过载、无效或失败数据也按同口径保存。

35秒 pilot 已完成：350,000 个计划到达全部最终接受，窗口内 goodput **9,998.086/s**，全量计划到达至确认 p99 **38.016ms**，drain **6.901ms**，未发送、unknown、业务拒绝和 server error 均为0。该点符合现有 `OBSERVED_STABLE_WINDOW` 判定，只证明这个有限窗口；不表示已找到上限或已达成长稳 SLA。准备 SHA 为 `2c6847a5eb5bbdf0674a74c63f92dfb274fdc626ddfbcd540866596979e46bc4`，相对旧 profile 已变化，不能把新旧点直接拼成同一配置曲线。正式四轮已登记为26,000/s、每轮350,000个到达，结果另列。

另行登记的[完整checkpoint与冷JVM恢复](../evidence/2026-10-23/runpod-optimization/window350k/checkpoint/README.md)已实际完成。三节点均写入匹配的官方service/consensus snapshot，原PID停止后以相同argv启动三个新JVM，均报告恢复所选快照；再通过公开协议完整读取57,682,277字节core，174.006秒内逐字节匹配固定SHA。业务序列350167/700267/700201、outbox exported0/pending700267和端点1..700267保持一致。独立审计通过172项断言与123个输入SHA，最终六次精确进程停止均通过。它验证完整应用checkpoint解码、core及outbox游标/数量/端点，没有独立逐条枚举700267个outbox payload，也不是断电、Pod重启或backup恢复测试；174秒是完整core读取校验耗时，不是服务恢复RTO。

第一轮W128完成验证但过载：窗口goodput14,942.200/s，已接受条件p99643.155ms，140,563条未发送，初次与最终unknown均为0。同步槽位平均占用99.9625%，FIFO等待p99634.229ms，初次API执行p9914.207ms。第二轮W256出现563个初次unknown，307个在原轮次内恢复，256个最终unresolved；只返回3,307个已接受回复，346,437条明确未发送。该轮验证失败、分类INVALID，后两轮未提交，不能给出四轮并发收益结论。

独立[全量缓存审计](../evidence/2026-10-23/runpod-optimization/window350k/tool-validation/unknown-audit.json)核对了原350k行与完整终态core：全部3,307个已知回复的业务结果逐字段等于终态缓存；256个unresolved中252个已缓存为accepted，另外4个只是在该snapshot中缺席，不能据此推断未执行。原校验器先重放confirmed-only集合，再检查allKnown；漏掉已执行但未确认的命令会使后续订单号/commandSeq错位，产生误导的business mismatch。修复将完整结果集合检查移到重放之前，保持unresolved失败与原始CSV，不将离线缓存发现回填成客户端确认。独立同身份恢复及其结果另存。

用户明确批准后，独立[同身份恢复](../evidence/2026-10-23/runpod-optimization/window350k/unknown-recovery/README.md)已完成：live pre-core先与冻结快照完全一致，再核对256个原业务身份。252个返回缓存结果，另外4个以同key完成恢复，实际增加4个命令与8条事件；最终canonical core、资产和新增事件payload全部通过，未ACK，outbox pending7385→7393。原容量轮次仍为INVALID，原CSV和unknown计数未改。helper执行9.507秒不含编排，不能当作容量或故障恢复SLA。

严格窗口[传输归因](../evidence/2026-10-23/runpod-optimization/window350k/analysis/failed-window-attribution-summary.json)显示W256 node0自有UDP drop增量233,810、负载端498,367；node0 NAK sent增量1,722,367。负载端drop集中在共享ingress publication的source/control socket，node0也包含ingress与consensus发送通道control socket；三节点固定LOG端口该窗口drops为0。256个session在窗口开始存在，未见session-cap拒绝；driver线程接近1核，线程/FD采样未触上限。这些关联不能证明唯一原因，也不把NAK次数等同业务丢单。

## NAK延迟交替对照

同一节点/负载源 `ab6fc73731642d0d17a242a930a2cb60aba11e16`，按1,000ns → 100,000ns → 1,000ns → 100,000ns运行26k/s、350k到达、W256/Q64。节点与负载共享driver同时设置，retry ratio保持100；固定leader0、sync2、2GiB、原131072接收请求和准备SHA。实际JVM参数、启动日志及负载driver context均独立核验。它是两端修复反馈延迟的整体对照。

| 顺序 | NAK delay | 窗口确认/s | 已接受条件p99 ms | 最终未发送 | 初次/最终unknown | 判定 |
|---|---|---:|---:|---:|---:|---|
| A1 | 1,000ns | 129.406† | 43,137.974† | 346,245 | 695 / 256 | INVALID |
| B1 | 100,000ns | 10,013.491 | 2,043.657 | 198,630 | 0 / 0 | 有效，过载 |
| A2 | 1,000ns | 109.571† | 42,766.794† | 346,333 | 726 / 256 | INVALID |
| B2 | 100,000ns | 9,989.274 | 2,077.543 | 198,936 | 0 / 0 | 有效，过载 |

† A两轮只有客户端报告的诊断数，没有通过完整业务正确性验证，不能称为已验证吞吐，也不能用B/A比值宣传容量倍增。四轮全量接受p99均不可用；排空后成功不回填窗口吞吐。A两轮的最终256个unknown保留原状，没有沿用前一轮针对特定256个身份的恢复授权。

B两轮完成canonical终态、逐条业务回复和资产验证，且初次/最终unknown均为0，表明同条件下未知结果崩溃得到重复改善；但每轮仍有约199k未发送，平均活跃槽位约255.876/256，不能称10k/s稳定容量。此前B的35秒10k/s pilot也有254条未发送、p991614.795ms，属于有效非稳定点。全部5次实际尝试与350k原始行分别保留在[NAK证据](../evidence/2026-10-23/runpod-optimization/nak/README.md)。

冻结的[正式归因报告](../evidence/2026-10-23/runpod-optimization/nak/analysis/attribution-summary.json)核对138个输入/工具SHA。严格窗口内A两轮NAK约131–133k次/s，node0 socket drops230486/231512、load543700/513617；B约1.02–1.04k次/s，node0 drops7300/6961、load0/0。B的node0剩余丢包集中在ingress；不能把负载端归零扩大为全网络无丢包。A末段append−commit差897600/919392字节，B窗口最大14784/12864字节。两组driver前缀线程都约1核，B的consensus线程约0.946/0.943核；总CPU配额未持续耗尽，不足以排除局部线程、调度、传输或持久化等待。

## 物理session与网络所有权对照

新源 `e57e341909a49692b9ecbf9693803ed62a240b06` 已完成128项Java测试和不可变上传，完整350k pilot及正式四轮对照均已完成，四轮全部有效且过载。两组统一W128、128个独立producer身份、每worker FIFO64和总FIFO8192、一个共享MediaDriver、NAK1000ns、相同2GiB/sync2节点与fixture；direct保留128个物理Aeron session，multiplexed使用一个session和一个网络owner，逻辑在途数不变。session数量、网络所有权与分发方式共同变化，不能将收益单独归于撮合引擎。

先执行35秒、350k全部接受的multiplexed pilot，正确性、时间有效性及零未发送/拒绝/error/最终unknown均通过后才登记26k/s的A/B/A/B。每次API调用有独立发送截止时间；同key重试复用pending与correlation，截止后只轮询响应，不自动延长发送期限。新的失败路径先保存CSV/backlog/failure再抛出原错误，未知终态继续失败。测试与[预登记协议](../evidence/2026-10-23/runpod-optimization/pipeline/PRE_REGISTRATION.md)不替代实测结果。

该pilot的350000条全部接受、0未发送/拒绝/error/初次与最终unknown；窗口goodput **9997.771/s**，全量计划到确认p99 **41.871ms**，drain **6.684ms**，分类`OBSERVED_STABLE_WINDOW`。完整57,682,277字节终态与同MatchingEngine重放的expected逐字节相同；172.049秒终态验证在到达窗口外。独立一次流式审计核对全部350k行及原始/压缩SHA，平均初次API执行6.297ms、窗口平均活跃62.963/128槽位。独立[归因](../evidence/2026-10-23/runpod-optimization/pipeline/analysis/pilot-attribution-summary.json)核对45项input/tool SHA；35秒pilot只证明新路径在这一点的有限稳定性，不能与旧profile拼接、提前断言26k性能或替代重复对照。完整方法与实际进度见[pipeline README](../evidence/2026-10-23/runpod-optimization/pipeline/README.md)。

| 顺序 | 物理session | 窗口goodput /s | 已接受条件p99 ms | 未发送 | 判定 |
|---|---:|---:|---:|---:|---|
| A1 direct | 128 | 14,810.491 | 607.846 | 142,336 | 有效，过载 |
| B1 multiplexed | 1 | 14,908.549 | 668.094 | 141,037 | 有效，过载 |
| A2 direct | 128 | 14,829.806 | 635.632 | 142,092 | 有效，过载 |
| B2 multiplexed | 1 | 15,373.354 | 608.066 | 134,745 | 有效，过载 |

四轮均为26k/s、350k计划到达，逐条业务回复、canonical终态、资产、配置与leader校验通过；初次/最终unknown、业务拒绝和server error全为0，全量接受p99全为null。B对对应A的goodput只高约0.66%/3.67%，条件p99一次升高、一次下降，没有建立新的稳定容量或一致的p99改善。前三轮平均活跃槽位均约127.95/128，平均API执行约8.59–8.65ms，与约14.9k/s的同步窗口关系相符；这不识别8.6ms的唯一来源。独立18k/s A/B/A/B已登记并执行，用于补相同业务配置的更低负载点；不把26k过载goodput称作稳定吞吐上限。

独立[正式归因](../evidence/2026-10-23/runpod-optimization/pipeline/analysis/attribution-summary.json)核对140个raw/tool SHA，确认资源下降可重复：node0 JVM由A的2.562/2.589核降到B的1.263/1.394核，负载由4.072/4.105核降到1.724/1.855核；node0 FD/UDP由553/134降到45/7，负载FD/UDP由400/129降到19/2，线程约299降到172–175。严格窗口内node0/load/node2四轮owned socket drops均0，node1日志socket A为315/91、B为0/0，未出现NAK风暴。node0总quota未持续耗尽，A限流24.53/1.94ms、B为0；累计限流不是单请求延迟。单session在本配置下节省资源成立，稳定吞吐与p99改善仍未成立；下一独立node-only park因子两组统一保留multiplexed路径，分别比较1ms与100µs上限，未把两种改动的总变化归给单个因素。

## 同配置18k边界复测

同一e57 node/load、W128/Q64配置的18k/s、每轮350k到达A/B/A/B已全部完成。窗口goodput依次为 **14,514.377 / 14,850.720 / 14,799.497 / 11,420.897/s**，已接受条件p99为 **645.285 / 621.434 / 628.043 / 1,101.152ms**。四轮canonical、配置与leader校验通过，unknown、业务拒绝和server error均为0，但均有队列满未发送，全量接受p99均为null，排空526–709ms超过194.444ms门槛，全部过载。B2明显退化完整保留，没有建立稳定18k容量或可重复的吞吐、p99改善。原始证据和逐轮审计见[cap18报告](../evidence/2026-10-23/runpod-optimization/pipeline-capacity/README.md)。

平均活跃请求仍约127.94–127.96/128槽位；B2平均API执行从B1的8.605ms升至11.183ms。核对169项input/tool SHA的[正式归因](../evidence/2026-10-23/runpod-optimization/pipeline-capacity/analysis/attribution-summary.json)显示，B2匹配的owned UDP drops均0，但node0 NAK sent从B1的54升至41,364；约18秒窗口内node0相关线程累计runqueue等待也增加，cgroup限流仍0。这些支持检验传输恢复与调度等待，不能唯一定位丢包、宿主机或持久化瓶颈，也不能把累计等待当作单请求p99。multiplexed的CPU/FD/socket节省仍重复出现，资源收益与稳定容量分别验收。

下一node-only试验只改变节点最大park：1ms与100µs，双方固定multiplexed负载及其余配置。新节点87ad通过132项Java测试和三节点不可变上传校验。100µs的严格10k/s、350k pilot已完整通过：全部接受，窗口goodput9998.771/s，全量p9923.711ms，drain8.759ms，初次/最终unknown、未发送、拒绝和server error全0。独立归因核对63项input/tool SHA；该pilot没有同新artifact的A控制组，不能单凭旧pilot的差异声称单因子收益。26k/s正式A/B/A/B随后登记并启动，结果另报。实际方法、独立node/load/analysis身份及审计工具失败记录见[idle报告](../evidence/2026-10-23/runpod-optimization/idle/README.md)。

## 已完成的代码验证

新负载版本从已提交源码 `git archive` 建立隔离 checkout，运行全部 Java tests 与 `:cluster:installDist`，记录 **109 tests、0 failures、0 errors、0 skipped**，见 [Java 验证](../evidence/2026-10-23/runpod-optimization/tool-validation/java-tests.json)。测试覆盖共享 driver 下独立 session/Aeron、关闭一个客户端后其他客户端继续工作、连接失败不关闭借用 driver、错误模式/固定端口拒绝、运行元数据及固定到达调度等路径；这些检查不替代云端容量测量。

独立网络与线程节点包分别完成 110 / 112 项 Java tests，均无失败或跳过；构建日志、XML、类内容比对与三台 launcher 校验保存在各自 tool-validation / deployment receipts。这些验证仍不替代云端容量测量。

新的独立流式证据分析器已完成15项定向测试，并对三个冻结的真实350k案例（multiplexed pilot、direct A1、NAK失败A1）逐trial全部字段比对一致，没有排除任何指标、判定、异常或input SHA。三个案例只运行新工具，既有摘要和旧工具不重跑。新进程耗时6.061/9.664/4.861秒，峰值RSS80,412,672/45,056,000/47,415,296字节，见[完整验证收据](../evidence/2026-10-23/runpod-optimization/tool-validation/streaming-analyzer-validation.json)。这是后处理效率验证，不是云端撮合吞吐收益或与旧工具同时测得的加速倍数；当前26k正式四轮仍保留原分析器。

新分析器与旁置legacy依赖从已提交源码`3fd86fe535fc0858e300e0337d4da154f622ae32`另建不可变本地postprocessor，分别记录source archive、两文件SHA、Python二进制/版本和parity receipt；analysis身份独立于e57 node/load/buildTools。18k四轮在原26k完整归档、配置与清理通过后统一使用独立31e4后处理；e57运行代码和原26k摘要保持原身份，旧摘要不被覆盖。

归因观察器在三台 Linux Pod 各完成 14 项测试与有界采样 smoke：[node0](../evidence/2026-10-23/runpod-optimization/tool-validation/attribution-node0.json)、[node1](../evidence/2026-10-23/runpod-optimization/tool-validation/attribution-node1.json)、[node2](../evidence/2026-10-23/runpod-optimization/tool-validation/attribution-node2.json)。配置验证器另用四组历史真实 command SHA 回归，拒绝 mode/count 错配、部分运行声明、非法 JVM 属性，并验证显式默认属性同样进入 NUL 分隔的完整参数摘要。

## 三个“一亿”目标的验收边界

用户要求的三个目标分别为累计一亿成功新命令、每秒一亿成功新命令、一亿同时在线连接。当前实验均未证明这三项；它们需要分别登记接口、持续时间、错误预算、延迟目标、账目和资源口径。

### 累计一亿成功新命令

当前 retained orders 包括成交、取消或过期订单且不会自动回收，旧测试 profile 上限为200k、新350k工作负载 profile上限为360k；outbox也有明确上限。单纯提高 MAX_ARRIVALS、定期重置后把计数相加、丢弃事件或把重试算新订单，都不能证明连续接收与可恢复处理一亿订单。

长期实现至少需要三个有明确恢复合同的部分：

1. 活跃撮合状态与不可变订单/成交审计历史分离；终态回收保留 client-order 唯一性、取消查询和引用规则，不能只从订单 Map 删除。
2. 持续消费 outbox，外部事件、投影和消费游标原子提交后才 ack；checkpoint 保存可验证的 exported cursor 与保留边界，积压时执行明确背压，不能先 ack 再持久化。
3. 明确 producer high-water、幂等结果保留窗及过期请求语义。已过重试保留窗的旧请求可拒绝或查询持久审计记录，不能被误当作新命令再执行；恢复后规则必须保持。

真正验收应在持续运行、跨越多次清理/checkpoint 和至少一次故障恢复的情况下，由独立审计游标与唯一业务身份核对 **≥100,000,000 个 accepted new commands**，同时证明资产守恒、事件连续、无重复执行、最终未知结果归零，保留拒绝/丢弃/重试与窗口吞吐曲线。有限 isolated epochs 的累计量可单独报告，不能称作不间断服务运行。

代码级复核给出的最小后续方案是显式版本化的long-run-v2合同，目前尚未实现。现有[orders/clientIds](../core/src/main/java/io/vectormatch/core/MatchingEngine.java)同时承担全历史client-order唯一性，直接删终态记录会改变业务语义。v2可限定client-order-id由account/固定producer/requestSeq规范派生，永久保留producer high-water；旧任意字符串ID接口继续保留原合同。完整command/result审计记录必须与状态机同次提交，覆盖新请求的业务拒绝；当前Event尚无producer/request身份，不足以单独审计一亿新命令。

已有[projector](../projector/src/main/java/io/vectormatch/projector/ReliableProjector.java)和[PostgreSQL事务](../projector/src/main/java/io/vectormatch/projector/PostgresEventStore.java)遵循commit后ACK，可扩展为结果账本、历史订单和cursor同事务提交。随后新增绑定stream lineage与受信consumer的durable watermark，以及确定性的有界replicated prune：只清理closedEventSeq不大于durableAck的终态，保留活跃book、余额、FIFO、订单/事件序列和幂等high-water，并版本化checkpoint。缓存外的STALE_SEQUENCE代表这次未重新执行，不能推断原结果失败；须按原身份查持久账本，不能换ID补单。这些均为待实现事项，现有数字ACK自身不是独立的外部持久化证明。

应先以小retained/outbox/cache连续跨越多轮上限、GC、checkpoint和冷恢复，并在数据库commit前后、ACK丢失、GC前后注入故障，对照不GC参考的每个新业务结果、active book和资产，验证旧身份及冲突载荷永不二次执行。通过后才运行单stream、不reset的一亿fresh accepted Place+trade审计。当前fixture仅380k maker lots与64买家各1.9B quote，也必须更换：同单价/单lot工作负载至少需100000100 maker lots及每买家15.625B quote，另计预热与分配余量。控制命令、重试、缓存回复不计入一亿成功新订单。

仅按历史 13k/s 估算，纯发送一亿条也需约 2.14 小时；这是算术下界，未含当前大约分钟级的准备、快照和终态验证，更不是已测可持续吞吐或完整费用报价。现有逐 190k 轮次流程不能据此承诺在总预算 20 美元内完成该验收。

### 每秒一亿成功新命令

当前约百字节的命令编码意味着，仅入口 payload 已是每秒数十 Gbit 量级，还需响应、复制和协议开销。当前三 Pod 的测量不能外推至这个目标。后续可按独立交易标的分片并分离接入/行情分发，但单订单簿的价格时间顺序、账户资金预留与跨片风险仍须有明确协议；把单片数字乘以假设片数不构成集群实测。

验收必须由独立分布式发生器观测整个系统的 **实际** 窗口 accepted-new-command 总数、分片分布、排队、p99 和故障后账目，公开网络/CPU/持久化资源以及热点单簿表现。纯内存循环、UDP 包数、批次中名义命令数和关闭同步持久化后的数字都需另列范围，不能替代该目标。

### 一亿同时在线连接

当前 128 个 Aeron session 不等于公网 TCP/WebSocket 连接容量。这个目标需要独立的接入与订阅网关层，实测每连接内存、fd、心跳、重连风暴、慢消费者和扇出开销；交易 session 与只读行情连接应分别计数，并保持用户可见的连接/订阅语义。

验收须证明同一时间窗内一亿个独立活跃端点完成规定的握手、心跳与收发，报告断线、丢消息、重复、延迟及资源费用。累计建连次数、模拟 ID 数或同一连接上的虚拟订阅不能直接当作一亿同时在线连接。本轮三 Pod、总预算 20 美元无法诚实验收这两个瞬时大规模目标，状态保持未验证。

## 证据、预算与服务恢复

原始目录为 [isolated](../evidence/2026-10-23/runpod-optimization/isolated/) 与 [shared](../evidence/2026-10-23/runpod-optimization/shared/)，准备状态、到达明细、backlog、进程参数、CnC、线程/socket 观察、官方 members、终态核对和无效点均保留。代码和已完成的合成证据持续进入原 private repo。

本轮复用原三台 Pod，不增加资源；总项目预算为 **20 美元**，按合计保守报价 **1.56 美元/小时**估算，登记保留 **2 美元恢复余量**，不是另加预算。费用估算不是供应商结算账单或平台硬上限。最终累计费用与原应用恢复结果，在本轮结束后的实际记录完成时更新；目前不声称已完成本轮恢复。

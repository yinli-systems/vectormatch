# 下一个单因素实验的优先级（只读建议）

已测：6033长窗33,792@500/s，12维护周期，0迟到/UNKNOWN/拒绝/未发送；all-arrival p99=554.293743ms、窗口goodput=499.9556107954545/s。已有raw032e43记录维护墙钟6.671297853s；RPC累计33.231341689s是重叠区间和，不能当墙钟或磁盘耗时。维护6850RPC=FetchEvents4225+ArchiveChunk2589+控制36。这里只引用原摘要，不新增CSV统计或容量结论；977的owner-cap ABAB由其他任务独立完成，下面不猜其结果。

1. **首选：事件页16→32，其他因素固定。** 确定约束是Wire.fetch上限16（RetentionWireV3:132）、Reply.Events/decoder同为16（RetentionReplyV3:136/252）、coordinator每页16（Maintenance:237）。ReplicatedOutbox:41每次fetch从队首遍历，页数减少也减少重复前缀遍历，但本实验不同时改索引。一个6144事件满周期页数由384→192是纯算术预测，不是性能实测。改动面中等：同一新artifact支持显式16|32，默认16，双方同profile/页外全部参数；Plan/codec/raw审计必须理解选中页长。
   编码源码给出保守边界：每事件8个long+2个byte+4字节长度+最多128 UTF8字节detail=198B；完整Events外层含最大scope/hash/error/counters/页头为427B，因此32项≤6763B，另加Aeron32B会话头≤6795B，仍低于既有common6951B。**这是源码上界推导，尚未通过新codec最大合法UTF8夹具/JAR证明**；必须先做32项全字段边界、非法33、截断/错范围/Unicode字节上界测试，保留8192回复/MTU1248和实际Image几何，不截断detail。预期收益来自减少复制查询/往返，不承诺耗时减半。风险中等，关键是扩大count合同与失败后的完整原始身份保留。

2. **其次：整波8→滚动补充，保留总read credit=8。** Maintenance:150–168先reserve整波、flush全部original、arm全部，再FIFO等待/写reply+timing/consume，整波清空才生成下一波。确定存在整波屏障和FIFO队头等待；现有offered HWM8不证明持续满窗或证明此屏障已成瓶颈。单改调度为完成并经证据消费一槽后补一槽；只能同kind/同phase，不能改RPC数量、deadline、允许offer次数、writer或business暂停策略。修改面和正确性风险高于页长：≤8必须包括reserved、已完成未消费；每个refill先保留并flush原wire再arm；OOO按correlation+descriptor/offset/event range匹配并完整覆盖；同一个失败bundle必须含所有仍保留originals。新元数据占用先计入共同Plan，不扩大现有硬上限。

3. **最后：每owner turn的pollEgress调用预算1→最多4，遇0提前停。** Transport:87目前每次poll只调用一次AeronCluster.pollEgress；[官方固定1.53.3源码](https://raw.githubusercontent.com/aeron-io/aeron/1.53.3/aeron-cluster/src/main/java/io/aeron/cluster/client/AeronCluster.java)的private FRAGMENT_LIMIT=10，pollEgress返回值通常是fragment work且还加state work。当前Owner:620–630在work>0时直接下一轮，不park；所以不能把10 fragments解释为10完整reply或每十个fragment必睡1ms。它不是Context可调的fragmentLimit；最小候选是同一个owner线程里有界重复原API，而不是绕过Assembler/状态机直接pollSubscription。代码面小，但收益证据最弱；可能反而延后业务offer、keepalive或deadline检查，必须保留公平性上限、全部Header/Image/correlation检查和原state/leader处理。park上限、页长、window、batch flush都固定。

force事实与诊断：原writer快照24submitted/completed，outstanding HWM1。源码Writer:100–119每job先payload force(true)+全量readback/hash/再校验，然后receipt再force(true)后才完成ticket；正常完成路径对应24个payload force+24个receipt force的API调用，不是已观测48次独立物理磁盘flush。现有receipt只量payload.forceNs，writeNs含open/写入，readbackNs还含close/afterForce/hash/验证；receipt force和前置验证没有单独时长。不能据此把Archive总writepath或RPC重叠和认成fsync。下面仅列已有24行原值，不计算新均值/p99，也不建议取消force/readback或先ACK。

最小后续诊断：在所有对照臂用同一有界观测，分别计逻辑RPC/实际offer/完整reply、波次间隙与retained/armed/offered credit、每turn poll调用/返回work/完整callback、writer payload write/force/验证/receipt force。poll返回含状态处理，不能直接叫精确fragment数。读票完成→证据消费与真实正offer→callback两个区间要分开。资源收据09:36显示perf_event_paranoid4、无perf可执行文件、硬件采样未证明；jcmd/jfr存在仅说明工具文件存在，未验证attach/事件/开销。现阶段不安装/运行profiler；若以后批准JFR，先单独空闲验证支持的事件与权限，再决定是否适合统一观察器。32affinity是允许逻辑CPU，cpu.max=max100000不是32个独占物理核保证。

所有候选共守：同新artifact两臂、相同完整finite Plan/配置与原始点保留；归档/事件exact prefix+链/hash+force/readback完成前，不允许ArchiveCommit或EventAck；任何未决read/控制/UNKNOWN挡ACK和新cycle；最多8retained含完成未消费；correlation/原wire/deadline/最多4offer不可续期或换新身份；业务global/per-producer retention credit不得因超时提前回收。维护时仍暂停业务dispatch但arrival clock/Q64计数继续，全部时间进入延迟/丢弃；实际leader/term、Image/header、canonical reference、三节点快照、raw完整TAR及PG57/989保护不变。现有有限维护journal仍非100M回收方案。

已有writer receipt原值（ns；最后列包含验证，不是纯读取延迟）：

|payload|bytes|writeNs|payloadForceNs|force后到验证完成Ns|
|---|---:|---:|---:|---:|
|0001-archive.bin|1432233|673852|5375107|21638187|
|0002-events.bin|559632|230847|1743320|8471461|
|0003-archive.bin|1437510|928439|4813314|29441395|
|0004-events.bin|559872|327816|1784020|11893490|
|0005-archive.bin|1437510|341446|1860879|26957684|
|0006-events.bin|559872|314706|1843838|11776012|
|0007-archive.bin|1437510|489615|2076415|26561509|
|0008-events.bin|559872|316426|1929768|11846461|
|0009-archive.bin|1448250|703862|3215972|32585769|
|0010-events.bin|559872|300516|1857009|12824050|
|0011-archive.bin|1449798|545193|3338041|31101856|
|0012-events.bin|559872|330436|1801529|13611760|
|0013-archive.bin|1449798|341156|4357709|31985086|
|0014-events.bin|559872|299486|1835279|13023847|
|0015-archive.bin|1449798|389235|3354301|28287659|
|0016-events.bin|559872|331006|1916508|13788628|
|0017-archive.bin|1449798|420095|3109033|28194591|
|0018-events.bin|559872|295997|1908667|13214706|
|0019-archive.bin|1449798|384466|4184001|27865773|
|0020-events.bin|559872|313616|1905858|12513943|
|0021-archive.bin|1449798|309906|2023436|28142961|
|0022-events.bin|559872|228237|2926746|9465779|
|0023-archive.bin|1802|154408|1640961|231007|
|0024-events.bin|688|82559|1551892|118179|

# 保留同步语义的批量业务候选：实施合同

状态：首阶段功能候选已冻结为 `973ff8f9bc4d9266c52d21866480dd45b31c39f9`，并 push 到 `codex/retention-batch-v3`。它基于 `9fda247d392432761a670de7c4d8040c7caff283`，尚未提升默认配置，也尚未测得性能收益。三节点均在本地同一机器，功能及原生归档证据归入 `evidence/2026-10-24/runpod-cpu/retention-batch-v3`；云端容量对照仍待新 owner 完成。

动机来自[完整四轮Archive遥测](../evidence/2026-10-24/runpod-cpu/derived/archive-path-client-abab-all4/README.md)和[独立八点force(true)诊断](../evidence/2026-10-24/runpod-cpu/force-path-experiment/comparison-r2/README.md)。后者单写线程force中位数1.35–1.40ms，三写线程2.51–2.77ms、行p99为4.65–4.99ms。它们支持优先验证批量提交，不能证明唯一硬件瓶颈或预测交易收益。现有V2的18k/s有限稳定点仅作背景，新V3必须重建同源对照。

## 首版消息与执行合同

首版每条业务请求最多4项，完整请求仍不超过4096B、完整回复不超过8192B；同时按实际编码字节装包。完整解码、canonical校验、逐项格式、重复producer检查和回复最坏空间预留，都必须在首项mutation之前完成。

实际回复逐项保留index、完整 `(account, producer, requestSeq)` 身份、command SHA、完整Result及reason、replayed、执行状态和counter frontier。byte-exact测试构造出可达到的完整最大请求2639B及最大回复4315B；回复为公共411B加4×976B。reason同时受原有256个UTF-16单元和1024B UTF-8上限约束，有效严格UTF-8可达768B；因此替换设计阶段5699B的保守估算。编码前校验最坏回复空间，不截断reason、不丢项。缓存中不兼容UTF-8的旧reason在批量入口首次使用及恢复后预检，拒绝发生在mutation之前。16项和分页回复不在首版范围。

采用顺序prefix-commit，明确不承诺批事务原子性。每项即时调用现有preview/apply；不得先preview全部Admission，因为首项后其余token的generation/sequence已失效。普通业务拒绝仍返回完整逐项业务结果。第j项遇到history/outbox等资源背压时，前缀保持已执行，第j项标为“未执行背压”，后缀标为“未尝试”。

重放无新业务事件、无新maintenance journal，沿用service现有applicationMutation语义；不得额外为整批计一次mutation。回复丢失后保留原identity/payload，逐项维持UNKNOWN并恢复，不能更换业务身份或假定整个batch回滚。首阶段只实现功能合同，不做性能宣传。

## 结果保留与新owner

每batch同一 `(account, producer)` 最多一项，每producer最多一个未终态命令。现smoke只有16 producers、每producer缓存8、global缓存64，不能作为W128容量profile。

global cache大于W128仍不充分：某producer丢回复时，其他producer持续推进仍可能驱逐其结果。两arm都必须有相同retention credit：以最早未终态首次业务offer为floor，对其后首次offer数量施加严格的全局保留窗口边界；达到边界先停止新offer并用原身份解析UNKNOWN。重复/invalid可保守占credit，禁止out-of-band业务。没有credit或cold-result lookup，只能承诺不会二次执行，不能承诺所有UNKNOWN可恢复。

容量实验需要另做有界owner。A/B固定逻辑W128、任务arrival queue Q64；单独记录每worker FIFO、物理session、MediaDriver、内部pending上限、retention credit和flush deadline。内部8192上限不等于任务Q。现RetentionClientV3是单物理inflight，直接比较它的batch1与batch4会改变逻辑窗口，不属于纯装包对照。

待构造器及实际边界测试确认的profile例：accounts8、producers256、hot orders8192、global results512、每producer results16；pending commands4096/events8192/serialized24MiB；outbox8192；maintenance producers16/cache128/journal4096条及4MiB。现保守公式得combined上界43,739,648B，低于64MiB；这只证明编码预算，不保证所有fanout都能装满4096条。全部字段进入新fingerprint，仍逐项检查实际字节、事件和outbox余量。

## Archive保持不变

继续使用sync2和force(true)。固定Aeron1.53.3的[RecordingWriter](https://raw.githubusercontent.com/aeron-io/aeron/1.53.3/aeron-archive/src/main/java/io/aeron/archive/RecordingWriter.java)在block写完后执行force；[RecordingSession](https://raw.githubusercontent.com/aeron-io/aeron/1.53.3/aeron-archive/src/main/java/io/aeron/archive/RecordingSession.java)在blockPoll返回后推进recorded position。fileIoMaxLength是上限，不能假设调大即可凑满一批。业务batch可能摊薄每次持久化的逻辑命令成本，但不能声称一批必然只force一次，fragment/padding/poll边界仍可拆block。

延迟Archive内部force还涉及recorded/commit position和恢复协议，是另一项依赖实现变更，不纳入首版。

## 一亿订单仍有独立边界

当前smoke maintenance journal2048条，代码硬上限10000条且不回收；维护重试、冲突和stale也追加journal。按当前512条history容量，一亿首次业务命令至少约195312次archive commit；若配相近数量event ACK，约390624条维护记录，远超当前限额，字节限额也可能先到。需要外部验证后的journal分段归档、ACK、checkpoint锚点和冷结果查询。批量入口不能替代这些工作。

business热路径没有O(journal)扫描；snapshot/restore和Position(stateHash)会全扫，不应每batch查询Position。当前每个3072B archive chunk重新编码完整前缀，导出约O(S²/chunk)，需另做有界不可变导出缓存或分段编码。

## 验收与对照顺序

1. 逐项reference与完整snapshot一致：批中资源耗尽、malformed尾项零mutation、UTF-8最大回复、重复/冲突、UNKNOWN/丢回复、cache floor、leader切换、checkpoint冷启动。保留所有失败及完整原生证据。
2. 新profile/有界owner/retention credit分别验收；容量harness以逐逻辑命令计数，记录scheduled latency、not-sent、reject、UNKNOWN、batch大小与装包等待。不能把batch数当订单数。
3. 同一候选artifact/profile/client运行batch1/4的完整A/B/A/B，固定leader、sync2、逻辑窗口、队列、到达率及flush deadline。所有已登记点保留，未知未闭合、canonical不一致或证据不全时阻断后续点。
4. 只有重复改善且所有正确性门通过才提升默认配置；累计一亿订单、一亿/秒、一亿连接分别验收，当前均未证明。

本阶段没有创建云资源；现有CPU探针全部停止，Pod继续按用户授权保留。

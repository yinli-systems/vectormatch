# NAK 延迟实验：五轮结果

**把节点和压测客户端的 unicast NAK 延迟同时从 1,000 ns 提高到 100,000 ns，在两组正式对照中都缓解了反馈拥塞与未决请求崩溃；尚未证明稳定容量提升。** B 的两轮正式测试均完成业务校验、最终 unknown 为零，但约 57% 的到达未被发送，26,000 条/秒仍明显过载。A 的两轮均留下 256 个 unresolved，不能作为经过业务正确性验证的容量点。

## 对照条件

[正式计划](plan.json)按 A1 → B1 → A2 → B2 执行；每轮 350,000 条到达、26,000 条/秒，精确到达窗口 13.461538461 秒。[B pilot](pilot-plan.json)为 10,000 条/秒 × 35 秒，同样完整运行 350,000 条。A/B 的节点与客户端 NAK 延迟分别为 1,000/100,000 ns，retry-delay ratio 均为 100；两侧同时变化，无法单独归因于其中一侧。

五轮使用同一节点及负载构件，源码为 `ab6fc73731642d0d17a242a930a2cb60aba11e16`，见[发布身份](node-release.json)与[部署清单](node-deployment-manifest.json)。固定三节点、leader 0、节点及负载堆各 2 GiB、Aeron 1.53.3、节点 MediaDriver/Archive 均为 SHARED、sync level 2、接收缓冲请求 131,072 字节。W256 为 256 个独立 Aeron 客户端/会话，共用一个客户端 MediaDriver；每 worker 同步单请求，FIFO 64，总等待槽 16,384。状态配置为 `capacity-350k-v1`；准备状态 SHA-256 全部为 `2c6847a5eb5bbdf0674a74c63f92dfb274fdc626ddfbcd540866596979e46bc4`。118 项 Java 测试及最终 64 项 Python 测试通过，见[Java 回执](tool-validation/java-tests.json)、[Python 回执](tool-validation/python-tests.json)。

## 实测结果

延迟从**计划到达时刻**计到收到接受回复，包含排队与请求处理，采用 nearest-rank p99；窗口结束后的回复只计入总数。

| 轮次及原始结果 | 接受回复：总数 / 窗口内 | 窗口内回复/秒 | 条件 p99（ms） | 未发送 | 最终 unresolved | 判定 |
|---|---:|---:|---:|---:|---:|---|
| [B pilot](pilot100us/runs/k-pilot-100000ns-10000-w256/result.json) | 349,746 / 340,808 | 9,737.371429 | 1,614.795477 | 254 | 0 | 有效，非稳定 |
| [A1](delay1000/runs/k-nak1000-26000-w256-r1/failure.json) | 3,499 / 1,742¹ | 129.405714¹ | 43,137.974020¹ | 346,245 | 256 | 无效，校验未完成 |
| [B1](delay100000/runs/k-nak100000-26000-w256-r1/result.json) | 151,370 / 134,797 | 10,013.491429 | 2,043.656586 | 198,630 | 0 | 有效，非稳定 |
| [A2](delay1000/runs/k-nak1000-26000-w256-r2/failure.json) | 3,411 / 1,475¹ | 109.571429¹ | 42,766.794118¹ | 346,333 | 256 | 无效，校验未完成 |
| [B2](delay100000/runs/k-nak100000-26000-w256-r2/result.json) | 151,064 / 134,471 | 9,989.274286 | 2,077.542968 | 198,936 | 0 | 有效，非稳定 |

¹ A 的回复计数、速率和延迟仅为客户端观测，未经完整 canonical 业务校验，不能称为已验证业务吞吐。**五轮 all-offered accepted p99 均为 `null`**：表中 p99 只覆盖收到接受回复的子集，未发送和未决到达没有虚构的零延迟。

A1 初始 unknown 695 个，随后解决 439 个；未发送拆分为 FIFO 满 331,618 条、被 unknown 阻塞 14,627 条。A2 对应为初始 726、解决 470、FIFO 满 331,885、阻塞 14,448；两轮各保留 256 个未决原始身份。校验器触发精确 UNKNOWN guard，跳过不完整的确认集回放；[A1 配置回执](delay1000/runs/k-nak1000-26000-w256-r1/configuration-verification.json)和[A2 配置回执](delay1000/runs/k-nak1000-26000-w256-r2/configuration-verification.json)仅证明配置，明确 `businessCorrectnessVerified=false`。这不构成撮合业务错误的证据。

B pilot、B1、B2 均无初始 unknown、最终 unknown、业务拒绝或服务端错误；接受回复、最终核心状态、账户守恒、事件序列与 outbox 计数通过校验。参考回放使用同一 MatchingEngine 类，不能当作独立撮合算法验证，也没有证明完整复制 checkpoint 的云端重启恢复。三轮仍分别有 254、198,630、198,936 条 FIFO 满未发送；drain 为 997.834069、1,756.751506、1,752.095294 ms，均超登记界限。B1/B2 窗口内吞吐亦未达目标的 95%。有限队列填满后的平坦积压不能说明稳定，见[pilot 分析](pilot100us/analysis/summary.json)与[正式 B 分析](delay100000/analysis/summary.json)。

## 为什么值得保留 B，但还不能宣布容量成功

[正式归因报告](analysis/attribution-summary.json)在到达窗口内部完整采样，按相邻单调时钟差计算速率，并按进程、inode 与重叠 FD 验证 UDP socket 所有权。A1/B1/A2 约覆盖 13 秒，B2 约 12 秒；因此比较每秒速率：

| 采样指标 | A1 | B1 | A2 | B2 |
|---|---:|---:|---:|---:|
| node 0 NAKs sent / 秒 | 131,125.7 | 1,021.3 | 133,285.5 | 1,041.9 |
| node 0 owned UDP drop 增量 / 秒 | 17,729.7 | 561.5 | 17,808.6 | 580.1 |
| load owned UDP drop 增量 / 秒 | 41,823.1 | 0 | 39,508.9 | 0 |

对应 node 0 drop 总增量为 230,486 / 7,300 / 231,512 / 6,961，load 为 543,700 / 0 / 513,617 / 0。两次 B 都减少了反馈流量和观察到的 socket 丢包，并完成校验；这是可重复的恢复行为改善。socket drop 不是业务命令丢失计数，采样相关性也不能确定唯一瓶颈。pilot 的不同负载归因另见[pilot 报告](analysis/pilot-attribution-summary.json)，不混作同负载对照。

## 证据完整性与结论边界

五份完整 gzip——[pilot](pilot100us/runs/k-pilot-100000ns-10000-w256/arrivals.csv.gz)、[A1](delay1000/runs/k-nak1000-26000-w256-r1/arrivals.csv.gz)、[B1](delay100000/runs/k-nak100000-26000-w256-r1/arrivals.csv.gz)、[A2](delay1000/runs/k-nak1000-26000-w256-r2/arrivals.csv.gz)、[B2](delay100000/runs/k-nak100000-26000-w256-r2/arrivals.csv.gz)——均保留每轮 350,000 行、全部 33 列。归档审计逐行检查身份及结果，核对压缩、解压、本地原始 CSV、归档 manifest 和分析输入的哈希；未启动请求不填补延迟，失败轮不删除或改写成通过。

本轮支持将 B 作为后续容量实验候选配置。它尚未给出 26k/s 稳定点、稳定吞吐上限、撮合引擎极限或长期 SLA；低负载重测与更长稳定窗口仍是必要证据。负载与 member 2 共用主机，网关、PostgreSQL 投影及订阅分发不在本轮路径内。总云预算上限仍为 20 美元；预算估算不等于结算账单。累计唯一一亿命令、一亿条/秒和一亿同时连接均未实现，独立轮次复用身份，不能累加冒充唯一命令数。

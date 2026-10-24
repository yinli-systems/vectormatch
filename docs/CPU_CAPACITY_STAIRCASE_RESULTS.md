# CPU 固定配置容量阶梯：原始五点

这是原登记六点阶梯中的五个已观测点，作为证据页面的独立 CPU cohort 展示。数据逐行来自固定31e4分析器已完成的五份独立分析，没有混入10k pilot、旧 GPU、JMH 或后续节点 idle 对照。

配置：同一 CPU 主机上的三个 JVM、loopback UDP、固定 leader0、source `433f02bebe2f3109ec363291fa562d5c509c0723`、sync2、节点与负载 heap2g、W128/Q64、一个共享 client driver/一个 multiplexed session、NAK1000ns、节点 maxPark1ms、350k profile。相同配置 fingerprint：`a77866e29cef71cba0deb192e5e1ec65c1de4b71f23b65204194b1d26ebf660e`。

| 点 | 到达率/s | 到达窗口 goodput/s | accepted-only p99 ms | 全 offered accepted p99 ms | 未发送/队列拒入 | 观测结论 |
|---|---:|---:|---:|---:|---:|---|
| 13k r1 | 13,000 | 12,997.59 | 22.42 | 22.42 | 0 | 有效、有限窗稳定 |
| 18k r1 | 18,000 | 17,607.24 | 440.41 | 空 | 33 | 有效、过载或客户端不足 |
| 26k r1 | 26,000 | 17,076.95 | 534.00 | 空 | 111,798 | 有效、过载或客户端不足 |
| 13k r2 | 13,000 | 12,997.18 | 48.82 | 48.82 | 0 | 有效、有限窗稳定 |
| 18k r2 | 18,000 | 17,856.67 | 214.33（无效诊断） | 不作为有效容量指标 | 0 | 生成器时序无效 |

五点初始/最终 UNKNOWN 均为0。窗口分别约26.923s、19.444s、13.462s；这不是持续运行或跨机器容量证明。13k有两次满足原有限窗稳定准则的观测，18k/26k出现过载；目前不能从这些短窗推出精确持续吞吐上限。

18k r2 保留在图中并标为 invalid：13个 scheduler lateness 超过登记20ms阈值，最大20.66404ms。它的原始诊断数值完整保留，不能用它宣称18k容量通过。登记的26k r2在无效点后的预声明停止条件触发后**未执行**，没有补造第六个观测或重试身份。

accepted-only p99以成功确认的请求为条件，不包含未发送请求。18k r1与26k r1的全 offered accepted p99保持 JSON null；不会将它们补成稳定延迟。goodput是到达窗口内确认的accepted数量除以窗口长度，不能与含drain吞吐混用。

原登记计划 SHA：`562ca67b1402fa1cfd0ec6130c486a7f649b913db5c25a2e8eefd7bf9ddae7ab`。

可审计来源：

- [五份原始分析行的汇总](../evidence/2026-10-24/runpod-cpu/derived/capacity-five-point-ui/summary.json)：原行保持不变，包括 invalid、overload 和 null。
- [SHA 来源清单](../evidence/2026-10-24/runpod-cpu/derived/capacity-five-point-ui/provenance.json)：五份独立分析、31e4执行收据、原注册、completion、原始CSV压缩包及归档清单的路径/SHA；构建时重新校验七类分析输入的原始 SHA。
- [UI 导出结果](../evidence/2026-10-24/runpod-cpu/derived/capacity-five-point-ui/capacity.json)与[导出验证收据](../evidence/2026-10-24/runpod-cpu/derived/capacity-five-point-ui/export-validation.json)。
- [只读汇总脚本](../evidence/2026-10-24/runpod-cpu/derived/capacity-five-point-ui/build-summary.py)，随后使用仓库既有 `scripts/export-capacity-ui.py` 添加 cohort。此过程不重跑负载或分析器。

原始五点、旧 GPU 与后续 idle 对照各自保持独立证据组。

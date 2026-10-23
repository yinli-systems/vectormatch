# Runpod 私网预检方案

用户于 2026-10-23 指定优先使用其已登录的 Runpod 控制台。当前只完成浏览器中的配置选择，没有新建 Pod、购买磁盘或运行云端压测。

## 本次表单选择

| 项目 | 已选值 |
|---|---|
| Pod 名称 | `vectormatch-udp-probe-01` |
| 云类型 / 筛选 | Secure，Global Networking 已勾选；至少 4 vCPU / 16GB RAM，NVMe |
| 机房 | `EUR-IS-1` |
| GPU 数量 | **1**，RTX A4000 |
| 页面报告的 CPU / RAM | **18 vCPU / 53GB**；实际配额和亲和性待远端预检 |
| 镜像 | Runpod 官方 PyTorch 2.8.0 / Ubuntu 24.04 模板 |
| 磁盘 | 50GB 临时 container disk，未挂载其他项目的卷 |
| 报价 | GPU $0.25/h，container disk 约 $0.007/h，页面总价四舍五入 **$0.26/h** |

此配置在选定时有匹配库存，但库存与宿主机分布可能变化。此前看到的 RTX 2000 Ada $0.24/h 在检查过的具体机房中缺货，不能用它作为已经确定能开齐的三机报价。

三台若仍有同价库存，按页面上调后的 $0.26/h 估算，12 小时约 **$9.36**，只计本项目新增资源。正式三机实验还需要独立持久卷及重新核价；目前的临时盘只适合先做无状态网络预检，停止 Pod 后不能依赖它保存撮合日志。20 美元预算并非账户自动停机上限，实际使用时间、其他既有任务、税费与持久存储费用需分别核对。

## 修正网络结论

[公网端口说明](https://docs.runpod.io/pods/configuration/expose-ports) 不支持公开 UDP 映射。[Global Networking 文档](https://docs.runpod.io/pods/networking) 描述的是 NVIDIA GPU Pods 的私有网络，标称 Pod 间 100 Mbps，并未明确承诺 Aeron UDP 可用。不能把公网限制直接推断为私网绝对不支持，也不能把私网地址的存在当成 UDP 已经验证。

浏览器中的 Global Networking 筛选处于勾选状态；本次有货的 EUR-IS-1 并不在当前文档列出的支持机房清单内，因此部署后首先核对实际私网地址和可用功能。CPU Pod 没有获得相同私网能力的文档依据；它仍可用于单机 CPU、HTTP 或 loopback 实验。

## 放行三机实验前的验证

1. 先调度两个小规格 Pod，确认相同机房、Global Networking 实际生效、SSH 可达。
2. 使用提供方 `machineId` 检查实际宿主机分布；[官方定义](https://docs.runpod.io/api-reference/pods/GET/pods) 为宿主机唯一标识。GPU count 调到 3 不是三台独立机器，也没有找到普通 Pods 的 Spread 保证。
3. 双向测试真实私网 UDP、源地址、MTU、丢包和 RTT。`ping` 成功或 TCP 可用都不能替代 UDP 验证。
4. 仅当 UDP 通过且能调度到第三个不同宿主机时，才开始三副本 Aeron 实验，并单独配置持久化存储。不要用 TCP 隧道的结果冒充原生 UDP 基准。
5. 当前仓库仍使用 loopback 拓扑；实际多机端点配置和云端故障恢复证据尚未完成。100 Mbps 私网也必须写入压测边界。

如果私网功能未提供或实测不通，则保存失败证据、结束本次预检，再采用 [Hetzner 三机租用单](HETZNER_LAB.md)。这是一条有明确验收条件的 Runpod 试验路线，不是已经实现的多机部署。

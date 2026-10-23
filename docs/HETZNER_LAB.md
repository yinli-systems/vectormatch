# Hetzner 三节点 UDP 实验租用单

核价日期：2026-10-23。目标是 **20 美元总预算内的一次短期实验**，不是包月托管。尚未购买云资源，也未进行远端部署。

## 配置与预算

首选德国 NBG1，同区缺货时整体改为芬兰 HEL1。全部使用 Ubuntu 24.04 LTS、x86-64、各一个公网 IPv4，加入同一私网及同一个 Spread Placement Group。

| 名称 | 机型 | CPU / 内存 / 本地盘 | 角色 | 每台每小时，含 IPv4，未含税 |
|---|---|---|---|---:|
| vm-node-0 | CCX23 | 4 dedicated vCPU / 16GB / 160GB NVMe | 撮合副本 0 | $0.1636 |
| vm-node-1 | CCX23 | 4 dedicated vCPU / 16GB / 160GB NVMe | 撮合副本 1 | $0.1636 |
| vm-node-2 | CCX23 | 4 dedicated vCPU / 16GB / 160GB NVMe | 撮合副本 2 | $0.1636 |
| vm-loadgen | CCX13 | 2 dedicated vCPU / 8GB / 80GB NVMe | 压测与控制机 | $0.0819 |

四台合计 **$0.5727/小时**。从创建到删除计：12 小时 $6.8724，24 小时 $13.7448，均未含税。若仅租三台 CCX23，24 小时为 $11.7792 未含税，但压测进程需要与一个副本共享资源，证据必须披露。

建议第一轮安排 12 小时，包含部署、UDP/MTU 预检、正确性与故障恢复、稳定负载、证据导出。最多按 24 小时规划，余下预算留给税费和小时取整。以账户实际结算价为准；预算说明和测试脚本均不是云账单硬限制。关闭实例仍收费，证据取回后需删除本次实例及其计费 IPv4。不要选自动备份、额外磁盘、负载均衡器或其他收费附件。

价格依据：[2026-06 最新价格表](https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/)、[机型规格](https://www.hetzner.com/cloud/general-purpose/)、[IPv4 小时价](https://docs.hetzner.com/cloud/servers/primary-ips/overview/)、[计费规则](https://docs.hetzner.com/general/billing-and-account-management/billing-at-hetzner/payment-overview/)。CCX23 $0.1626/h、CCX13 $0.0809/h，IPv4 各 $0.0010/h。

**库存条件：**[官方目前有实例供应受限通知](https://status.hetzner.com/incident/0a75c7ae-3377-41dc-aabe-601063724d24)，新账户和部分既有账户可能无法创建。先在控制台确认配额和同地区机型库存；不要把其他地区或更贵机型当作不加核价的替代品。尚未核实此账户可实际创建四台机器。

## 控制台填写顺序

1. 账户币种选 USD，项目命名 `vectormatch-lab`。
2. 将本机 `runtime/ssh/vectormatch-cloud.pub` 的整行公钥导入项目 SSH Keys，名称 `vectormatch-cloud-20261023`。创建每台机器时都选中它。私钥保留在本机、权限 0600，整个 runtime 已被 Git 忽略。不要把私钥或云账号密码贴进聊天。
3. 创建 Network `vm-private`，网络区 `eu-central`，CIDR `10.77.0.0/16`，子网 `10.77.0.0/24`。
4. 创建 Placement Group `vm-spread`，类型 **Spread**。把四台机器加入同一组；[官方保证组内实例位于不同物理宿主机](https://docs.hetzner.com/cloud/placement-groups/overview/)，但这不是跨机房或跨供电域保证。
5. 按上表创建机器，四台都位于 NBG1（或四台都在 HEL1）、挂载 `vm-private`、选择指定 SSH Key 和 Spread group，启用公网 IPv4。
6. 公网入站只放行 TCP 22，来源限定这台 Mac 的当前公网 IP/32；出站先保留默认允许。Aeron 的 UDP 使用私网，不向公网开放。私网的主机过滤规则由部署阶段配置；[Hetzner Cloud Firewall 不过滤私网](https://docs.hetzner.com/cloud/firewalls/faq/)。
7. 发来四台机器的名称、公网 IPv4、实际分配的私网 IPv4，以及 SSH 用户与端口（官方 Ubuntu 镜像默认 `root`、22）。不需要发送账户密码或 API token。

```text
vm-node-0   公网=...  私网=...  用户=root  端口=22
vm-node-1   公网=...  私网=...  用户=root  端口=22
vm-node-2   公网=...  私网=...  用户=root  端口=22
vm-loadgen  公网=...  私网=...  用户=root  端口=22
```

这是标准 SSH 接入，不依赖 Runpod 连接器。公钥在创建时注入后，本机可使用项目专用私钥连接：

```sh
ssh -i runtime/ssh/vectormatch-cloud -o IdentitiesOnly=yes root@实际公网IPv4
```

参考：[官方建机步骤](https://docs.hetzner.com/cloud/servers/getting-started/creating-a-server/)、[官方 SSH 登录说明](https://docs.hetzner.com/cloud/servers/getting-started/connecting-to-the-server/)。

## 接通后的实施边界

当前仓库启动器仍是同机 loopback 拓扑。下一步先把所有 Aeron 成员、复制、Archive 响应、客户端回包端点改为实际私网地址，并验证三台机器各运行一个副本；原启动器不能原样当作多机部署证据。

Hetzner Networks 是免费私有 IPv4 三层网络，适用于这次 UDP unicast 拓扑；实际双向 UDP、丢包与 RTT 在部署后验证。[Networks FAQ](https://docs.hetzner.com/networking/networks/faq/)。其 [私网 MTU 最大 1450](https://docs.hetzner.com/networking/networks/troubleshooting/mtu/)，计划先使用 Aeron MTU 1408，并实测双向路径，避免未经验证的分片。

随后部署非 root 服务用户、Java 21、同步级别 2 的三副本、真实 PostgreSQL 投影，再执行有固定到达率的压测、leader kill、重启恢复、资金/事件/状态哈希校验。压测期间不把 Mac 到欧洲的 SSH 或公网 RTT 混入集群内延迟；所有数据注明机器、拓扑、时长、持久化和测量范围。

import pathlib,json
base=pathlib.Path('evidence/2026-10-23')
restore=base/'runpod-capacity-restoration';budget=json.loads((restore/'final-budget.json').read_text());ready=json.loads((restore/'restored-readiness.json').read_text());ledger=json.loads((restore/'postgres-ledger.json').read_text());ws=json.loads((restore/'websocket.json').read_text());repeat=json.loads((base/'runpod-capacity-long/analysis/repeats.json').read_text());summary=json.loads((base/'runpod-capacity-long/analysis/summary.json').read_text())
assert ready['passed'] and ledger['passed'] and ws['passed'] and len(ws['frames'])==3
count=sum(len(json.loads((base/folder/'analysis/summary.json').read_text())['trials']) for folder in ['runpod-capacity','runpod-capacity-extended','runpod-capacity-128','runpod-capacity-long'])
stable=repeat['highestRepeatedlyStableRate'];upper=repeat['lowestRepeatedlyNonstableRate'];assert stable and upper
cost=budget['estimatedAccruedUsd'];utc=budget['asOfUtc'];cursor=ledger['cursor']['event_seq'];trades=ledger['cursor']['trades_stored']
link='../evidence/2026-10-23/runpod-capacity-restoration/'
blocks={
'docs/CLOUD_TESTING.md':f'''## Latest capacity and restoration evidence

The completed open-loop campaign retains **{count} trials in four separate configuration cohorts**, including {len(summary['trials'])} fixed 2 GiB/128-client long-window trials. The highest repeatedly stable tested arrival rate in that cohort is **{stable:,.0f}/s**; **14,000/s is mixed**, and **{upper:,.0f}/s is repeatedly nonstable**. These are finite client-plus-replicated-path observations, with the load generator sharing member 2; they do not establish an unconstrained matching-core ceiling or indefinite production capacity. See the [capacity report](CAPACITY_RESULTS.md), [raw long-window evidence](../evidence/2026-10-23/runpod-capacity-long/) and [cross-phase repeat summary](../evidence/2026-10-23/runpod-capacity-long/analysis/repeats.json). Every completed outcome is retained.

After testing, fresh [offline backup digests]({link}backup-manifest.json) were verified on their source Pods, the original Java release and original state resumed, and [HTTP readiness]({link}restored-readiness.json), [SQL ledger continuity]({link}postgres-ledger.json) and [WebSocket state delivery]({link}websocket.json) passed. The observed SQL cursor is **{cursor:,}**, trades **{trades:,}**, lag **0**, with synthetic flow paused. Service resumption used the same Pod filesystems; it was not a backup restore rehearsal. Fresh native backup archives remain on the source Pods; no new native archive contents were exported. Automatic approval rejected the proposed additional native-state export because it might exceed the explicit synthetic-evidence authorization. Earlier local backups remain unchanged; synthetic evidence and manifests are in this private repository.

At **{utc}**, estimated cumulative project cost is **${cost:.3f} of $20**, based on launch-time/rate estimates rather than a reconciled provider bill. No additional Pods were created. The existing three remain running at the user's retained-service request, approximately $1.56/hour; the existing 04:24 Dubai reminder remains a notification, not an automatic stop. The earlier low-rate observations and earlier cost estimates below retain their historical scope.

''',
'docs/RUNPOD_LAB.md':f'''## 最新容量曲线与恢复验收

本次 open-loop 容量压测已保留 **{count} 轮、4 个独立配置组**，其中新的 2 GiB / 128 客户端长窗组完成 {len(summary['trials'])} 轮：**{stable:,.0f}/s 两轮稳定，14,000/s 结果混合，{upper:,.0f}/s 两轮非稳定**。结论覆盖有限队列、同步客户端和三节点复制撮合路径；负载与 member 2 共址。完整 p99、积压、准入损失、拒绝和 unknown 见[容量报告](CAPACITY_RESULTS.md)、[长窗原始记录](../evidence/2026-10-23/runpod-capacity-long/)及[跨阶段复测汇总](../evidence/2026-10-23/runpod-capacity-long/analysis/repeats.json)，不将它包装成撮合核心或无限持续写入上限。

测试后已在原 Pod 重新制作并校验[原应用离线备份清单]({link}backup-manifest.json)，恢复原 Java release 和原始业务状态。[HTTP]({link}restored-readiness.json)、[SQL 账本]({link}postgres-ledger.json)、[WebSocket]({link}websocket.json)验收均通过；SQL cursor **{cursor:,}**、trades **{trades:,}**、观察 lag **0**，合成流保持暂停。这是在相同 Pod 原文件系统上恢复服务，并非从备份副本恢复演练；新增原生归档保留在原 Pod，没有外传原生内容；自动审批因授权边界拒绝了新增原生状态导出。此前本地备份保持，仓库保存合成证据与校验元数据。

截至 **{utc}**，本项目累计费用估算 **${cost:.3f} / $20**，按启动时间和报价估算，尚未与供应商账单结算。没有新增 Pod；现有三台按用户要求保留，约 $1.56/小时继续计费，原定 04:24 Dubai 提醒保持。下文较早的单在途结果、SQL 观察和费用估算均保留其历史时点。

'''}
for name,block in blocks.items():
 p=pathlib.Path(name);text=p.read_text();first,rest=text.split('\n\n',1)
 assert '## Latest capacity and restoration evidence' not in rest and '## 最新容量曲线与恢复验收' not in rest,'Overview already updated; review instead of duplicating'
 p.write_text(first+'\n\n'+block+rest)
print('OVERVIEW_UPDATED',count,cost,cursor,trades)

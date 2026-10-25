# V4 capacity source: exact-cut and admission-audit correction

The first1,000/s CONTINUE run at source6716f74a/artifact2ea38974 confirms all20,000 synthetic one-unit trades,zero notSent/unknown,and matching physical-order replay,snapshots and cold restore. It is excluded from capacity conclusions:its first cut contains1,535 commands instead of the preregistered1,536. The second pair and upward rate progression were stopped. The original217-file scope is preserved as a fully downloaded/member-verified private attachment.

## Two separate findings

The previous independent checker rejected a physical publication during ACK_DRAIN. The original command was logically admitted in FILE_WAIT0.495ms before that transition,published0.044ms afterward,and completed before the destructive-intent phase. The coordinator correctly prevents new logical submissions during drain while allowing already-admitted originals to finish. A stronger checker now verifies logical admission timestamps and binds any drain publication to its prior original admission. It still rejects new submissions during read/drain and every publication during genuinely exclusive read/control phases.

After that false positive was removed,the exact-cut check exposed a real source race. A global completed frontier can already include an original whose local pending slot has not been observed. Adding those values is a conservative admission heuristic and can double-count completion. The sticky cut request was then allowed to close a1,535-command nonfinal prefix after the local slot drained.

The new allocation-free cut gate recomputes admission on each observation. Only a drained known prefix of at least1,536 commands can start a normal cut. A shorter final prefix requires independently exhausted arrivals and queues. If the admission heuristic resolves to an incomplete prefix,the source admits the missing work. This restores the ceiling on cycle/file/journal counts derived by the finite plan.

## Validation and next experiment

Seventy-four forced local tests pass,including the observed1,535+1 boundary,all127 possible overlapping worker observations,final partial cuts,file-count bounds and invalid observations. The existing two-policy open-loop test still executes10,000 arrivals per policy and checks exact cuts and original outcomes. The corrected Python checker passes14 actual system-Python3.8 checks over11 fixtures. It separately proves legitimate original draining,new-submission refusal,the previous strict false positive,and continued rejection of the actual1,535-command cut. All original native inputs remain unchanged.

The matching engine and coordinator business rules are unchanged. The source change and new checker require a new qualified artifact and fresh common-artifact comparisons. Earlier500/s pairs remain separate historical observations;their latency values cannot qualify the new artifact. The original failed checker output and the workload-contract failure are retained rather than repaired in place. Full Linux regression and new native qualification remain pending at this checkpoint. No additional business command was issued to reinterpret the old run.

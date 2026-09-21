| Agent | Model | LLM calls | LLM input tok | LLM output tok | Jev calls | Jev input tok | Jev output tok | LLM cost | Jev cost | Total cost | LLM latency p50 | LLM latency p90 | Jev latency p50 | Jev latency p90 | Max tool calls/turn | Turn latency p50 | Turn latency p90 | Passed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| jev | deepseek/deepseek-v4-flash-20260731 | 137 | 184,990 | 58,156 | 137 | 361,821 | 137,777 | $0.0719 | $0.0152 | $0.0871 | 1,855ms | 6,435ms | 343ms | 809ms | 0 | 2,317ms | 6,986ms | 11/11 |
| simple_workflow_api | deepseek/deepseek-v4-flash-20260731 | 261 | 1,295,606 | 36,176 | — | 0 | 0 | $0.2808 | — | $0.2808 | 915ms | 2,616ms | — | — | 3 | 1,889ms | 5,436ms | 11/11 |

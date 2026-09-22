| Agent | Model | LLM calls | LLM input tok | LLM output tok | Jev calls | Jev input tok | Jev output tok | LLM cost | Jev cost | Total cost | LLM latency p50 | LLM latency p90 | Jev latency p50 | Jev latency p90 | Max tool calls/turn | Turn latency p50 | Turn latency p90 | Passed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| jev | deepseek/deepseek-v4-flash-20260731 | 137 | 161,981 | 38,215 | 137 | 378,059 | 145,345 | $0.0553 | $0.0159 | $0.0712 | 3,266ms | 9,555ms | 322ms | 800ms | 0 | 3,765ms | 9,889ms | 11/11 |
| simple_workflow_api | deepseek/deepseek-v4-flash-20260731 | 257 | 1,265,358 | 41,849 | — | 0 | 0 | $0.2782 | — | $0.2782 | 1,017ms | 3,395ms | — | — | 1 | 2,130ms | 5,957ms | 11/11 |

| Agent | Model | LLM calls | LLM input tok | LLM output tok | Jev calls | Jev input tok | Jev output tok | LLM cost | Jev cost | Total cost | LLM latency p50 | LLM latency p90 | Jev latency p50 | Jev latency p90 | Max tool calls/turn | Turn latency p50 | Turn latency p90 | Passed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| jev | deepseek/deepseek-v4-flash-20260731 | 137 | 189,720 | 61,415 | 137 | 361,367 | 137,786 | $0.0748 | $0.0152 | $0.0900 | 1,874ms | 8,928ms | 285ms | 645ms | 0 | 2,271ms | 9,247ms | 11/11 |
| simple_workflow_api | deepseek/deepseek-v4-flash-20260731 | 260 | 1,341,921 | 41,122 | — | 0 | 0 | $0.2931 | — | $0.2931 | 1,116ms | 4,069ms | — | — | 2 | 2,270ms | 7,467ms | 11/11 |

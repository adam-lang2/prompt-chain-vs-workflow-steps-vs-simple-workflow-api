| Agent | Model | LLM calls | LLM input tok | LLM output tok | Jev calls | Jev input tok | Jev output tok | LLM cost | Jev cost | Total cost | LLM latency p50 | LLM latency p90 | Jev latency p50 | Jev latency p90 | Max tool calls/turn | Turn latency p50 | Turn latency p90 | Passed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| jev | deepseek/deepseek-v4-flash-20260731:none | 137 | 180,562 | 11,168 | 137 | 361,536 | 137,774 | $0.0428 | $0.0152 | $0.0580 | 1,011ms | 1,984ms | 319ms | 412ms | 0 | 1,382ms | 2,492ms | 10/11 |
| simple_workflow_api | deepseek/deepseek-v4-flash-20260731:none | 235 | 1,118,764 | 18,872 | — | 0 | 0 | $0.2351 | — | $0.2351 | 1,166ms | 2,553ms | — | — | 2 | 2,195ms | 4,355ms | 10/11 |

Failures:
- **jev** [deepseek/deepseek-v4-flash-20260731:none] / `messy_malformed_email_retry`: book_court.contact_name = 'morgan.diaz@example.com', expected 'Morgan Diaz'
- **simple_workflow_api** [deepseek/deepseek-v4-flash-20260731:none] / `zero_result_relax`: book_court was never called (expected date='2026-09-20'); book_court was never called (expected time='17:30'); book_court was never called (expected duration_minutes=90); book_court was never called (expected num_players=2); book_court was never called (expected skill_level='intermediate'); book_court was never called (expected equipment_rental=False); book_court was never called (expected contact_name='Alex Rivera'); book_court was never called (expected contact_email='alex.rivera@example.com')

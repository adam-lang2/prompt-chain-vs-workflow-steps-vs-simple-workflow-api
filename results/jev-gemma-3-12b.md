| Agent | Model | LLM calls | LLM input tok | LLM output tok | Jev calls | Jev input tok | Jev output tok | LLM cost | Jev cost | Total cost | LLM latency p50 | LLM latency p90 | Jev latency p50 | Jev latency p90 | Max tool calls/turn | Turn latency p50 | Turn latency p90 | Passed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| jev | google/gemma-3-12b-it | 137 | 179,946 | 11,249 | 137 | 375,219 | 145,345 | — | $0.0158 | $0.0158 | 1,434ms | 2,867ms | 344ms | 791ms | 0 | 1,965ms | 3,239ms | 11/11 |

## Per-scenario timing and reasoning text

### jev / in_order_golden_gate_hard — 37.7s, 13 turns

- turn 1: 2,598ms
- turn 2: 2,543ms
- turn 3: 1,965ms
- turn 4: 2,641ms
- turn 5: 2,355ms
- turn 6: 11,652ms
- turn 7: 2,975ms
- turn 8: 1,278ms
- turn 9: 1,057ms
- turn 10: 1,309ms
- turn 11: 2,779ms
- turn 12: 2,241ms
- turn 13: 2,290ms

**call 1** turn 1 `jev` — 850ms, in=2,722 (cached 0), out=1,154 (reasoning 0)

**call 2** turn 1 `llm` — 1,745ms, in=562 (cached 0), out=27 (reasoning 0)

**call 3** turn 2 `jev` — 302ms, in=2,418 (cached 0), out=953 (reasoning 0)

**call 4** turn 2 `llm` — 2,237ms, in=579 (cached 0), out=28 (reasoning 0)

**call 5** turn 3 `jev` — 334ms, in=2,291 (cached 0), out=888 (reasoning 0)

**call 6** turn 3 `llm` — 1,628ms, in=635 (cached 0), out=46 (reasoning 0)

**call 7** turn 4 `jev` — 378ms, in=2,317 (cached 0), out=886 (reasoning 0)

**call 8** turn 4 `llm` — 2,259ms, in=705 (cached 0), out=41 (reasoning 0)

**call 9** turn 5 `jev` — 755ms, in=2,417 (cached 0), out=939 (reasoning 0)

**call 10** turn 5 `llm` — 1,593ms, in=761 (cached 0), out=45 (reasoning 0)

**call 11** turn 6 `jev` — 486ms, in=2,210 (cached 0), out=826 (reasoning 0)

**call 12** turn 6 `llm` — 11,147ms, in=2,150 (cached 0), out=514 (reasoning 0)

**call 13** turn 7 `jev` — 845ms, in=3,817 (cached 0), out=1,380 (reasoning 0)

**call 14** turn 7 `llm` — 2,120ms, in=1,434 (cached 0), out=87 (reasoning 0)

**call 15** turn 8 `jev` — 338ms, in=2,971 (cached 0), out=1,147 (reasoning 0)

**call 16** turn 8 `llm` — 932ms, in=1,534 (cached 0), out=12 (reasoning 0)

**call 17** turn 9 `jev` — 324ms, in=3,044 (cached 0), out=1,229 (reasoning 0)

**call 18** turn 9 `llm` — 726ms, in=1,537 (cached 0), out=17 (reasoning 0)

**call 19** turn 10 `jev` — 299ms, in=2,942 (cached 0), out=1,167 (reasoning 0)

**call 20** turn 10 `llm` — 1,001ms, in=1,644 (cached 0), out=24 (reasoning 0)

**call 21** turn 11 `jev` — 307ms, in=2,781 (cached 0), out=1,057 (reasoning 0)

**call 22** turn 11 `llm` — 2,458ms, in=1,820 (cached 0), out=101 (reasoning 0)

**call 23** turn 12 `jev` — 367ms, in=3,085 (cached 0), out=1,202 (reasoning 0)

**call 24** turn 12 `llm` — 1,855ms, in=1,875 (cached 0), out=74 (reasoning 0)

**call 25** turn 13 `jev` — 385ms, in=2,976 (cached 0), out=1,145 (reasoning 0)

**call 26** turn 13 `llm` — 1,902ms, in=1,993 (cached 0), out=75 (reasoning 0)

### jev / messy_prospect_park_clay_correction — 24.4s, 10 turns

- turn 1: 2,475ms
- turn 2: 1,315ms
- turn 3: 2,291ms
- turn 4: 1,227ms
- turn 5: 6,734ms
- turn 6: 1,407ms
- turn 7: 2,498ms
- turn 8: 2,501ms
- turn 9: 2,202ms
- turn 10: 1,780ms

**call 1** turn 1 `jev` — 833ms, in=2,550 (cached 0), out=1,059 (reasoning 0)

**call 2** turn 1 `llm` — 1,639ms, in=532 (cached 0), out=25 (reasoning 0)

**call 3** turn 2 `jev` — 325ms, in=3,008 (cached 0), out=1,306 (reasoning 0)

**call 4** turn 2 `llm` — 983ms, in=625 (cached 0), out=22 (reasoning 0)

**call 5** turn 3 `jev` — 350ms, in=2,585 (cached 0), out=1,031 (reasoning 0)

**call 6** turn 3 `llm` — 1,935ms, in=683 (cached 0), out=57 (reasoning 0)

**call 7** turn 4 `jev` — 290ms, in=2,633 (cached 0), out=1,029 (reasoning 0)

**call 8** turn 4 `llm` — 930ms, in=775 (cached 0), out=35 (reasoning 0)

**call 9** turn 5 `jev` — 352ms, in=2,256 (cached 0), out=855 (reasoning 0)

**call 10** turn 5 `llm` — 6,370ms, in=1,549 (cached 0), out=281 (reasoning 0)

**call 11** turn 6 `jev` — 767ms, in=3,534 (cached 0), out=1,348 (reasoning 0)

**call 12** turn 6 `llm` — 633ms, in=1,144 (cached 0), out=15 (reasoning 0)

**call 13** turn 7 `jev` — 358ms, in=2,872 (cached 0), out=1,107 (reasoning 0)

**call 14** turn 7 `llm` — 2,127ms, in=1,403 (cached 0), out=104 (reasoning 0)

**call 15** turn 8 `jev` — 365ms, in=2,970 (cached 0), out=1,143 (reasoning 0)

**call 16** turn 8 `llm` — 2,124ms, in=1,405 (cached 0), out=76 (reasoning 0)

**call 17** turn 9 `jev` — 592ms, in=3,006 (cached 0), out=1,172 (reasoning 0)

**call 18** turn 9 `llm` — 1,606ms, in=1,538 (cached 0), out=62 (reasoning 0)

**call 19** turn 10 `jev` — 297ms, in=3,002 (cached 0), out=1,169 (reasoning 0)

**call 20** turn 10 `llm` — 1,474ms, in=1,636 (cached 0), out=57 (reasoning 0)

### jev / messy_prospect_park_bulk_dump — 28.6s, 8 turns

- turn 1: 2,013ms
- turn 2: 1,351ms
- turn 3: 14,324ms
- turn 4: 1,407ms
- turn 5: 2,767ms
- turn 6: 2,516ms
- turn 7: 2,163ms
- turn 8: 2,038ms

**call 1** turn 1 `jev` — 853ms, in=2,501 (cached 0), out=1,031 (reasoning 0)

**call 2** turn 1 `llm` — 1,159ms, in=531 (cached 0), out=10 (reasoning 0)

**call 3** turn 2 `jev` — 339ms, in=2,999 (cached 0), out=1,309 (reasoning 0)

**call 4** turn 2 `llm` — 1,005ms, in=593 (cached 0), out=16 (reasoning 0)

**call 5** turn 3 `jev` — 316ms, in=3,468 (cached 0), out=1,537 (reasoning 0)

**call 6** turn 3 `llm` — 13,987ms, in=2,132 (cached 0), out=544 (reasoning 0)

**call 7** turn 4 `jev` — 803ms, in=4,241 (cached 0), out=1,604 (reasoning 0)

**call 8** turn 4 `llm` — 591ms, in=1,270 (cached 0), out=14 (reasoning 0)

**call 9** turn 5 `jev` — 384ms, in=2,936 (cached 0), out=1,137 (reasoning 0)

**call 10** turn 5 `llm` — 2,372ms, in=1,526 (cached 0), out=100 (reasoning 0)

**call 11** turn 6 `jev` — 352ms, in=3,034 (cached 0), out=1,172 (reasoning 0)

**call 12** turn 6 `llm` — 2,150ms, in=1,577 (cached 0), out=75 (reasoning 0)

**call 13** turn 7 `jev` — 334ms, in=3,342 (cached 0), out=1,343 (reasoning 0)

**call 14** turn 7 `llm` — 1,823ms, in=1,734 (cached 0), out=74 (reasoning 0)

**call 15** turn 8 `jev` — 309ms, in=3,030 (cached 0), out=1,171 (reasoning 0)

**call 16** turn 8 `llm` — 1,722ms, in=1,782 (cached 0), out=69 (reasoning 0)

### jev / zero_result_relax — 38.6s, 14 turns

- turn 1: 2,109ms
- turn 2: 1,619ms
- turn 3: 1,799ms
- turn 4: 1,274ms
- turn 5: 2,041ms
- turn 6: 1,899ms
- turn 7: 15,402ms
- turn 8: 1,919ms
- turn 9: 927ms
- turn 10: 1,195ms
- turn 11: 1,116ms
- turn 12: 2,818ms
- turn 13: 2,235ms
- turn 14: 2,267ms

**call 1** turn 1 `jev` — 865ms, in=2,506 (cached 0), out=1,028 (reasoning 0)

**call 2** turn 1 `llm` — 1,242ms, in=556 (cached 0), out=13 (reasoning 0)

**call 3** turn 2 `jev` — 406ms, in=2,155 (cached 0), out=813 (reasoning 0)

**call 4** turn 2 `llm` — 1,209ms, in=553 (cached 0), out=32 (reasoning 0)

**call 5** turn 3 `jev` — 291ms, in=2,193 (cached 0), out=831 (reasoning 0)

**call 6** turn 3 `llm` — 1,506ms, in=652 (cached 0), out=41 (reasoning 0)

**call 7** turn 4 `jev` — 365ms, in=2,202 (cached 0), out=829 (reasoning 0)

**call 8** turn 4 `llm` — 906ms, in=683 (cached 0), out=24 (reasoning 0)

**call 9** turn 5 `jev` — 311ms, in=2,293 (cached 0), out=882 (reasoning 0)

**call 10** turn 5 `llm` — 1,721ms, in=773 (cached 0), out=53 (reasoning 0)

**call 11** turn 6 `jev` — 314ms, in=2,232 (cached 0), out=801 (reasoning 0)

**call 12** turn 6 `llm` — 1,583ms, in=826 (cached 0), out=48 (reasoning 0)

**call 13** turn 7 `jev` — 326ms, in=2,583 (cached 0), out=995 (reasoning 0)

**call 14** turn 7 `llm` — 15,065ms, in=2,210 (cached 0), out=696 (reasoning 0)

**call 15** turn 8 `jev` — 752ms, in=3,691 (cached 0), out=1,204 (reasoning 0)

**call 16** turn 8 `llm` — 1,159ms, in=1,624 (cached 0), out=44 (reasoning 0)

**call 17** turn 9 `jev` — 344ms, in=2,775 (cached 0), out=1,063 (reasoning 0)

**call 18** turn 9 `llm` — 569ms, in=1,675 (cached 0), out=9 (reasoning 0)

**call 19** turn 10 `jev` — 278ms, in=3,038 (cached 0), out=1,229 (reasoning 0)

**call 20** turn 10 `llm` — 905ms, in=1,668 (cached 0), out=17 (reasoning 0)

**call 21** turn 11 `jev` — 378ms, in=2,947 (cached 0), out=1,167 (reasoning 0)

**call 22** turn 11 `llm` — 732ms, in=1,780 (cached 0), out=19 (reasoning 0)

**call 23** turn 12 `jev` — 367ms, in=2,772 (cached 0), out=1,061 (reasoning 0)

**call 24** turn 12 `llm` — 2,443ms, in=1,950 (cached 0), out=98 (reasoning 0)

**call 25** turn 13 `jev` — 309ms, in=3,027 (cached 0), out=1,172 (reasoning 0)

**call 26** turn 13 `llm` — 1,910ms, in=1,955 (cached 0), out=72 (reasoning 0)

**call 27** turn 14 `jev` — 312ms, in=2,975 (cached 0), out=1,144 (reasoning 0)

**call 28** turn 14 `llm` — 1,949ms, in=2,119 (cached 0), out=65 (reasoning 0)

### jev / messy_duration_change_after_selection — 40.5s, 15 turns

- turn 1: 2,172ms
- turn 2: 1,505ms
- turn 3: 1,256ms
- turn 4: 3,035ms
- turn 5: 1,266ms
- turn 6: 12,907ms
- turn 7: 2,401ms
- turn 8: 2,257ms
- turn 9: 1,772ms
- turn 10: 900ms
- turn 11: 1,572ms
- turn 12: 1,402ms
- turn 13: 3,109ms
- turn 14: 2,354ms
- turn 15: 2,634ms

**call 1** turn 1 `jev` — 862ms, in=2,403 (cached 0), out=972 (reasoning 0)

**call 2** turn 1 `llm` — 1,307ms, in=553 (cached 0), out=16 (reasoning 0)

**call 3** turn 2 `jev` — 406ms, in=2,159 (cached 0), out=813 (reasoning 0)

**call 4** turn 2 `llm` — 1,091ms, in=553 (cached 0), out=43 (reasoning 0)

**call 5** turn 3 `jev` — 300ms, in=2,200 (cached 0), out=832 (reasoning 0)

**call 6** turn 3 `llm` — 953ms, in=621 (cached 0), out=35 (reasoning 0)

**call 7** turn 4 `jev` — 296ms, in=2,198 (cached 0), out=830 (reasoning 0)

**call 8** turn 4 `llm` — 2,736ms, in=674 (cached 0), out=17 (reasoning 0)

**call 9** turn 5 `jev` — 330ms, in=2,236 (cached 0), out=855 (reasoning 0)

**call 10** turn 5 `llm` — 931ms, in=699 (cached 0), out=21 (reasoning 0)

**call 11** turn 6 `jev` — 329ms, in=2,143 (cached 0), out=798 (reasoning 0)

**call 12** turn 6 `llm` — 12,564ms, in=2,286 (cached 0), out=520 (reasoning 0)

**call 13** turn 7 `jev` — 822ms, in=3,617 (cached 0), out=1,260 (reasoning 0)

**call 14** turn 7 `llm` — 1,574ms, in=1,340 (cached 0), out=47 (reasoning 0)

**call 15** turn 8 `jev` — 302ms, in=3,236 (cached 0), out=1,320 (reasoning 0)

**call 16** turn 8 `llm` — 1,933ms, in=1,473 (cached 0), out=59 (reasoning 0)

**call 17** turn 9 `jev` — 377ms, in=3,154 (cached 0), out=1,265 (reasoning 0)

**call 18** turn 9 `llm` — 1,389ms, in=1,588 (cached 0), out=51 (reasoning 0)

**call 19** turn 10 `jev` — 366ms, in=2,821 (cached 0), out=1,089 (reasoning 0)

**call 20** turn 10 `llm` — 521ms, in=1,561 (cached 0), out=11 (reasoning 0)

**call 21** turn 11 `jev` — 375ms, in=3,040 (cached 0), out=1,229 (reasoning 0)

**call 22** turn 11 `llm` — 1,183ms, in=1,563 (cached 0), out=19 (reasoning 0)

**call 23** turn 12 `jev` — 317ms, in=2,852 (cached 0), out=1,111 (reasoning 0)

**call 24** turn 12 `llm` — 1,076ms, in=1,671 (cached 0), out=19 (reasoning 0)

**call 25** turn 13 `jev` — 300ms, in=2,777 (cached 0), out=1,058 (reasoning 0)

**call 26** turn 13 `llm` — 2,796ms, in=1,845 (cached 0), out=100 (reasoning 0)

**call 27** turn 14 `jev` — 339ms, in=2,981 (cached 0), out=1,144 (reasoning 0)

**call 28** turn 14 `llm` — 2,001ms, in=1,894 (cached 0), out=68 (reasoning 0)

**call 29** turn 15 `jev` — 345ms, in=2,866 (cached 0), out=1,089 (reasoning 0)

**call 30** turn 15 `llm` — 2,283ms, in=1,984 (cached 0), out=69 (reasoning 0)

### jev / messy_malformed_email_retry — 40.8s, 14 turns

- turn 1: 2,050ms
- turn 2: 1,627ms
- turn 3: 1,221ms
- turn 4: 1,366ms
- turn 5: 1,229ms
- turn 6: 16,734ms
- turn 7: 3,057ms
- turn 8: 843ms
- turn 9: 985ms
- turn 10: 1,096ms
- turn 11: 2,279ms
- turn 12: 2,895ms
- turn 13: 3,132ms
- turn 14: 2,272ms

**call 1** turn 1 `jev` — 915ms, in=2,603 (cached 0), out=1,089 (reasoning 0)

**call 2** turn 1 `llm` — 1,133ms, in=558 (cached 0), out=22 (reasoning 0)

**call 3** turn 2 `jev` — 437ms, in=2,164 (cached 0), out=813 (reasoning 0)

**call 4** turn 2 `llm` — 1,187ms, in=563 (cached 0), out=24 (reasoning 0)

**call 5** turn 3 `jev` — 356ms, in=2,289 (cached 0), out=894 (reasoning 0)

**call 6** turn 3 `llm` — 862ms, in=630 (cached 0), out=29 (reasoning 0)

**call 7** turn 4 `jev` — 314ms, in=2,192 (cached 0), out=836 (reasoning 0)

**call 8** turn 4 `llm` — 1,049ms, in=673 (cached 0), out=22 (reasoning 0)

**call 9** turn 5 `jev` — 365ms, in=2,387 (cached 0), out=948 (reasoning 0)

**call 10** turn 5 `llm` — 860ms, in=706 (cached 0), out=14 (reasoning 0)

**call 11** turn 6 `jev` — 285ms, in=2,348 (cached 0), out=914 (reasoning 0)

**call 12** turn 6 `llm` — 16,428ms, in=2,276 (cached 0), out=820 (reasoning 0)

**call 13** turn 7 `jev` — 781ms, in=3,866 (cached 0), out=1,242 (reasoning 0)

**call 14** turn 7 `llm` — 2,269ms, in=1,654 (cached 0), out=38 (reasoning 0)

**call 15** turn 8 `jev` — 310ms, in=2,767 (cached 0), out=1,067 (reasoning 0)

**call 16** turn 8 `llm` — 521ms, in=1,697 (cached 0), out=9 (reasoning 0)

**call 17** turn 9 `jev` — 336ms, in=2,987 (cached 0), out=1,205 (reasoning 0)

**call 18** turn 9 `llm` — 645ms, in=1,695 (cached 0), out=16 (reasoning 0)

**call 19** turn 10 `jev` — 322ms, in=2,802 (cached 0), out=1,087 (reasoning 0)

**call 20** turn 10 `llm` — 765ms, in=1,797 (cached 0), out=14 (reasoning 0)

**call 21** turn 11 `jev` — 346ms, in=2,948 (cached 0), out=1,177 (reasoning 0)

**call 22** turn 11 `llm` — 1,926ms, in=1,817 (cached 0), out=77 (reasoning 0)

**call 23** turn 12 `jev` — 378ms, in=2,941 (cached 0), out=1,118 (reasoning 0)

**call 24** turn 12 `llm` — 2,504ms, in=2,055 (cached 0), out=96 (reasoning 0)

**call 25** turn 13 `jev` — 328ms, in=3,077 (cached 0), out=1,206 (reasoning 0)

**call 26** turn 13 `llm` — 2,789ms, in=2,113 (cached 0), out=62 (reasoning 0)

**call 27** turn 14 `jev` — 330ms, in=2,912 (cached 0), out=1,121 (reasoning 0)

**call 28** turn 14 `llm` — 1,936ms, in=2,201 (cached 0), out=69 (reasoning 0)

### jev / messy_all_at_once_opener — 26.3s, 6 turns

- turn 1: 13,687ms
- turn 2: 3,172ms
- turn 3: 1,019ms
- turn 4: 2,677ms
- turn 5: 2,519ms
- turn 6: 3,195ms

**call 1** turn 1 `jev` — 772ms, in=4,001 (cached 0), out=1,849 (reasoning 0)

**call 2** turn 1 `llm` — 12,901ms, in=2,074 (cached 0), out=526 (reasoning 0)

**call 3** turn 2 `jev` — 744ms, in=3,512 (cached 0), out=1,213 (reasoning 0)

**call 4** turn 2 `llm` — 2,423ms, in=1,230 (cached 0), out=66 (reasoning 0)

**call 5** turn 3 `jev` — 324ms, in=2,796 (cached 0), out=1,066 (reasoning 0)

**call 6** turn 3 `llm` — 681ms, in=1,315 (cached 0), out=9 (reasoning 0)

**call 7** turn 4 `jev` — 325ms, in=2,986 (cached 0), out=1,204 (reasoning 0)

**call 8** turn 4 `llm` — 2,339ms, in=1,488 (cached 0), out=97 (reasoning 0)

**call 9** turn 5 `jev` — 415ms, in=3,069 (cached 0), out=1,205 (reasoning 0)

**call 10** turn 5 `llm` — 2,096ms, in=1,554 (cached 0), out=80 (reasoning 0)

**call 11** turn 6 `jev` — 354ms, in=2,922 (cached 0), out=1,119 (reasoning 0)

**call 12** turn 6 `llm` — 2,838ms, in=1,661 (cached 0), out=72 (reasoning 0)

### jev / messy_multi_field_redo — 34.9s, 14 turns

- turn 1: 1,530ms
- turn 2: 1,643ms
- turn 3: 1,567ms
- turn 4: 1,506ms
- turn 5: 1,311ms
- turn 6: 1,326ms
- turn 7: 11,680ms
- turn 8: 3,152ms
- turn 9: 869ms
- turn 10: 1,028ms
- turn 11: 1,240ms
- turn 12: 2,537ms
- turn 13: 3,102ms
- turn 14: 2,427ms

**call 1** turn 1 `jev` — 765ms, in=2,496 (cached 0), out=1,028 (reasoning 0)

**call 2** turn 1 `llm` — 760ms, in=553 (cached 0), out=19 (reasoning 0)

**call 3** turn 2 `jev` — 327ms, in=2,161 (cached 0), out=813 (reasoning 0)

**call 4** turn 2 `llm` — 1,309ms, in=556 (cached 0), out=49 (reasoning 0)

**call 5** turn 3 `jev` — 308ms, in=2,211 (cached 0), out=839 (reasoning 0)

**call 6** turn 3 `llm` — 1,255ms, in=643 (cached 0), out=44 (reasoning 0)

**call 7** turn 4 `jev` — 295ms, in=3,156 (cached 0), out=1,349 (reasoning 0)

**call 8** turn 4 `llm` — 1,201ms, in=742 (cached 0), out=46 (reasoning 0)

**call 9** turn 5 `jev` — 281ms, in=2,209 (cached 0), out=836 (reasoning 0)

**call 10** turn 5 `llm` — 1,022ms, in=800 (cached 0), out=31 (reasoning 0)

**call 11** turn 6 `jev` — 326ms, in=2,249 (cached 0), out=861 (reasoning 0)

**call 12** turn 6 `llm` — 995ms, in=839 (cached 0), out=29 (reasoning 0)

**call 13** turn 7 `jev` — 301ms, in=2,151 (cached 0), out=804 (reasoning 0)

**call 14** turn 7 `llm` — 11,352ms, in=2,159 (cached 0), out=459 (reasoning 0)

**call 15** turn 8 `jev` — 789ms, in=3,507 (cached 0), out=1,238 (reasoning 0)

**call 16** turn 8 `llm` — 2,349ms, in=1,427 (cached 0), out=91 (reasoning 0)

**call 17** turn 9 `jev` — 341ms, in=2,813 (cached 0), out=1,067 (reasoning 0)

**call 18** turn 9 `llm` — 515ms, in=1,529 (cached 0), out=9 (reasoning 0)

**call 19** turn 10 `jev` — 352ms, in=2,935 (cached 0), out=1,179 (reasoning 0)

**call 20** turn 10 `llm` — 669ms, in=1,526 (cached 0), out=18 (reasoning 0)

**call 21** turn 11 `jev` — 364ms, in=2,894 (cached 0), out=1,145 (reasoning 0)

**call 22** turn 11 `llm` — 864ms, in=1,632 (cached 0), out=28 (reasoning 0)

**call 23** turn 12 `jev` — 313ms, in=2,779 (cached 0), out=1,064 (reasoning 0)

**call 24** turn 12 `llm` — 2,208ms, in=1,812 (cached 0), out=102 (reasoning 0)

**call 25** turn 13 `jev` — 389ms, in=2,983 (cached 0), out=1,148 (reasoning 0)

**call 26** turn 13 `llm` — 2,697ms, in=1,819 (cached 0), out=74 (reasoning 0)

**call 27** turn 14 `jev` — 393ms, in=2,925 (cached 0), out=1,120 (reasoning 0)

**call 28** turn 14 `llm` — 2,028ms, in=1,989 (cached 0), out=74 (reasoning 0)

### jev / messy_double_date_correction — 36.3s, 15 turns

- turn 1: 1,751ms
- turn 2: 1,185ms
- turn 3: 1,632ms
- turn 4: 1,446ms
- turn 5: 1,686ms
- turn 6: 1,287ms
- turn 7: 1,931ms
- turn 8: 10,384ms
- turn 9: 2,900ms
- turn 10: 1,151ms
- turn 11: 1,783ms
- turn 12: 1,264ms
- turn 13: 3,304ms
- turn 14: 2,480ms
- turn 15: 2,164ms

**call 1** turn 1 `jev` — 786ms, in=2,447 (cached 0), out=1,000 (reasoning 0)

**call 2** turn 1 `llm` — 960ms, in=552 (cached 0), out=21 (reasoning 0)

**call 3** turn 2 `jev` — 341ms, in=2,163 (cached 0), out=813 (reasoning 0)

**call 4** turn 2 `llm` — 836ms, in=557 (cached 0), out=22 (reasoning 0)

**call 5** turn 3 `jev` — 367ms, in=2,430 (cached 0), out=957 (reasoning 0)

**call 6** turn 3 `llm` — 1,259ms, in=606 (cached 0), out=20 (reasoning 0)

**call 7** turn 4 `jev` — 323ms, in=2,177 (cached 0), out=832 (reasoning 0)

**call 8** turn 4 `llm` — 1,119ms, in=651 (cached 0), out=38 (reasoning 0)

**call 9** turn 5 `jev` — 344ms, in=2,770 (cached 0), out=1,130 (reasoning 0)

**call 10** turn 5 `llm` — 1,337ms, in=741 (cached 0), out=38 (reasoning 0)

**call 11** turn 6 `jev` — 342ms, in=2,201 (cached 0), out=836 (reasoning 0)

**call 12** turn 6 `llm` — 939ms, in=797 (cached 0), out=26 (reasoning 0)

**call 13** turn 7 `jev` — 321ms, in=2,245 (cached 0), out=861 (reasoning 0)

**call 14** turn 7 `llm` — 1,599ms, in=831 (cached 0), out=22 (reasoning 0)

**call 15** turn 8 `jev` — 324ms, in=2,144 (cached 0), out=804 (reasoning 0)

**call 16** turn 8 `llm` — 10,037ms, in=2,368 (cached 0), out=463 (reasoning 0)

**call 17** turn 9 `jev` — 794ms, in=3,464 (cached 0), out=1,210 (reasoning 0)

**call 18** turn 9 `llm` — 2,094ms, in=1,414 (cached 0), out=63 (reasoning 0)

**call 19** turn 10 `jev` — 374ms, in=2,796 (cached 0), out=1,069 (reasoning 0)

**call 20** turn 10 `llm` — 765ms, in=1,482 (cached 0), out=9 (reasoning 0)

**call 21** turn 11 `jev` — 335ms, in=3,047 (cached 0), out=1,235 (reasoning 0)

**call 22** turn 11 `llm` — 1,434ms, in=1,489 (cached 0), out=16 (reasoning 0)

**call 23** turn 12 `jev` — 373ms, in=2,804 (cached 0), out=1,089 (reasoning 0)

**call 24** turn 12 `llm` — 879ms, in=1,591 (cached 0), out=19 (reasoning 0)

**call 25** turn 13 `jev` — 383ms, in=2,777 (cached 0), out=1,067 (reasoning 0)

**call 26** turn 13 `llm` — 2,910ms, in=1,765 (cached 0), out=99 (reasoning 0)

**call 27** turn 14 `jev` — 355ms, in=2,984 (cached 0), out=1,153 (reasoning 0)

**call 28** turn 14 `llm` — 2,111ms, in=1,813 (cached 0), out=60 (reasoning 0)

**call 29** turn 15 `jev` — 330ms, in=2,910 (cached 0), out=1,117 (reasoning 0)

**call 30** turn 15 `llm` — 1,830ms, in=1,883 (cached 0), out=64 (reasoning 0)

### jev / messy_named_court_instead_of_area — 35.5s, 14 turns

- turn 1: 1,764ms
- turn 2: 1,170ms
- turn 3: 1,545ms
- turn 4: 1,163ms
- turn 5: 1,122ms
- turn 6: 1,054ms
- turn 7: 14,917ms
- turn 8: 2,114ms
- turn 9: 1,197ms
- turn 10: 866ms
- turn 11: 1,315ms
- turn 12: 2,431ms
- turn 13: 2,581ms
- turn 14: 2,262ms

**call 1** turn 1 `jev` — 800ms, in=2,559 (cached 0), out=1,056 (reasoning 0)

**call 2** turn 1 `llm` — 954ms, in=565 (cached 0), out=25 (reasoning 0)

**call 3** turn 2 `jev` — 362ms, in=2,384 (cached 0), out=945 (reasoning 0)

**call 4** turn 2 `llm` — 801ms, in=601 (cached 0), out=23 (reasoning 0)

**call 5** turn 3 `jev` — 345ms, in=2,164 (cached 0), out=813 (reasoning 0)

**call 6** turn 3 `llm` — 1,191ms, in=608 (cached 0), out=41 (reasoning 0)

**call 7** turn 4 `jev` — 316ms, in=2,415 (cached 0), out=950 (reasoning 0)

**call 8** turn 4 `llm` — 836ms, in=694 (cached 0), out=26 (reasoning 0)

**call 9** turn 5 `jev` — 316ms, in=2,188 (cached 0), out=836 (reasoning 0)

**call 10** turn 5 `llm` — 796ms, in=738 (cached 0), out=23 (reasoning 0)

**call 11** turn 6 `jev` — 303ms, in=2,182 (cached 0), out=833 (reasoning 0)

**call 12** turn 6 `llm` — 737ms, in=767 (cached 0), out=15 (reasoning 0)

**call 13** turn 7 `jev` — 306ms, in=2,136 (cached 0), out=804 (reasoning 0)

**call 14** turn 7 `llm` — 14,596ms, in=2,218 (cached 0), out=511 (reasoning 0)

**call 15** turn 8 `jev` — 828ms, in=3,295 (cached 0), out=1,096 (reasoning 0)

**call 16** turn 8 `llm` — 1,279ms, in=1,372 (cached 0), out=48 (reasoning 0)

**call 17** turn 9 `jev` — 417ms, in=2,770 (cached 0), out=1,067 (reasoning 0)

**call 18** turn 9 `llm` — 764ms, in=1,447 (cached 0), out=9 (reasoning 0)

**call 19** turn 10 `jev` — 325ms, in=2,828 (cached 0), out=1,121 (reasoning 0)

**call 20** turn 10 `llm` — 531ms, in=1,441 (cached 0), out=11 (reasoning 0)

**call 21** turn 11 `jev` — 367ms, in=2,786 (cached 0), out=1,087 (reasoning 0)

**call 22** turn 11 `llm` — 936ms, in=1,532 (cached 0), out=25 (reasoning 0)

**call 23** turn 12 `jev` — 338ms, in=2,768 (cached 0), out=1,064 (reasoning 0)

**call 24** turn 12 `llm` — 2,081ms, in=1,720 (cached 0), out=89 (reasoning 0)

**call 25** turn 13 `jev` — 309ms, in=2,907 (cached 0), out=1,120 (reasoning 0)

**call 26** turn 13 `llm` — 2,259ms, in=1,709 (cached 0), out=63 (reasoning 0)

**call 27** turn 14 `jev` — 349ms, in=2,854 (cached 0), out=1,093 (reasoning 0)

**call 28** turn 14 `llm` — 1,910ms, in=1,827 (cached 0), out=67 (reasoning 0)

### jev / messy_out_of_range_duration — 41.2s, 14 turns

- turn 1: 1,462ms
- turn 2: 1,187ms
- turn 3: 1,611ms
- turn 4: 1,756ms
- turn 5: 1,902ms
- turn 6: 2,512ms
- turn 7: 13,664ms
- turn 8: 2,328ms
- turn 9: 875ms
- turn 10: 981ms
- turn 11: 1,310ms
- turn 12: 3,316ms
- turn 13: 5,108ms
- turn 14: 3,140ms

**call 1** turn 1 `jev` — 799ms, in=2,492 (cached 0), out=1,028 (reasoning 0)

**call 2** turn 1 `llm` — 654ms, in=555 (cached 0), out=13 (reasoning 0)

**call 3** turn 2 `jev` — 370ms, in=2,156 (cached 0), out=813 (reasoning 0)

**call 4** turn 2 `llm` — 813ms, in=551 (cached 0), out=23 (reasoning 0)

**call 5** turn 3 `jev` — 304ms, in=2,229 (cached 0), out=866 (reasoning 0)

**call 6** turn 3 `llm` — 1,298ms, in=613 (cached 0), out=45 (reasoning 0)

**call 7** turn 4 `jev` — 357ms, in=2,207 (cached 0), out=838 (reasoning 0)

**call 8** turn 4 `llm` — 1,391ms, in=670 (cached 0), out=40 (reasoning 0)

**call 9** turn 5 `jev` — 292ms, in=2,358 (cached 0), out=923 (reasoning 0)

**call 10** turn 5 `llm` — 1,602ms, in=730 (cached 0), out=17 (reasoning 0)

**call 11** turn 6 `jev` — 333ms, in=2,236 (cached 0), out=861 (reasoning 0)

**call 12** turn 6 `llm` — 2,169ms, in=759 (cached 0), out=42 (reasoning 0)

**call 13** turn 7 `jev` — 310ms, in=2,163 (cached 0), out=804 (reasoning 0)

**call 14** turn 7 `llm` — 13,326ms, in=2,228 (cached 0), out=501 (reasoning 0)

**call 15** turn 8 `jev` — 891ms, in=3,490 (cached 0), out=1,210 (reasoning 0)

**call 16** turn 8 `llm` — 1,430ms, in=1,401 (cached 0), out=47 (reasoning 0)

**call 17** turn 9 `jev` — 309ms, in=2,768 (cached 0), out=1,067 (reasoning 0)

**call 18** turn 9 `llm` — 559ms, in=1,459 (cached 0), out=9 (reasoning 0)

**call 19** turn 10 `jev` — 315ms, in=2,983 (cached 0), out=1,207 (reasoning 0)

**call 20** turn 10 `llm` — 653ms, in=1,457 (cached 0), out=17 (reasoning 0)

**call 21** turn 11 `jev` — 329ms, in=2,794 (cached 0), out=1,089 (reasoning 0)

**call 22** turn 11 `llm` — 969ms, in=1,560 (cached 0), out=13 (reasoning 0)

**call 23** turn 12 `jev` — 339ms, in=2,769 (cached 0), out=1,064 (reasoning 0)

**call 24** turn 12 `llm` — 2,968ms, in=1,725 (cached 0), out=108 (reasoning 0)

**call 25** turn 13 `jev` — 350ms, in=2,940 (cached 0), out=1,122 (reasoning 0)

**call 26** turn 13 `llm` — 4,744ms, in=1,782 (cached 0), out=67 (reasoning 0)

**call 27** turn 14 `jev` — 447ms, in=2,971 (cached 0), out=1,151 (reasoning 0)

**call 28** turn 14 `llm` — 2,689ms, in=1,901 (cached 0), out=63 (reasoning 0)


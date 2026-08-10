---
type: Report
title: "B02-DUPLICATE-MARGIN — okf-revision"
description: "Katalogweiter Near-Duplicate-Scan plus Vorher/Nachher-Messung der Hypothese, Konzept-Kopien nähmen dem lexikalischen Arm den BM25-Margin — Hypothese widerlegt, die Schwelle in _keyword_top1_is_confident ist auf diesem Korpus strukturell unerreichbar."
tags:
  - tpic
  - okf-revision
timestamp: 2026-08-10T14:11:31Z
---

# B02 — Duplicate concepts steal the BM25 margin

bean `OKFT-hjqp`, Elternbean `OKFT-hkze`. Reine Messung: der echte Katalog `~/Obsidian/Knowledge-Catalogue` wurde ausschließlich gelesen, alle Mutationen liefen auf einer Kopie im Scratchpad. Kein Merge, kein `ce-okf`-Aufruf, keine Katalogänderung.

## Verdikt

**Hypothese widerlegt.** Die Duplikate sind real und zahlreicher als im bean vermutet, aber sie sind nicht die Ursache dafür, dass `ralph wiggum loop` und `integration` an den semantischen Arm fallen. Nach Entfernen der Kopien reißt die Margin-Bedingung in `_keyword_top1_is_confident` weiterhin, in beiden Fällen. Die Schwelle `top1 >= (1 + SEMANTIC_MARGIN_RATIO) * top2` mit `SEMANTIC_MARGIN_RATIO = 0.5` verlangt, dass der Zweitplatzierte höchstens zwei Drittel des BM25-Rohscores des Erstplatzierten erreicht; auf einem Korpus von 2590 Konzepten erreicht kein einziger Mehrtreffer-Query des kanonischen Eval-Satzes dieses Verhältnis.

## 1. Katalogweiter Near-Duplicate-Scan

Der Scan verwendet die Produktions-Semantik: `cli/okf-cli.py` wird als Modul importiert, die Kandidatenmenge stammt aus `list_bundles()` + `iter_concepts()`, die Frontmatter-Werte aus `split_frontmatter()`. Damit zählt genau das, was der Index sieht — `index.md`, `log.md`, `readme.md`, `index-map.md` sind `RESERVED` und fallen raus, ebenso alle `_`-präfixierten Top-Level-Verzeichnisse (`_inbox/`, `_plan/`) und `assets/`. Ein naiver `os.walk` über alle `*.md` liefert stattdessen 2813 Dateien und dadurch Scheingruppen wie `index` (154×) oder `INDEX-MAP` (6×); die Zahlen unten sind die bereinigten.

| Kennzahl | Wert |
| --- | --- |
| indexierte Konzepte | 2590 |
| Gruppen mit identischem Concept-Slug (n > 1) | 88 |
| zusätzliche Gruppen mit identischem `title:` bei abweichendem Slug | 17 |
| Gruppen gesamt | 105 |
| beteiligte Konzeptdateien | 222 |

Die beiden im bean genannten Fälle sind **bestätigt**: `ralph-wiggum-loop` existiert 3× mit drei verschiedenen md5, `integration` 2×. Eine Gruppe ist ein Scan-Artefakt und kein Duplikat: `GLOSSARY` (5×) sind die je eigenen Glossare der fünf symlink-eingebundenen Repo-Bundles und tragen bewusst denselben Dateinamen.

Dominantes Muster: 53 der 88 Slug-Gruppen liegen ausschließlich auf der Achse `ai-wiki/<slug>.md` gegen `general-knowledge-wiki/<subdir>/<slug>.md`, wobei die `general-knowledge-wiki`-Kopie fast immer die größere ist. Das gleiche Muster liegt unter 13 der 17 Titel-Gruppen, dort mit übersetztem Slug (`ai-wiki/ai-agent.md` gegen `general-knowledge-wiki/ai-agentic-coding/ki-agent.md`). Zusammen sind das 66 Gruppen über 132 Dateien. Ein zweites Muster ist rein `qm-wiki`-intern (6 Gruppen): derselbe Begriff als `ChecklistItem`, `Reference` und `Concept` in drei Unterordnern — das sind bewusst verschiedene Sichten auf einen Begriff, keine versehentlichen Kopien.

### Gruppen mit identischem Concept-Slug (88)

| Slug | n | Pfade · md5 (8) · Bytes |
| --- | --- | --- |
| `agentic-workflow` | 2 | `general-knowledge-wiki/ai-agentic-coding/agentic-workflow.md` · `10fc284b` · 2576 B<br>`ai-wiki/agentic-workflow.md` · `02c14c80` · 1887 B |
| `ai-operating-system` | 2 | `general-knowledge-wiki/ai-agentic-coding/ai-operating-system.md` · `47636a68` · 2886 B<br>`ai-wiki/ai-operating-system.md` · `f39c15f6` · 2071 B |
| `algorithmen-zur-verschleierung-oder-taeuschung` | 2 | `general-knowledge-wiki/ai-agentic-coding/algorithmen-zur-verschleierung-oder-taeuschung.md` · `3eede610` · 3035 B<br>`ai-wiki/algorithmen-zur-verschleierung-oder-taeuschung.md` · `7323c477` · 2199 B |
| `algorithmic-fog` | 2 | `general-knowledge-wiki/ai-agentic-coding/algorithmic-fog.md` · `f45a8336` · 3003 B<br>`ai-wiki/algorithmic-fog.md` · `49c1459d` · 2248 B |
| `andrej-karpathy` | 2 | `general-knowledge-wiki/ai-agentic-coding/andrej-karpathy.md` · `8f6ef7a2` · 2285 B<br>`ai-wiki/andrej-karpathy.md` · `e1628a30` · 1850 B |
| `anthropic` | 2 | `general-knowledge-wiki/ai-agentic-coding/anthropic.md` · `98f2129c` · 2084 B<br>`ai-wiki/anthropic.md` · `012d1dbd` · 1381 B |
| `anthropic-api` | 2 | `general-knowledge-wiki/ai-agentic-coding/anthropic-api.md` · `cd7898e7` · 2501 B<br>`ai-wiki/anthropic-api.md` · `c56f6e48` · 1531 B |
| `anthropic-messages-api` | 2 | `general-knowledge-wiki/ai-agentic-coding/anthropic-messages-api.md` · `cf3f96fe` · 2338 B<br>`ai-wiki/anthropic-messages-api.md` · `0b4299bc` · 1512 B |
| `anytype` | 2 | `home-lab-wiki/services/anytype.md` · `707227b8` · 2438 B<br>`general-knowledge-wiki/personal-knowledge-mgmt/anytype.md` · `492642b6` · 2357 B |
| `auditprogramm` | 2 | `qm-wiki/qmb-training/knowledge-blocks/auditprogramm.md` · `c634ac74` · 5239 B<br>`qm-wiki/term-glossary/auditprogramm.md` · `a13c56e4` · 445 B |
| `authentifizierung` | 2 | `general-knowledge-wiki/misc/authentifizierung.md` · `8a484111` · 849 B<br>`ai-wiki/authentifizierung.md` · `2dfa7213` · 723 B |
| `automation-bias` | 2 | `general-knowledge-wiki/ai-agentic-coding/automation-bias.md` · `c3334043` · 1702 B<br>`ai-wiki/automation-bias.md` · `753f2e43` · 1149 B |
| `autoresearch` | 2 | `general-knowledge-wiki/ai-agentic-coding/autoresearch.md` · `8064149c` · 2311 B<br>`ai-wiki/autoresearch.md` · `236fc1ca` · 1876 B |
| `beta-features` | 2 | `general-knowledge-wiki/ai-agentic-coding/beta-features.md` · `5342d4c9` · 2123 B<br>`ai-wiki/beta-features.md` · `ae481494` · 1474 B |
| `big-data` | 2 | `general-knowledge-wiki/defense-and-geopolitics/big-data.md` · `b50df9ab` · 1690 B<br>`ai-wiki/big-data.md` · `7a40083e` · 1028 B |
| `block-referenzen` | 2 | `general-knowledge-wiki/personal-knowledge-mgmt/block-referenzen.md` · `5e176349` · 2183 B<br>`obsidian-vault-mgmt-wiki/grundlagen/block-referenzen.md` · `d9506bf6` · 1497 B |
| `browsecomp` | 2 | `general-knowledge-wiki/ai-agentic-coding/browsecomp.md` · `e660cfe5` · 2370 B<br>`ai-wiki/browsecomp.md` · `8d15f120` · 1819 B |
| `chain-of-thought-verification` | 2 | `general-knowledge-wiki/ai-agentic-coding/chain-of-thought-verification.md` · `2155b9f8` · 2503 B<br>`ai-wiki/chain-of-thought-verification.md` · `9ba52ce7` · 2259 B |
| `claude-code` | 2 | `general-knowledge-wiki/ai-agentic-coding/claude-code.md` · `61b622de` · 1612 B<br>`ai-wiki/claude-code.md` · `f935183e` · 780 B |
| `claude-dispatch` | 2 | `ai-wiki/claude-dispatch.md` · `b1951ed7` · 2789 B<br>`general-knowledge-wiki/ai-agentic-coding/claude-dispatch.md` · `900ad3e8` · 2353 B |
| `claude-haiku` | 2 | `general-knowledge-wiki/ai-agentic-coding/claude-haiku.md` · `b747e088` · 1904 B<br>`ai-wiki/claude-haiku.md` · `66fe768a` · 1388 B |
| `claude-project-template` | 2 | `dev-wiki/project-bootstrap/claude-project-template.md` · `cb999049` · 2408 B<br>`claude-code-wiki/claude-md-conventions/claude-project-template.md` · `fd3c8ea5` · 2315 B |
| `cli` | 2 | `general-knowledge-wiki/misc/cli.md` · `9d6fec9c` · 906 B<br>`ai-wiki/cli.md` · `8eab547c` · 380 B |
| `cognitive-electronic-warfare` | 2 | `general-knowledge-wiki/defense-and-geopolitics/cognitive-electronic-warfare.md` · `234de101` · 1829 B<br>`ai-wiki/cognitive-electronic-warfare.md` · `161232ac` · 1245 B |
| `confirmation-bias` | 2 | `general-knowledge-wiki/ai-agentic-coding/confirmation-bias.md` · `24716c73` · 1446 B<br>`ai-wiki/confirmation-bias.md` · `4abdf6fe` · 1089 B |
| `context-anxiety` | 3 | `general-knowledge-wiki/ai-agentic-coding/context-anxiety.md` · `7ae24e33` · 2939 B<br>`claude-code-wiki/sessions-workflow/context-anxiety.md` · `de00d70b` · 2269 B<br>`ai-wiki/context-anxiety.md` · `f519772b` · 2061 B |
| `context-reset` | 3 | `general-knowledge-wiki/ai-agentic-coding/context-reset.md` · `d2e3336e` · 2847 B<br>`claude-code-wiki/sessions-workflow/context-reset.md` · `f27550f3` · 2253 B<br>`ai-wiki/context-reset.md` · `16389de6` · 1944 B |
| `cron-job` | 3 | `claude-code-wiki/sessions-workflow/cron-job.md` · `1280d741` · 934 B<br>`ai-wiki/cron-job.md` · `b015f973` · 915 B<br>`general-knowledge-wiki/misc/cron-job.md` · `130385aa` · 837 B |
| `custom-endpoint` | 2 | `general-knowledge-wiki/ai-agentic-coding/custom-endpoint.md` · `73687d7e` · 2810 B<br>`ai-wiki/custom-endpoint.md` · `4b320720` · 1602 B |
| `data-ui-convention` | 2 | `devd2-okf/architecture/data-ui-convention.md` · `959287e2` · 7969 B<br>`dev-wiki/debug-interface/data-ui-convention.md` · `efad5a92` · 5766 B |
| `dataview` | 2 | `general-knowledge-wiki/ai-agentic-coding/dataview.md` · `c97e939b` · 1969 B<br>`obsidian-vault-mgmt-wiki/plugins/dataview.md` · `acaa01e4` · 1701 B |
| `dateiname` | 2 | `general-knowledge-wiki/personal-knowledge-mgmt/dateiname.md` · `b85036c3` · 2100 B<br>`obsidian-vault-mgmt-wiki/konventionen-templates/dateiname.md` · `d4df2612` · 1767 B |
| `datenfusion` | 2 | `general-knowledge-wiki/defense-and-geopolitics/datenfusion.md` · `b125e4b9` · 1935 B<br>`ai-wiki/datenfusion.md` · `4f23cbe6` · 1151 B |
| `delete-files-by-yaml-properties` | 2 | `obsidian-vault-mgmt-wiki/skripts/delete-files-by-yaml-properties.md` · `478b0553` · 1139 B<br>`general-knowledge-wiki/misc/delete-files-by-yaml-properties.md` · `cd86ee4b` · 728 B |
| `dokumentation` | 2 | `general-knowledge-wiki/personal-knowledge-mgmt/dokumentation.md` · `fb0b1880` · 2130 B<br>`km-wiki/dokumentation.md` · `ece8e7ae` · 1390 B |
| `embeddings` | 2 | `general-knowledge-wiki/ai-agentic-coding/embeddings.md` · `f9b7316f` · 2244 B<br>`ai-wiki/embeddings.md` · `81344d1b` · 1501 B |
| `entity-extraction` | 2 | `general-knowledge-wiki/ai-agentic-coding/entity-extraction.md` · `b049f9ca` · 2646 B<br>`ai-wiki/entity-extraction.md` · `a7cc4ac0` · 2054 B |
| `fabric` | 2 | `general-knowledge-wiki/ai-agentic-coding/fabric.md` · `010f9931` · 2026 B<br>`ai-wiki/fabric.md` · `160f223b` · 1559 B |
| `file-explorer` | 2 | `general-knowledge-wiki/personal-knowledge-mgmt/file-explorer.md` · `e2262ca3` · 2036 B<br>`obsidian-vault-mgmt-wiki/grundlagen/file-explorer.md` · `af6c177e` · 1661 B |
| `fireflies-ai` | 2 | `general-knowledge-wiki/ai-agentic-coding/fireflies-ai.md` · `144abc6d` · 2286 B<br>`ai-wiki/fireflies-ai.md` · `3eddf459` · 1753 B |
| `GLOSSARY` | 5 | `lean-stack-okf/GLOSSARY.md` · `54bdbeea` · 9823 B<br>`devd2-okf/GLOSSARY.md` · `5c325a3e` · 5008 B<br>`okf-tools-okf/GLOSSARY.md` · `74f201ca` · 2912 B<br>`bew_BeWiki-Python-Download-okf/GLOSSARY.md` · `55db7d08` · 2882 B<br>`vc-search-okf/GLOSSARY.md` · `9fc144d7` · 1223 B |
| `graph-view` | 2 | `general-knowledge-wiki/personal-knowledge-mgmt/graph-view.md` · `5b77badb` · 2095 B<br>`obsidian-vault-mgmt-wiki/grundlagen/graph-view.md` · `0ca4c5c3` · 1507 B |
| `halluzinationen` | 2 | `ai-wiki/halluzinationen.md` · `3e9b840f` · 781 B<br>`general-knowledge-wiki/misc/halluzinationen.md` · `86ed372a` · 684 B |
| `harnesses` | 2 | `general-knowledge-wiki/ai-agentic-coding/harnesses.md` · `c07d9b89` · 2739 B<br>`ai-wiki/harnesses.md` · `c1b08c9b` · 1967 B |
| `hooks` | 3 | `general-knowledge-wiki/ai-agentic-coding/hooks.md` · `deda1646` · 2308 B<br>`claude-code-wiki/mcp-servers-plugins/hooks.md` · `46869283` · 1848 B<br>`ai-wiki/hooks.md` · `05177770` · 1724 B |
| `ingest-lessons-learned` | 2 | `qm-wiki/_intake/ingest-lessons-learned.md` · `1db7e16c` · 4670 B<br>`general-knowledge-wiki/_intake/ingest-lessons-learned.md` · `322a8b5f` · 3969 B |
| `integration` | 2 | `general-knowledge-wiki/ai-agentic-coding/integration.md` · `4d3c9bfc` · 2875 B<br>`ai-wiki/integration.md` · `52a6a8d4` · 1542 B |
| `internes-audit` | 3 | `qm-wiki/qmb-training/knowledge-blocks/internes-audit.md` · `74401802` · 9340 B<br>`qm-wiki/checklist/internes-audit.md` · `14e0da50` · 962 B<br>`qm-wiki/story-line/internes-audit.md` · `dc8f7a7b` · 500 B |
| `internet-of-battlefield-things` | 2 | `general-knowledge-wiki/defense-and-geopolitics/internet-of-battlefield-things.md` · `506da1ec` · 2428 B<br>`ai-wiki/internet-of-battlefield-things.md` · `7949efb4` · 1218 B |
| `interpretability` | 2 | `claude-code-wiki/model-behavior-safety/interpretability.md` · `b32bb12c` · 6627 B<br>`ai-wiki/interpretability.md` · `e660a8f2` · 2296 B |
| `jit-heap-spray` | 2 | `general-knowledge-wiki/ai-agentic-coding/jit-heap-spray.md` · `bd3c1f1b` · 3034 B<br>`ai-wiki/jit-heap-spray.md` · `ec6485e4` · 2220 B |
| `just-enough-ai` | 2 | `general-knowledge-wiki/ai-agentic-coding/just-enough-ai.md` · `5efb3478` · 2443 B<br>`ai-wiki/just-enough-ai.md` · `81596bd3` · 1691 B |
| `kundenzufriedenheit` | 3 | `qm-wiki/qmb-training/knowledge-blocks/kundenzufriedenheit.md` · `d79c9903` · 2219 B<br>`qm-wiki/norm-reference/kundenzufriedenheit.md` · `b784c67b` · 2160 B<br>`qm-wiki/checklist/kundenzufriedenheit.md` · `320fe7ea` · 744 B |
| `large-language-models` | 2 | `general-knowledge-wiki/ai-agentic-coding/large-language-models.md` · `1e02e646` · 2893 B<br>`ai-wiki/large-language-models.md` · `734ba4c5` · 2145 B |
| `lieferantenbewertung` | 2 | `qm-wiki/qmb-training/knowledge-blocks/lieferantenbewertung.md` · `0b73c57d` · 1348 B<br>`qm-wiki/checklist/lieferantenbewertung.md` · `ed0a1e9d` · 991 B |
| `lightrag` | 2 | `ai-wiki/lightrag.md` · `fb510379` · 825 B<br>`general-knowledge-wiki/ai-agentic-coding/lightrag.md` · `e19fb92a` · 825 B |
| `lm-studio` | 2 | `general-knowledge-wiki/ai-agentic-coding/lm-studio.md` · `16337421` · 2180 B<br>`ai-wiki/lm-studio.md` · `057a035a` · 1522 B |
| `local-rest-api` | 2 | `general-knowledge-wiki/personal-knowledge-mgmt/local-rest-api.md` · `811bf7a2` · 2342 B<br>`obsidian-vault-mgmt-wiki/plugins/local-rest-api.md` · `8a8b41a3` · 2072 B |
| `mammouth-ai` | 2 | `general-knowledge-wiki/ai-agentic-coding/mammouth-ai.md` · `710d8326` · 2864 B<br>`ai-wiki/mammouth-ai.md` · `34cd942a` · 1529 B |
| `map-of-content` | 2 | `general-knowledge-wiki/personal-knowledge-mgmt/map-of-content.md` · `158eb2f6` · 2497 B<br>`obsidian-vault-mgmt-wiki/grundlagen/map-of-content.md` · `bfa9625a` · 1652 B |
| `mcp` | 3 | `ai-wiki/mcp.md` · `58be767f` · 1925 B<br>`claude-code-wiki/mcp-servers-plugins/mcp.md` · `d0011466` · 905 B<br>`general-knowledge-wiki/ai-agentic-coding/mcp.md` · `dffa53f5` · 832 B |
| `n8n` | 2 | `ai-wiki/n8n.md` · `c9fda816` · 994 B<br>`general-knowledge-wiki/ai-agentic-coding/n8n.md` · `8d2cb63c` · 931 B |
| `nanoclaw` | 2 | `general-knowledge-wiki/misc/nanoclaw.md` · `5d49499c` · 716 B<br>`ai-wiki/nanoclaw.md` · `97b0c31a` · 712 B |
| `obsidian` | 2 | `home-lab-wiki/services/obsidian.md` · `36ffd043` · 4001 B<br>`km-wiki/obsidian.md` · `95e89757` · 1815 B |
| `openai` | 2 | `general-knowledge-wiki/ai-agentic-coding/openai.md` · `3136f84c` · 725 B<br>`ai-wiki/openai.md` · `45d350b6` · 312 B |
| `openai-codex` | 2 | `general-knowledge-wiki/ai-agentic-coding/openai-codex.md` · `c84b71b4` · 2193 B<br>`ai-wiki/openai-codex.md` · `9c42f381` · 1701 B |
| `openclaw` | 2 | `general-knowledge-wiki/ai-agentic-coding/openclaw.md` · `482061eb` · 2463 B<br>`ai-wiki/openclaw.md` · `dcb3d4f9` · 1576 B |
| `opencode` | 2 | `general-knowledge-wiki/ai-agentic-coding/opencode.md` · `161b52f6` · 2647 B<br>`ai-wiki/opencode.md` · `6d4ae515` · 1989 B |
| `openrouter` | 2 | `general-knowledge-wiki/ai-agentic-coding/openrouter.md` · `99e683ec` · 2037 B<br>`ai-wiki/openrouter.md` · `0d2e4f69` · 1433 B |
| `project-glasswing` | 3 | `general-knowledge-wiki/ai-agentic-coding/project-glasswing.md` · `5caf0aed` · 3485 B<br>`ai-wiki/project-glasswing.md` · `c1ebf133` · 3275 B<br>`claude-code-wiki/model-behavior-safety/project-glasswing.md` · `d2fa2438` · 3101 B |
| `qwen` | 2 | `general-knowledge-wiki/ai-agentic-coding/qwen.md` · `25798acb` · 2554 B<br>`ai-wiki/qwen.md` · `e07a5e3a` · 1989 B |
| `rag` | 2 | `general-knowledge-wiki/ai-agentic-coding/rag.md` · `8dbe8599` · 2289 B<br>`ai-wiki/rag.md` · `d6200ca8` · 1566 B |
| `rag-anything` | 2 | `ai-wiki/rag-anything.md` · `fe1378e7` · 790 B<br>`general-knowledge-wiki/ai-agentic-coding/rag-anything.md` · `7b9a9554` · 771 B |
| `ralph-wiggum-loop` | 3 | `general-knowledge-wiki/ai-agentic-coding/ralph-wiggum-loop.md` · `d5eadf68` · 2425 B<br>`claude-code-wiki/sessions-workflow/ralph-wiggum-loop.md` · `00055059` · 1904 B<br>`ai-wiki/ralph-wiggum-loop.md` · `5f8f9b39` · 1784 B |
| `remy-gaskell` | 2 | `general-knowledge-wiki/ai-agentic-coding/remy-gaskell.md` · `d6ab3f35` · 2063 B<br>`ai-wiki/remy-gaskell.md` · `a4d6ec85` · 1414 B |
| `saas` | 2 | `ai-wiki/saas.md` · `55ef0824` · 940 B<br>`general-knowledge-wiki/misc/saas.md` · `91ee83a2` · 878 B |
| `skills` | 2 | `claude-code-wiki/skills-commands/skills.md` · `03b74a50` · 1291 B<br>`general-knowledge-wiki/misc/skills.md` · `29077d78` · 940 B |
| `slash-commands` | 3 | `general-knowledge-wiki/ai-agentic-coding/slash-commands.md` · `81c087fe` · 2088 B<br>`claude-code-wiki/skills-commands/slash-commands.md` · `6b0b1398` · 1850 B<br>`ai-wiki/slash-commands.md` · `203c03ca` · 1461 B |
| `steuerung-der-produktion-und-dienstleistungserbringung` | 2 | `qm-wiki/norm-reference/steuerung-der-produktion-und-dienstleistungserbringung.md` · `52c3e026` · 1518 B<br>`qm-wiki/checklist/steuerung-der-produktion-und-dienstleistungserbringung.md` · `abdda63d` · 915 B |
| `subagents` | 3 | `general-knowledge-wiki/ai-agentic-coding/subagents.md` · `b0972a19` · 2234 B<br>`claude-code-wiki/sessions-workflow/subagents.md` · `4a79958c` · 2084 B<br>`ai-wiki/subagents.md` · `adb542d8` · 1298 B |
| `swe-bench` | 2 | `general-knowledge-wiki/ai-agentic-coding/swe-bench.md` · `50d71199` · 2469 B<br>`ai-wiki/swe-bench.md` · `2dd2b3a4` · 2055 B |
| `token` | 2 | `ai-wiki/token.md` · `7e0f1532` · 2603 B<br>`general-knowledge-wiki/ai-agentic-coding/token.md` · `83313b06` · 1992 B |
| `tokens` | 2 | `linear-design-system/tokens/tokens.md` · `b65d375d` · 5389 B<br>`design-wiki/tokens.md` · `63524583` · 3593 B |
| `unified-memory` | 2 | `general-knowledge-wiki/ai-agentic-coding/unified-memory.md` · `eb7f5699` · 2407 B<br>`ai-wiki/unified-memory.md` · `a3abe5cb` · 1732 B |
| `verbesserung` | 2 | `qm-wiki/checklist/verbesserung.md` · `62c3871d` · 944 B<br>`qm-wiki/story-line/verbesserung.md` · `c1aa9e39` · 244 B |
| `vibecoding` | 2 | `general-knowledge-wiki/ai-agentic-coding/vibecoding.md` · `935825a0` · 2855 B<br>`ai-wiki/vibecoding.md` · `37971b41` · 1945 B |
| `wiki-links` | 2 | `general-knowledge-wiki/personal-knowledge-mgmt/wiki-links.md` · `2874e2b4` · 2614 B<br>`obsidian-vault-mgmt-wiki/grundlagen/wiki-links.md` · `34f3bfb7` · 1888 B |
| `zettelkasten` | 2 | `general-knowledge-wiki/personal-knowledge-mgmt/zettelkasten.md` · `aca31708` · 2794 B<br>`obsidian-vault-mgmt-wiki/grundlagen/zettelkasten.md` · `432a46ed` · 2602 B |

### Zusätzliche Gruppen mit identischem `title:` bei abweichendem Slug (17)

| title | n | Pfade · md5 (8) · Bytes |
| --- | --- | --- |
| architecture reference chain | 2 | `dev-arch-wiki/architecture-methodology/architecture-reference-chain.md` · `6ed4b4b4` · 17886 B<br>`dev-arch-wiki/governance/adrs/adr-0008-architecture-reference-chain.md` · `ca7e6d4c` · 1434 B |
| automatisierung | 2 | `general-knowledge-wiki/ai-agentic-coding/automatisierung.md` · `8df7f82c` · 1972 B<br>`ai-wiki/automation.md` · `5bbe45f2` · 1381 B |
| black-box-problematik | 2 | `general-knowledge-wiki/ai-agentic-coding/black-box-problematik.md` · `56741b80` · 1806 B<br>`ai-wiki/black-box-problem.md` · `42916cdf` · 1430 B |
| give me 18 minutes and i'll make you dangerously smart (with ai) | 2 | `ai-wiki/give-me-18-minutes-and-ill-make-you-dangerously-smart.md` · `12645280` · 3049 B<br>`ai-wiki/give-me-18-minutes-dangerously-smart-with-ai.md` · `e4c378e6` · 1834 B |
| how smart people are using claude code skills to automate anything | 2 | `ai-wiki/claude-code-skills-agentic-operating-system.md` · `d50a15e1` · 2512 B<br>`ai-wiki/claude-code-skills-automate-anything.md` · `358f89f5` · 2349 B |
| interpretierbarkeit | 2 | `ai-wiki/interpretability.md` · `e660a8f2` · 2296 B<br>`general-knowledge-wiki/ai-agentic-coding/interpretierbarkeit.md` · `7ab7e053` · 2284 B |
| ki-agent | 2 | `ai-wiki/ai-agent.md` · `ffea4c78` · 3206 B<br>`general-knowledge-wiki/ai-agentic-coding/ki-agent.md` · `3bc7faba` · 2824 B |
| ki-exoskelett | 2 | `general-knowledge-wiki/ai-agentic-coding/ki-exoskelett.md` · `f5874c34` · 2733 B<br>`ai-wiki/ai-exoskeleton.md` · `6ea36c92` · 2009 B |
| ki-modell | 2 | `general-knowledge-wiki/ai-agentic-coding/ki-modell.md` · `709c95fb` · 2982 B<br>`ai-wiki/ai-model.md` · `8b5e4a22` · 2280 B |
| ki-sicherheitsforschung | 2 | `general-knowledge-wiki/ai-agentic-coding/ki-sicherheitsforschung.md` · `1e33d2d7` · 3309 B<br>`ai-wiki/ai-safety-research.md` · `57f56308` · 2547 B |
| kontext-fenster | 2 | `general-knowledge-wiki/ai-agentic-coding/kontext-fenster.md` · `520bb399` · 2285 B<br>`ai-wiki/context-window.md` · `640d3261` · 1650 B |
| künstliche intelligenz | 2 | `general-knowledge-wiki/ai-agentic-coding/kuenstliche-intelligenz.md` · `9f15c8c6` · 2187 B<br>`ai-wiki/artificial-intelligence.md` · `bd4f2763` · 1586 B |
| map of content (moc) | 2 | `obsidian-vault-mgmt-wiki/grundlagen/map-of-content-moc.md` · `b35a37e6` · 2940 B<br>`obsidian-vault-mgmt-wiki/grundlagen/map-of-content.md` · `bfa9625a` · 1652 B |
| openai-kompatible api | 2 | `general-knowledge-wiki/ai-agentic-coding/openai-kompatible-api.md` · `1ac7692e` · 2162 B<br>`ai-wiki/openai-compatible-api.md` · `85f8bf87` · 1527 B |
| plan | 2 | `general-knowledge-wiki/ai-agentic-coding/plan.md` · `efd45769` · 2052 B<br>`ai-wiki/saas-plan.md` · `a293ec53` · 1322 B |
| tools (ki-agenten) | 2 | `general-knowledge-wiki/ai-agentic-coding/tools-ki-agenten.md` · `650917e4` · 2219 B<br>`ai-wiki/ai-agent-tools.md` · `310125d7` · 1478 B |
| wohlstandsfonds | 2 | `general-knowledge-wiki/ai-agentic-coding/wohlstandsfonds.md` · `b9b570af` · 2703 B<br>`ai-wiki/wealth-fund.md` · `5eb9c7be` · 1986 B |

## 2. Messaufbau

Die Kopie entstand mit `rsync -a --copy-links --exclude '.git/' --exclude '.obsidian/'` in den Scratchpad, inklusive `.fts/fts.sqlite` und `.tagvec/tag_vectors.sqlite`; `--copy-links` löst die fünf Repo-Bundle-Symlinks auf, damit keine Mutation je in ein echtes Repo zeigen kann.

Der Substrat-Nachweis: `find "ralph wiggum loop" --limit 10 --breakdown` liefert auf der Kopie byteweise dieselbe Ausgabe wie auf dem Original — dieselben drei Treffer in derselben Reihenfolge mit `cosine 0.54`, dieselben zwei stderr-Notizen (`lexical index is stale`, `semantic arm owns this ranking`). Die Kopie ist damit als Substrat gültig.

Um die Wirkung der Duplikate von der Wirkung des veralteten Index zu trennen, wurde auf der Kopie vor der Variante einmal `build-index` gelaufen (2590 Konzepte). Die BM25-Rohwerte änderten sich dabei nur in der vierten Nachkommastelle (28.763849 → 28.756292), die Rangfolge und die Margin-Entscheidung nicht — die Staleness ist für diesen Befund irrelevant.

Die Variante entfernte auf der Kopie `ai-wiki/ralph-wiggum-loop.md`, `claude-code-wiki/sessions-workflow/ralph-wiggum-loop.md` und `ai-wiki/integration.md`, löschte die drei zugehörigen Zeilen aus `concept_emb` in `.tagvec/tag_vectors.sqlite` (`delete ... ; select changes();` → `3`) und baute `.fts` neu (2587 Konzepte). Behalten wurde jeweils die reichste Kopie — dieselbe, die die Merge-Empfehlung unten vorschlägt.

Die Zwischenwerte, die `find` nicht ausgibt, stammen aus einer Sonde, die den Produktionscode importiert und `okf._fts_ranking`, `okf._rank_lexically` und `okf._keyword_top1_is_confident` direkt aufruft — kein nachgebautes Ranking, keine eigene Regex.

## 3. Die Schwelle

`_keyword_top1_is_confident` (`cli/okf-cli.py:1351`) entscheidet, welcher Arm das Ranking besitzt.

````python
    if not hits:
        return False
    if len(hits) == 1:
        return True
    top1, top2 = hits[0]["score"], hits[1]["score"]
    if top1 <= 0:
        return False
    return top1 >= (1 + SEMANTIC_MARGIN_RATIO) * top2
````

`SEMANTIC_MARGIN_RATIO = 0.5` (`cli/okf-cli.py:1187`). Die `score`-Werte kommen aus `_rank_lexically` und sind auf den eigenen Spitzenreiter normiert: `int(round(100 * s / top))`, `top1` ist also immer exakt `100`. Die Bedingung reduziert sich damit auf `top2 <= 66`, gleichbedeutend mit „der Zweitplatzierte erreicht höchstens zwei Drittel des BM25-Rohscores des Erstplatzierten". Dass die Konstante laut Docstring auf den Rohscores von `eval/hybrid_eval.py:151` gemessen wurde, ist unschädlich: der Test ist ein reiner Quotiententest und damit skaleninvariant, die Normierung verschiebt die Schwelle nicht.

## 4. `ralph wiggum loop`

Vorher, alle drei Kopien vorhanden:

````
raw bm25 (path, s):
   ai-wiki/ralph-wiggum-loop                                              28.756292
   claude-code-wiki/sessions-workflow/ralph-wiggum-loop                   28.634282
   general-knowledge-wiki/ai-agentic-coding/ralph-wiggum-loop             28.566107
   ai-wiki/anthropic-harness-design-context-reset-and-gan-evaluator       22.235473
normalized lexical hits:
   score=100  ai-wiki/ralph-wiggum-loop
   score=100  claude-code-wiki/sessions-workflow/ralph-wiggum-loop
   score= 99  general-knowledge-wiki/ai-agentic-coding/ralph-wiggum-loop
   score= 77  ai-wiki/anthropic-harness-design-context-reset-and-gan-evaluator
top1=100 top2=100  need top1 >= 1.5*top2 = 150.00  -> False
````

Nachher, nur `general-knowledge-wiki/ai-agentic-coding/ralph-wiggum-loop.md` übrig:

````
raw bm25 (path, s):
   general-knowledge-wiki/ai-agentic-coding/ralph-wiggum-loop             29.641692
   ai-wiki/anthropic-harness-design-context-reset-and-gan-evaluator       23.061471
   claude-code-wiki/sessions-workflow/context-reset                       22.699555
normalized lexical hits:
   score=100  general-knowledge-wiki/ai-agentic-coding/ralph-wiggum-loop
   score= 78  ai-wiki/anthropic-harness-design-context-reset-and-gan-evaluator
   score= 77  claude-code-wiki/sessions-workflow/context-reset
top1=100 top2=78  need top1 >= 1.5*top2 = 117.00  -> False
````

Der Margin verbessert sich messbar — der Zweitplatzierte fällt von `100` auf `78` — und reißt die Schwelle trotzdem: gefordert sind `<= 66`, gemessen sind `78`. Die Ausgabe von `find` bleibt entsprechend unverändert im semantischen Arm:

````
=== VARIANT find ralph ===
note: semantic arm owns this ranking (lexical top-1 lacked a clear margin)
------
score: cosine 0.54
title: Ralph Wiggum Loop
path: general-knowledge-wiki/ai-agentic-coding/ralph-wiggum-loop
provenance: semantic
````

Das Ergebnis ist für den Nutzer besser (eine statt drei identischer Zeilen), aber es kippt nicht an den lexikalischen Arm zurück. Die Kopien waren nicht die Ursache; die Ursache ist die Nachbarschaft `anthropic-harness-design-context-reset-and-gan-evaluator`, `context-reset`, `agent-harness-patterns-digest`, die über den Term `loop` bzw. das Prefix-Matching mitgezogen wird und bei 78 % des Spitzenscores landet.

## 5. `integration`

Hier trägt die Hypothese von vornherein nicht, denn die Kopie war nie der Zweitplatzierte.

Vorher:

````
normalized lexical hits:
   score=100  ai-wiki/integration
   score= 98  km-wiki/integriertes-wissensmanagement
   score= 97  general-knowledge-wiki/ai-agentic-coding/integration
   score= 95  dev-wiki/cole-medin-ai-coding/concepts/mcp-integration-layer
top1=100 top2=98  need top1 >= 1.5*top2 = 147.00  -> False
````

Nachher, `ai-wiki/integration.md` entfernt:

````
normalized lexical hits:
   score=100  km-wiki/integriertes-wissensmanagement
   score= 99  general-knowledge-wiki/ai-agentic-coding/integration
   score= 97  dev-wiki/cole-medin-ai-coding/concepts/mcp-integration-layer
top1=100 top2=99  need top1 >= 1.5*top2 = 148.50  -> False
````

Der Margin wird nach dem Entfernen der Kopie sogar schlechter (98 → 99), und das erwünschte Konzept verliert den lexikalischen Platz 1 an `km-wiki/integriertes-wissensmanagement`, das über Prefix-Matching auf `integr*` gewinnt. Der zugehörige `find`-Lauf zeigt das direkt: der semantische Arm besitzt weiterhin das Ranking, und `integriertes-wissensmanagement` erscheint als angehängter lexikalischer Treffer mit `score: 100/100`.

## 6. Kontrollmessung über den gesamten Eval-Satz

Damit die beiden Einzelfälle nicht als Zufall durchgehen, wurde `_keyword_top1_is_confident` auf dem unveränderten Original über alle 48 Queries aus `queries_v2.json` (40) und `queries_real.json` (8) ausgewertet — rein lexikalisch, ohne Netzaufruf.

| Kennzahl | Wert |
| --- | --- |
| Queries gesamt | 48 |
| lexikalischer Arm besitzt das Ranking | 1 |
| davon wegen Einzeltreffer (`len(hits) == 1`) | 1 |
| kleinster beobachteter `top2` über alle Mehrtreffer-Queries | 69 |
| für die Schwelle nötig | `<= 66` |

Der einzige Fall ist `jupyter pandas numpy conda`, und er gewinnt nicht über den Margin, sondern weil es nur einen einzigen Treffer gibt. Über den gesamten kanonischen Eval-Satz feuert die Margin-Bedingung also **kein einziges Mal**. Der kleinste je gemessene Zweitplatzierte liegt mit 69 noch drei Punkte über der Schwelle. Das ist eine Eigenschaft der BM25-Score-Kompression auf einem Korpus dieser Größe und Homogenität, nicht eine Eigenschaft der Duplikate.

## 7. Kostenseite

Von den 48 kanonischen Eval-Queries zeigen **11** auf ein Ziel, das zu einer Duplikatgruppe gehört (222 betroffene Konzeptpfade als Vergleichsmenge).

| Ziel | Query |
| --- | --- |
| `general-knowledge-wiki/ai-agentic-coding/fireflies-ai` | digitaler helfer protokolliert besprechungen eigenständig |
| `general-knowledge-wiki/ai-agentic-coding/kontext-fenster` | obergrenze der aufnahmefähigkeit bei chatbots |
| `ai-wiki/claude-dispatch` | bots aus hauseigener oberfläche beauftragen |
| `ai-wiki/ai-model` | Sorten von Algorithmen Aufbau und Aufsicht |
| `general-knowledge-wiki/personal-knowledge-mgmt/map-of-content` | handgepflegte Übersicht zusammengehöriger Artikel |
| `general-knowledge-wiki/ai-agentic-coding/anthropic` | Firma hinter dem Programmier-Assistenten aus Kalifornien |
| `general-knowledge-wiki/ai-agentic-coding/dataview` | metadaten auswerten erweiterung wissensarchiv |
| `general-knowledge-wiki/ai-agentic-coding/context-reset` | chatverlauf wegwerfen übergabenotiz fortsetzen |
| `general-knowledge-wiki/ai-agentic-coding/openai-codex` | chatgpt gegenstück konkurrenz vergleich |
| `dev-wiki/debug-interface/data-ui-convention` | data-ui konvention namensschema |
| `ai-wiki/ai-operating-system` | Persistente KI-Betriebsschicht auf Basis eines lokalen Second Brains |

Der Eval-Satz hat damit ein zweites, unabhängiges Problem: 11 von 48 Queries haben ein Gold-Target, für das im Katalog ein gleich gutes Alternativziel existiert. Jede Rangmessung dieser 11 Queries bestraft ein korrektes Ergebnis, wenn das Retrieval die andere Kopie zuerst liefert. Nebenbefund derselben Prüfung: ein Ziel existiert überhaupt nicht mehr, `home-lab-wiki/context/lessons/synology-spezifisch`.

## 8. Empfehlung zum Merge — als Empfehlung, nicht als Ausführung

Der Merge bleibt richtig, aber nicht als Retrieval-Fix. Er zahlt auf Pflegbarkeit, Index-Kosten (222 überflüssige Konzeptdateien, entsprechend viele Embeddings) und auf die Belastbarkeit des Eval-Satzes ein. Die Erwartung „danach gewinnt der lexikalische Arm" ist durch diese Messung ausgeschlossen und sollte nicht als Akzeptanzkriterium in ein Merge-bean geschrieben werden.

Für `ralph-wiggum-loop` ist `general-knowledge-wiki/ai-agentic-coding/ralph-wiggum-loop.md` (2425 B) die reichste Kopie, auch nach Crosslinks: 3 ausgehende Pfad-Links gegen 2 in der `claude-code-wiki`-Kopie und 0 in `ai-wiki/ralph-wiggum-loop.md`, die den Begriff `Agentic Workflow` nur als Text nennt. Nachzuziehen wären die eingehenden Verweise: 3 Dateien referenzieren `ai-wiki/ralph-wiggum-loop`, 2 die `claude-code-wiki`-Kopie, 1 die Zielkopie — überwiegend `index.md`-Listungen, die `okf-cli reindex` ohnehin neu erzeugt, sodass real nur die Fließtext-Verweise von Hand umzuhängen sind.

Für `integration` ist `general-knowledge-wiki/ai-agentic-coding/integration.md` (2875 B) die reichste Kopie mit deutlichem Abstand: 11 ausgehende Pfad-Links gegen 2, und mit 2 eingehenden Dateien gegen 1 auch die stärkere Anbindung. Hier ist zusätzlich zu prüfen, ob der Slug `integration` überhaupt trägt — er kollidiert im Prefix-Matching mit `integriertes-wissensmanagement` und `mcp-integration-layer`, und ein präziserer Titel würde dem Retrieval mehr helfen als der Merge.

Vor dem eigentlichen Merge sollte die dominante Achse als Ganzes entschieden werden statt Gruppe für Gruppe: 53 Slug-Gruppen plus 13 Titel-Gruppen liegen ausschließlich zwischen `ai-wiki` und `general-knowledge-wiki`. Das ist keine Sammlung von Einzelunfällen, sondern eine bundle-weite Doppelablage, die eine Richtungsentscheidung braucht (welches Bundle ist kanonisch), bevor 132 Dateien einzeln angefasst werden. Die `qm-wiki`-internen Gruppen (`internes-audit`, `kundenzufriedenheit`, `verbesserung`, …) sind davon auszunehmen: dort sind `checklist/`, `norm-reference/`, `story-line/` und `qmb-training/knowledge-blocks/` verschiedene Sichten auf denselben Begriff und ein gewolltes Muster.

## Findings

| ID | Sachverhalt | Status |
| --- | --- | --- |
| B01 | Die Margin-Bedingung `top1 >= 1.5 * top2` in `_keyword_top1_is_confident` feuert auf diesem Korpus für keine einzige Mehrtreffer-Query des kanonischen Eval-Satzes; der kleinste gemessene `top2` ist 69, nötig wären `<= 66`. Der lexikalische Arm besitzt das Ranking faktisch nur noch bei Einzeltreffern. | 🟣 offen |
| B02 | Die Hypothese aus `OKFT-hjqp`, Duplikate nähmen den Margin, ist widerlegt: Nach Entfernen der Kopien fällt `ralph wiggum loop` weiterhin an den semantischen Arm (`top2` 100 → 78, Schwelle 66), und bei `integration` verschlechtert sich der Margin sogar (98 → 99), weil der Zweitplatzierte nie die Kopie war. | 🟢 done |
| I01 | 105 Duplikatgruppen über 222 Konzeptdateien, davon 66 Gruppen (132 Dateien) ausschließlich auf der Achse `ai-wiki` gegen `general-knowledge-wiki`. Merge lohnt für Pflege und Indexkosten, braucht aber eine bundle-weite Richtungsentscheidung statt 105 Einzelentscheidungen. | 🟣 offen |
| I02 | 11 der 48 kanonischen Eval-Queries haben ein Gold-Target, für das ein gleichwertiges Duplikat existiert; ihre Rangmessung ist dadurch systematisch verzerrt. | 🟣 offen |
| T01 | `home-lab-wiki/context/lessons/synology-spezifisch` ist Ziel einer Eval-Query, existiert aber nicht mehr im Katalog. | 🟣 offen |
| Q01 | `SEMANTIC_MARGIN_RATIO = 0.5` stammt laut Docstring aus `eval/hybrid_eval.py:151`, das die R43-Qualität von 0.437 erzeugt hat. Wenn die Bedingung dort ebenfalls nie feuerte, war das gemessene Ergebnis faktisch „semantischer Arm allein" und der Wert 0.5 ist nie als Kompromiss kalibriert worden. Zu klären: mit welchem `MARGIN` reproduziert `hybrid_eval.py` heute welchen Wert, und existiert überhaupt ein Bereich, in dem der lexikalische Arm für literale Queries gewinnt, ohne Paraphrasen zu verschlechtern. | 🟣 offen |

## Nachweis: der echte Katalog ist unverändert

`git status --porcelain` in `~/Obsidian/Knowledge-Catalogue` ist vor und nach der Messung leer. Alle 2590 Konzeptdateien wurden nach Abschluss gegen die zu Beginn erhobenen md5-Summen nachgerechnet: 0 Abweichungen, 0 fehlende Dateien.

Eine Beobachtung ist offenzulegen: die md5 von `.fts/fts.sqlite` driftet während der Messung mehrfach (`37ad3ba3` → `b636abaf` → `bccad76f` → …), während `.tagvec/tag_vectors.sqlite` durchgehend bei `a43a048f74812d316693650bf5dfd828` bleibt. Beide Verzeichnisse stehen in `.gitignore` und sind nicht Teil des versionierten Katalogzustands.

Die Drift stammt nicht aus dieser Messung. Eine kontrollierte Probe — md5, dann `sqlite3` mit `MATCH`, dann `sqlite3 -readonly`, dann `sqlite3.connect` aus Python im Read-Write-Modus, dann wieder md5 — liefert viermal denselben Wert `e11210d2e0a13a6ab3c6c76952787f9a`. Lesende Zugriffe verändern die Datei also nicht. Die Ursache steht in `ps`: parallel zu dieser Messung läuft ein fremder Prozess gegen den Live-Katalog, `okf-cli.py --root /Users/erik/Obsidian/Knowledge-Catalogue find record absent structured labels discoverable only by browsing --limit 50`, gestartet aus `cli/eval/`. Zwischen zwei md5-Messungen im Abstand von 25 Sekunden, in denen dieser Auftrag nichts tat, änderten sich md5 und `mtime` erneut.

Dass der Indexinhalt unverändert ist, ist unabhängig belegt: die BM25-Rohwerte des Originals nach der Messung (28.763849 / 28.641645 / 28.573362) sind identisch mit denen der Kopie, die vor jeder Drift byteweise vom Original gezogen wurde.

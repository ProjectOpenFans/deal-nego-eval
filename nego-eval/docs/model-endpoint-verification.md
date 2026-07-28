# 模型端点核验

核验时间：2026-07-28

| 角色连接 | Base URL | 精确 model ID | 状态 |
|---|---|---|---|
| GLM | `http://192.168.55.233:8000/v1` | `GLM-5.2-NVFP4` | `/v1/models` 与 `/v1/chat/completions` HTTP 200 |
| Qwen | `http://192.168.55.237:8000/v1` | `Qwen3.6-27B-NVFP4` | `/v1/models` 与 `/v1/chat/completions` HTTP 200 |

当前固定路由：

- buyer negotiator：GLM
- seller negotiator：GLM
- buyer counterparty：Qwen
- seller counterparty：Qwen
- offer extractor：Qwen
- M2/M6/M11/M12 judges：Qwen，每项重复 3 次
- case 并发：4
- 每个 case 的 negotiation rerun：3
- 两个连接均设置 `trust_env: false`，避免内网请求误走 HTTP/SOCKS 代理
- negotiator / counterparty 输出上限：2048
- offer extractor 输出上限：1024
- judge 输出上限：1536，temperature 固定为 0.0
- Qwen 的 `chat_template_kwargs.enable_thinking=false`，避免 extractor/sim/judge
  把输出预算全部消耗在 reasoning 而不返回 JSON

可提交的配置使用 `COOLWEI_API_KEY` / `GLM_LOCAL_API_KEY` 环境变量。本地
直接运行配置 `configs/eval.clean.glm52-qwen36.local.yaml` 把 key 写在 YAML
里，但该文件被 git ignore，不会进入结果、viewer 或远端分支。

结果目录：`nego-eval/results/clean-coolwei-glm52-qwen36/`。

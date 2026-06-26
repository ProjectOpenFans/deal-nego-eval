#!/usr/bin/env python3
"""一键给 nego-eval 加 clean 臂 (clean prompt + 关skill工具)。
用法: 在 nego-eval 仓库根目录运行  python apply_clean_arm.py
幂等: 重复运行安全。改动 5 个文件 + 注入两个 CLEAN prompt 常量。
sim 不动。"""
import re, sys, pathlib

ROOT = pathlib.Path(".")
def edit(path, olds_news, must=True):
    p = ROOT/path
    s = p.read_text(encoding="utf-8"); orig=s
    for old,new in olds_news:
        if new in s and old not in s:   # 已应用
            continue
        if old not in s:
            if must: print(f"  ⚠ {path}: 找不到锚点(可能已改过),跳过一处"); 
            continue
        s = s.replace(old,new,1)
    if s!=orig:
        p.write_text(s,encoding="utf-8"); print(f"  ✓ {path}")
    else:
        print(f"  · {path} 无需改动(已应用)")

CLEAN_SELLER = pathlib.Path("clean_seller.txt").read_text(encoding="utf-8")
CLEAN_BUYER  = pathlib.Path("clean_buyer.txt").read_text(encoding="utf-8")

# 1) prompts.py: 改函数 + 追加常量
edit("negoeval/broker/prompts.py", [(
'''def broker_system_prompt(side: str) -> str:
    if side == "seller_broker":
        return SELLER_BROKER_SYSTEM_PROMPT
    return BUYER_BROKER_SYSTEM_PROMPT''',
'''def broker_system_prompt(side: str, variant: str = "full") -> str:
    if variant == "clean":
        if side == "seller_broker":
            return CLEAN_SELLER_BROKER_SYSTEM_PROMPT
        return CLEAN_BUYER_BROKER_SYSTEM_PROMPT
    if side == "seller_broker":
        return SELLER_BROKER_SYSTEM_PROMPT
    return BUYER_BROKER_SYSTEM_PROMPT''')])
# 追加常量(若未追加)
pf=ROOT/"negoeval/broker/prompts.py"; s=pf.read_text(encoding="utf-8")
if "CLEAN_SELLER_BROKER_SYSTEM_PROMPT" not in s:
    s += f'\n\nCLEAN_SELLER_BROKER_SYSTEM_PROMPT = """{CLEAN_SELLER}"""\n\nCLEAN_BUYER_BROKER_SYSTEM_PROMPT = """{CLEAN_BUYER}"""\n'
    pf.write_text(s,encoding="utf-8"); print("  ✓ prompts.py 注入 CLEAN 常量")
else:
    print("  · prompts.py CLEAN 常量已存在")

# 2) orchestrator.py
edit("negoeval/orchestrator.py", [
('    tools_enabled = skills == "on"\n    request, agent_side, sim_side = build_broker_request(inp, side, value_tools_enabled=tools_enabled)',
 '    tools_enabled = skills == "on"\n    prompt_variant = "clean" if skills == "clean" else "full"\n    request, agent_side, sim_side = build_broker_request(inp, side, value_tools_enabled=tools_enabled)'),
('''        build_provider("agent", mode=mode, case=case, agent_profile=agent_profile, llm_config=agent_cfg),
        allowlist=allowlist,
    )''',
'''        build_provider("agent", mode=mode, case=case, agent_profile=agent_profile, llm_config=agent_cfg),
        allowlist=allowlist,
        prompt_variant=prompt_variant,
    )''')])

# 3) agent/runner.py
edit("negoeval/agent/runner.py", [
('    def __init__(self, request: BrokerChatRequest, provider, *, allowlist: Optional[Set[str]]):',
 '    def __init__(self, request: BrokerChatRequest, provider, *, allowlist: Optional[Set[str]], prompt_variant: str = "full"):'),
('''            skills_used=self.skills_used,
        )''',
'''            skills_used=self.skills_used,
            prompt_variant=prompt_variant,
        )''')])

# 4) broker/runner.py
edit("negoeval/broker/runner.py", [
('''        skills_used: List[str],
        max_tool_rounds: int = 4,
    ) -> None:''',
'''        skills_used: List[str],
        max_tool_rounds: int = 4,
        prompt_variant: str = "full",
    ) -> None:'''),
('''        self.skills_used = skills_used
        self.max_tool_rounds = max_tool_rounds''',
'''        self.skills_used = skills_used
        self.max_tool_rounds = max_tool_rounds
        self.prompt_variant = prompt_variant'''),
('        system = f"""{broker_system_prompt(side)}',
 '        system = f"""{broker_system_prompt(side, self.prompt_variant)}')])

# 5) cli.py
edit("negoeval/cli.py", [
('choices=["on", "off", "both"]','choices=["on", "off", "both", "clean"]')])

print("\n完成。clean 臂已就绪: skills=clean → 双方 clean prompt(按side选) + 关skill工具; sim 不动。")

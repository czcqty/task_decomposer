from task_decomposer_app.llm import LLMClient
from task_decomposer_app.models import (
    AgentRunResult,
    DecomposedTask,
    Plan,
    SearchResult,
    Skill,
    SubAgentRun,
    SubAgentSpec,
    TaskRelation,
)
from task_decomposer_app.search import SearchService, format_search_results_for_prompt
from task_decomposer_app.skills import format_skills_for_prompt


CLARIFY_PROMPT = """
你是一个任务拆解型 Agent。请判断用户目标是否足够清晰。
如果目标足够清晰，返回空数组。
如果目标模糊，请提出 1-3 个最关键的澄清问题。

只返回 JSON，格式如下：
{"questions": ["问题1", "问题2"]}
"""

DECOMPOSE_PROMPT = """
你是一个任务拆解型 Agent（Task Decomposer）。
你的任务是把用户输入的自然语言目标拆成清晰、有序、可执行的步骤。

请遵循：
1. 先总结用户目标。
2. 给出 5-8 个子任务。
3. 每个子任务包含：id、标题、具体行动、预期产出。
4. 定义任务之间的关系（见下方 relations 字段说明）。
5. 如果提供了 Skills，请遵循其中的专业方法和约束。
6. 如果提供了联网搜索资料，请只把它当作参考上下文，不要编造资料来源。
7. 给出一个最适合立即开始的下一步。
8. 输出语言使用中文。

任务关系类型：
- "sequential"：A 完成后才能做 B（顺序执行）
- "parallel"：A 和 B 可以同时进行（并行）
- "blocking"：A 阻塞 B 的开始（A 未完成则 B 无法开始）
- "nesting"：A 是 B 的父任务（B 是 A 的子任务，B 在 A 内部完成）

只返回 JSON，格式如下：
{
  "goal": "目标总结",
  "tasks": [
    {
      "task_id": "task_1",
      "title": "子任务标题",
      "action": "具体行动",
      "output": "预期产出"
    }
  ],
  "relations": [
    {
      "source_id": "task_1",
      "target_id": "task_2",
      "relation_type": "sequential"
    }
  ],
  "next_step": "下一步行动建议",
  "sources": ["使用到的资料 URL，可为空数组"]
}
"""

SUB_AGENT_PROMPT = """
你是任务拆解系统中的一个 sub-agent。
你不负责输出最终计划，而是从你的角色视角提出独立拆解建议，帮助主 Agent 得到更可靠的结果。

请遵循：
1. 严格围绕你的角色职责分析目标。
2. 给出 4-7 个可执行子任务，每个任务必须有 task_id。
3. 定义任务之间的关系（sequential/parallel/blocking/nesting）。
4. 标出你认为最容易遗漏的风险或依赖。
5. 如果提供了 Skills，只使用与你角色相关的规则。
6. 输出语言使用中文。

只返回 JSON，格式如下：
{
  "goal": "你视角下的目标总结",
  "tasks": [
    {
      "task_id": "task_1",
      "title": "子任务标题",
      "action": "具体行动",
      "output": "预期产出"
    }
  ],
  "relations": [
    {
      "source_id": "task_1",
      "target_id": "task_2",
      "relation_type": "sequential"
    }
  ],
  "next_step": "你建议主 Agent 优先考虑的下一步",
  "sources": []
}
"""

MERGE_PROMPT = """
你是主 Agent，负责综合多个 sub-agent 的建议，输出最终任务拆解。

请遵循：
1. 保留最关键、最可执行的步骤，去掉重复项。
2. 如果 sub-agent 发现风险、依赖或验收问题，要把它们转化为具体任务或产出要求。
3. 最终输出 6-10 个任务，每个任务必须有 task_id。
4. 每个任务必须包含：标题、具体行动、预期产出。
5. 定义任务之间的关系（sequential/parallel/blocking/nesting）。
6. 输出语言使用中文。

任务关系类型：
- "sequential"：A 完成后才能做 B（顺序执行）
- "parallel"：A 和 B 可以同时进行（并行）
- "blocking"：A 阻塞 B 的开始（A 未完成则 B 无法开始）
- "nesting"：A 是 B 的父任务（B 是 A 的子任务，B 在 A 内部完成）

只返回 JSON，格式如下：
{
  "goal": "目标总结",
  "tasks": [
    {
      "task_id": "task_1",
      "title": "子任务标题",
      "action": "具体行动",
      "output": "预期产出"
    }
  ],
  "relations": [
    {
      "source_id": "task_1",
      "target_id": "task_2",
      "relation_type": "sequential"
    }
  ],
  "next_step": "下一步行动建议",
  "sources": ["使用到的资料 URL，可为空数组"]
}
"""


class TaskDecomposerAgent:
    def __init__(
        self,
        llm_client: LLMClient | None = None,
        search_service: SearchService | None = None,
        skills: list[Skill] | None = None,
        sub_agents: list[SubAgentSpec] | None = None,
    ):
        self.llm_client = llm_client
        self.search_service = search_service
        self.skills = skills or []
        self.sub_agents = sub_agents or []

    def clarify(self, goal: str) -> list[str]:
        if self.llm_client is None:
            return local_clarify(goal)

        result = self.llm_client.complete_json(CLARIFY_PROMPT, goal)
        questions = result.get("questions", [])
        return questions if isinstance(questions, list) else []

    def run(self, goal: str, context: str = "", search_query: str = "") -> AgentRunResult:
        warnings: list[str] = []
        search_results = self._search(search_query or goal, warnings)
        sub_agent_runs = self._run_sub_agents(goal, context, search_results, warnings)

        if self.llm_client is None:
            plan = local_decompose(goal, context, search_results, self.skills, sub_agent_runs)
            return AgentRunResult(
                plan=plan,
                warnings=warnings,
                search_results=search_results,
                sub_agent_runs=sub_agent_runs,
            )

        if sub_agent_runs:
            user_input = self._build_merge_input(goal, context, search_results, sub_agent_runs)
            result = self.llm_client.complete_json(MERGE_PROMPT, user_input)
        else:
            user_input = self._build_user_input(goal, context, search_results)
            result = self.llm_client.complete_json(DECOMPOSE_PROMPT, user_input)

        plan = plan_from_dict(result, fallback_goal=goal)
        return AgentRunResult(
            plan=plan,
            warnings=warnings,
            search_results=search_results,
            sub_agent_runs=sub_agent_runs,
        )

    def _run_sub_agents(
        self,
        goal: str,
        context: str,
        search_results: list[SearchResult],
        warnings: list[str],
    ) -> list[SubAgentRun]:
        runs: list[SubAgentRun] = []
        for spec in self.sub_agents:
            try:
                plan = self._run_one_sub_agent(spec, goal, context, search_results)
                runs.append(
                    SubAgentRun(
                        name=spec.name,
                        role=spec.role,
                        plan=plan,
                        skills=[skill.name for skill in spec.skills],
                    )
                )
            except Exception as error:
                warnings.append(f"{spec.name} 执行失败，已跳过：{error}")
        return runs

    def _run_one_sub_agent(
        self,
        spec: SubAgentSpec,
        goal: str,
        context: str,
        search_results: list[SearchResult],
    ) -> Plan:
        sub_agent_client = LLMClient(spec.model_config) if spec.model_config is not None else self.llm_client
        if sub_agent_client is None:
            return local_decompose_for_sub_agent(spec, goal, context, search_results)

        user_input = self._build_sub_agent_input(spec, goal, context, search_results)
        result = sub_agent_client.complete_json(SUB_AGENT_PROMPT, user_input)
        return plan_from_dict(result, fallback_goal=goal)

    def _search(self, query: str, warnings: list[str]) -> list[SearchResult]:
        if self.search_service is None:
            return []
        try:
            return self.search_service.search(query)
        except Exception as error:
            warnings.append(f"联网搜索失败，已继续执行：{error}")
            return []

    def _build_user_input(self, goal: str, context: str, search_results: list[SearchResult]) -> str:
        sections = [f"目标：{goal}"]
        if context:
            sections.append(f"补充信息：{context}")

        skill_text = format_skills_for_prompt(self.skills)
        if skill_text:
            sections.append(f"主 Agent Skills：\n{skill_text}")

        search_text = format_search_results_for_prompt(search_results)
        if search_text:
            sections.append(f"联网搜索资料：\n{search_text}")

        return "\n\n".join(sections)

    def _build_sub_agent_input(
        self,
        spec: SubAgentSpec,
        goal: str,
        context: str,
        search_results: list[SearchResult],
    ) -> str:
        sections = [
            f"sub-agent 名称：{spec.name}",
            f"sub-agent 角色：{spec.role or '未指定，请从独立审查视角拆解'}",
            f"目标：{goal}",
        ]
        if context:
            sections.append(f"补充信息：{context}")

        skill_text = format_skills_for_prompt(spec.skills)
        if skill_text:
            sections.append(f"{spec.name} Skills：\n{skill_text}")

        search_text = format_search_results_for_prompt(search_results)
        if search_text:
            sections.append(f"联网搜索资料：\n{search_text}")
        return "\n\n".join(sections)

    def _build_merge_input(
        self,
        goal: str,
        context: str,
        search_results: list[SearchResult],
        sub_agent_runs: list[SubAgentRun],
    ) -> str:
        sections = [self._build_user_input(goal, context, search_results)]
        blocks = []
        for run in sub_agent_runs:
            blocks.append(
                f"## {run.name}\n"
                f"角色：{run.role}\n"
                f"Skills：{', '.join(run.skills) or '无'}\n"
                f"{format_plan_for_prompt(run.plan)}"
            )
        sections.append("sub-agent 建议：\n" + "\n\n".join(blocks))
        return "\n\n".join(sections)


def plan_from_dict(result: dict, fallback_goal: str) -> Plan:
    raw_tasks = result.get("tasks", [])
    tasks = []
    for index, item in enumerate(raw_tasks):
        if not isinstance(item, dict):
            continue
        task_id = str(item.get("task_id", f"task_{index + 1}"))
        tasks.append(
            DecomposedTask(
                task_id=task_id,
                title=str(item.get("title", "未命名任务")),
                action=str(item.get("action", "")),
                output=str(item.get("output", "")),
            )
        )

    raw_relations = result.get("relations", [])
    relations = []
    if isinstance(raw_relations, list):
        for item in raw_relations:
            if not isinstance(item, dict):
                continue
            rel_type = str(item.get("relation_type", "sequential"))
            if rel_type not in ("sequential", "parallel", "blocking", "nesting"):
                rel_type = "sequential"
            relations.append(
                TaskRelation(
                    source_id=str(item.get("source_id", "")),
                    target_id=str(item.get("target_id", "")),
                    relation_type=rel_type,
                )
            )

    sources = result.get("sources", [])
    if not isinstance(sources, list):
        sources = []

    return Plan(
        goal=str(result.get("goal", fallback_goal)),
        tasks=tasks,
        next_step=str(result.get("next_step", "从第一个任务开始执行。")),
        relations=relations,
        sources=[str(source) for source in sources if source],
    )


def format_plan_for_prompt(plan: Plan) -> str:
    lines = [f"目标总结：{plan.goal}"]
    for index, task in enumerate(plan.tasks, start=1):
        lines.append(f"{index}. [{task.task_id}] {task.title}\n行动：{task.action}\n产出：{task.output}")
    if plan.relations:
        rel_strs = [f"  {r.source_id} --[{r.relation_type}]--> {r.target_id}" for r in plan.relations]
        lines.append("关系：\n" + "\n".join(rel_strs))
    lines.append(f"下一步：{plan.next_step}")
    if plan.sources:
        lines.append("来源：" + ", ".join(plan.sources))
    return "\n".join(lines)


def local_clarify(goal: str) -> list[str]:
    short_goal = len(goal.strip()) < 8
    vague_words = ["优化", "提升", "学会", "做好", "变好", "规划", "管理"]
    if short_goal or any(word in goal for word in vague_words):
        return [
            "你希望在多长时间内完成这个目标？",
            "你当前的基础或资源条件是什么？",
            "你判断目标完成的标准是什么？",
        ]
    return []


def local_decompose(
    goal: str,
    context: str = "",
    search_results: list[SearchResult] | None = None,
    skills: list[Skill] | None = None,
    sub_agent_runs: list[SubAgentRun] | None = None,
) -> Plan:
    merged_goal = goal if not context else f"{goal}（补充信息：{context}）"
    tasks = local_tasks_for_skills(skills or [])
    if sub_agent_runs:
        tasks = merge_local_tasks(tasks, sub_agent_runs)
    sources = [result.url for result in search_results or [] if result.url]
    relations = _build_sequential_relations(tasks)
    return Plan(
        goal=merged_goal,
        tasks=tasks,
        next_step="先写下目标的完成标准，然后马上完成第一个 30 分钟行动。",
        relations=relations,
        sources=sources,
    )


def local_decompose_for_sub_agent(
    spec: SubAgentSpec,
    goal: str,
    context: str = "",
    search_results: list[SearchResult] | None = None,
) -> Plan:
    skills = spec.skills
    if not skills:
        skills = skills_from_role(spec)
    plan = local_decompose(goal, context, search_results, skills)
    if spec.role:
        plan.goal = f"{goal}（{spec.name} 视角：{spec.role}）"
    return plan


def skills_from_role(spec: SubAgentSpec) -> list[Skill]:
    role = spec.role
    if "风险" in role or "审查" in role or "验收" in role:
        return [Skill(name="risk-review", content="", path="")]
    if "执行" in role or "MVP" in role or "里程碑" in role:
        return [Skill(name="execution", content="", path="")]
    if "用户" in role or "价值" in role or "场景" in role:
        return [Skill(name="user-value", content="", path="")]
    return []


def merge_local_tasks(main_tasks: list[DecomposedTask], sub_agent_runs: list[SubAgentRun]) -> list[DecomposedTask]:
    merged = list(main_tasks[:4])
    merged.append(
        DecomposedTask(
            task_id="task_merge_1",
            title="整合 sub-agent 建议",
            action="对比各 sub-agent 的拆解结果，保留共识任务，并标记冲突或遗漏。",
            output="合并后的任务路线图",
        )
    )
    merged.append(
        DecomposedTask(
            task_id="task_merge_2",
            title="补充风险和验收标准",
            action="把 sub-agent 提到的风险、依赖和检查点转化为验收条件。",
            output="风险与验收清单",
        )
    )
    for run in sub_agent_runs[:3]:
        if run.plan.tasks:
            task = run.plan.tasks[0]
            merged.append(
                DecomposedTask(
                    task_id=f"task_sub_{run.name}",
                    title=f"采纳 {run.name} 的关键建议",
                    action=task.action,
                    output=task.output,
                )
            )
    return merged[:10]


def _build_sequential_relations(tasks: list[DecomposedTask]) -> list[TaskRelation]:
    """为本地模式的任务列表自动构建顺序关系。"""
    relations = []
    for i in range(len(tasks) - 1):
        relations.append(
            TaskRelation(
                source_id=tasks[i].task_id,
                target_id=tasks[i + 1].task_id,
                relation_type="sequential",
            )
        )
    return relations


def _make_tasks(raw: list[tuple[str, str, str]]) -> list[DecomposedTask]:
    """从 (title, action, output) 元组列表批量构建 DecomposedTask，自动分配 task_id。"""
    return [
        DecomposedTask(task_id=f"task_{i + 1}", title=t, action=a, output=o)
        for i, (t, a, o) in enumerate(raw)
    ]


def local_tasks_for_skills(skills: list[Skill]) -> list[DecomposedTask]:
    skill_names = {skill.name for skill in skills}
    if "writing" in skill_names:
        return _make_tasks([
            ("确定写作定位", "明确读者、主题、体裁、篇幅和完成期限。", "写作定位说明"),
            ("收集素材", "列出需要查找的背景资料、案例、人物或灵感来源。", "素材清单"),
            ("设计结构", "搭建章节、情节或论点结构，标出每部分功能。", "写作大纲"),
            ("完成初稿", "按大纲逐段写作，优先完成完整版本。", "可通读的初稿"),
            ("修改润色", "检查逻辑、节奏、表达和错别字。", "修改版文稿"),
            ("安排写作节奏", "把剩余任务拆成每日或每周写作安排。", "写作日程表"),
        ])
    if "learning" in skill_names:
        return _make_tasks([
            ("诊断当前水平", "记录已有基础、薄弱点、可投入时间和目标标准。", "学习诊断表"),
            ("选择学习资源", "挑选 1-2 个主资源，避免资料过多导致分散。", "资源清单"),
            ("学习基础概念", "按主题学习核心概念，并写出自己的解释。", "概念笔记"),
            ("刻意练习", "设计小练习并及时对答案或找反馈。", "练习记录"),
            ("做一个小项目", "用学到的内容完成一个可展示成果。", "实践作品"),
            ("复盘测试", "用测验、讲解或作品验收确认掌握程度。", "复盘结论"),
        ])
    if "project" in skill_names or "planning" in skill_names or "execution" in skill_names:
        return _make_tasks([
            ("确认项目范围", "写清目标用户、核心需求、交付物和截止时间。", "项目范围说明"),
            ("定义 MVP", "选出最小可行版本，只保留必须功能。", "MVP 功能列表"),
            ("设计方案", "确定技术路线、页面或模块结构、数据流和验收标准。", "方案设计稿"),
            ("实现核心功能", "先完成主流程，再补充边缘能力。", "可运行版本"),
            ("测试与修正", "检查主流程、异常情况和输出质量。", "测试记录"),
            ("交付复盘", "整理使用说明、已知限制和下一步优化方向。", "交付说明"),
        ])
    if "risk-review" in skill_names:
        return _make_tasks([
            ("识别关键假设", "列出计划成立所依赖的前提、外部资源和时间限制。", "假设清单"),
            ("检查遗漏任务", "从准备、执行、测试、交付四个阶段寻找缺口。", "遗漏任务清单"),
            ("定义失败信号", "说明哪些迹象代表计划偏离或质量不足。", "风险信号列表"),
            ("补充验收标准", "为每个关键产出写出可检查的完成标准。", "验收标准表"),
        ])
    if "user-value" in skill_names:
        return _make_tasks([
            ("确认目标用户", "描述谁会使用最终成果，以及他们最核心的痛点。", "目标用户画像"),
            ("定义核心场景", "写出用户在什么情境下会使用这个成果。", "核心使用场景"),
            ("提炼用户收益", "说明完成后用户能更快、更省力或更可靠地做到什么。", "用户价值说明"),
            ("设计最小可用体验", "保留最能体现价值的主流程，推迟低价值功能。", "最小可用体验清单"),
        ])
    return _make_tasks([
        ("明确目标边界", "用一句话写下要达成的结果、时间范围和验收标准。", "一条清晰的目标定义"),
        ("梳理当前状态", "列出现有资源、限制条件、已完成内容和主要困难。", "当前情况清单"),
        ("拆分关键阶段", "把目标拆成准备、执行、检查、调整四个阶段。", "阶段路线图"),
        ("生成可执行动作", "为每个阶段写出具体动作，确保每个动作能在 30-90 分钟内推进。", "行动任务列表"),
        ("安排优先级", "按影响力和紧急程度排序，选出前三个最值得先做的任务。", "优先级列表"),
        ("设置检查点", "为每个阶段设置完成标志和复盘时间。", "检查点与复盘计划"),
    ])

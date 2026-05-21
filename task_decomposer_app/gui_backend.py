import sys
import os
import json
import traceback
import time
from pathlib import Path
from argparse import Namespace

# 保存真正的标准输出，用于 JSON 管道通信
real_stdout = sys.stdout
# 重定向全局 stdout 到 stderr，彻底防止第三方库或 print 语句污染 JSON 通信流
sys.stdout = sys.stderr

# 导入应用层组件
from task_decomposer_app.cli import (
    SkillRegistry,
    load_project_config,
    load_runtime_project,
    build_llm_client,
    load_main_skills,
    load_sub_agents,
    build_search_service,
    build_conversation_context,
    run_token_count,
    append_conversation,
    export_plan,
    append_run_log,
    append_failure_log,
    setup_user_config,
    validate_project,
    normalize_conversation_id,
    start_timer,
    elapsed_since,
    runtime_timestamp,
)
from task_decomposer_app.agent import TaskDecomposerAgent


def send_json(data):
    """向 C++ 客户端发送单行 JSON 数据"""
    try:
        real_stdout.write(json.dumps(data) + "\n")
        real_stdout.flush()
    except Exception as e:
        sys.stderr.write(f"发送 JSON 失败: {e}\n")


def handle_run_command(cmd_data):
    """处理任务拆解目标运行"""
    goal = cmd_data.get("goal", "").strip()
    if not goal:
        send_json({"type": "error", "message": "输入的目标不能为空。"})
        return

    conversation_id = normalize_conversation_id(cmd_data.get("conversation", "default"))
    project_name = cmd_data.get("project", "default").strip() or "default"
    
    # 模拟 CLI 参数
    args = Namespace(
        local=bool(cmd_data.get("local", False)),
        provider=str(cmd_data.get("provider", "auto")),
        model=cmd_data.get("model") or None,
        base_url=cmd_data.get("base_url") or None,
        skip_clarify=bool(cmd_data.get("skip_clarify", True)),
        user=os.getenv("TASK_DECOMPOSER_USER") or os.getenv("USERNAME") or os.getenv("USER") or "default",
        global_skill=[],
        skills_dir=cmd_data.get("skills_dir", "skills"),
        project=project_name,
        project_dir=None,
        sub_agent=[],
        sub_agent_mode="all",
        runtime_dir=cmd_data.get("runtime_dir", "project"),
        conversation=conversation_id,
        search=bool(cmd_data.get("search", True)),
        search_provider=str(cmd_data.get("search_provider", "auto")),
        search_query="",
        max_results=int(cmd_data.get("max_results", 5)),
        feedback="",
    )

    run_id = runtime_timestamp()
    timer = start_timer()

    send_json({"type": "status", "message": "✻ 正在初始化配置..."})

    # 1. 验证用户/项目配置
    if not args.local:
        try:
            setup_user_config(args)
        except Exception as error:
            send_json({"type": "error", "message": f"用户级配置不可用: {error}"})
            return
        
        # 验证项目配置
        checks = validate_project(args, project_name, require_api_keys=True) if project_name else []
        blocking = [msg for lvl, msg in checks if lvl == "ERROR"]
        if blocking:
            send_json({"type": "error", "message": f"项目模型配置未通过校验: {blocking[0]}"})
            return

    # 2. 加载项目与运行时上下文
    try:
        send_json({"type": "status", "message": "✻ 正在加载项目技能与上下文..."})
        registry = SkillRegistry(args.skills_dir)
        project = load_project_config(project_name, args.skills_dir)
        runtime_project = load_runtime_project(project.name if project else project_name, args.runtime_dir)

        llm_client = build_llm_client(args, runtime_project.main if runtime_project else None)
        main_skills = load_main_skills(registry, args, project)
        sub_agents = load_sub_agents(registry, args, project, runtime_project, goal)
        search_service = build_search_service(args, project_name)
    except Exception as error:
        send_json({"type": "error", "message": f"运行时构建失败: {error}"})
        return

    # 3. 创建 Agent
    agent = TaskDecomposerAgent(
        llm_client=llm_client,
        search_service=search_service,
        skills=main_skills,
        sub_agents=sub_agents,
    )

    context = build_conversation_context(args, project, project_name)
    clarify_questions = []

    # 4. 需求澄清
    if not args.skip_clarify:
        send_json({"type": "status", "message": "✻ 正在分析需求清晰度..."})
        try:
            questions = agent.clarify(goal)
            if questions:
                clarify_questions = questions
        except Exception as error:
            send_json({"type": "error", "message": f"模型需求澄清失败: {error}"})
            return

    # 5. 任务拆解与合成
    send_json({"type": "status", "message": "✻ 正在分析拆解任务树..."})
    try:
        detail = "本地演示模式" if args.local else "调用大模型"
        send_json({"type": "status", "message": f"✻ 正在合成计划 ({detail})..."})
        result = agent.run(goal, context=context, search_query=args.search_query)
    except Exception as error:
        send_json({"type": "error", "message": f"模型任务拆解失败: {error}"})
        return

    elapsed_seconds = elapsed_since(timer)
    token_count = run_token_count(llm_client, result, goal, context)
    token_note = " (估计)" if llm_client is None or getattr(llm_client, "total_tokens", 0) <= 0 else ""

    # 6. 数据持久化保存
    mode = "local" if agent.llm_client is None else "model"
    try:
        if args.conversation:
            append_conversation(args.runtime_dir, project_name, args.conversation, goal, context, result)
        exported = export_plan(args.runtime_dir, project_name, result, run_id=run_id)
        append_run_log(args.runtime_dir, project_name, run_id, goal, result, elapsed_seconds, mode=mode)
    except Exception as error:
        send_json({"type": "error", "message": f"持久化结果保存失败: {error}"})
        return

    # 7. 成功返回最终 JSON 报文
    # 格式化任务数据，以便 C++ 端渲染 TreeView
    tasks_list = []
    for t in result.plan.tasks:
        tasks_list.append({
            "title": t.title,
            "action": t.action,
            "output": t.output
        })

    plan_data = {
        "goal": result.plan.goal,
        "tasks": tasks_list,
        "next_step": result.plan.next_step
    }

    send_json({
        "type": "success",
        "elapsed": elapsed_seconds,
        "tokens": token_count,
        "token_note": token_note,
        "plan": plan_data,
        "questions": clarify_questions,
        "markdown_path": str(exported.get("markdown", ""))
    })


def main():
    """主事件循环，逐行读取 stdin 接收 C++ 命令"""
    sys.stderr.write("Task Decomposer GUI 后端引擎已拉起。\n")
    sys.stderr.flush()
    
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            
            line = line.strip()
            if not line:
                continue
            
            cmd_data = json.loads(line)
            command = cmd_data.get("command")
            
            if command == "run":
                handle_run_command(cmd_data)
            elif command == "ping":
                send_json({"type": "pong"})
            else:
                send_json({"type": "error", "message": f"未知命令: {command}"})
                
        except json.JSONDecodeError:
            send_json({"type": "error", "message": "无法解析 JSON 报文。"})
        except KeyboardInterrupt:
            break
        except Exception as e:
            tb = traceback.format_exc()
            sys.stderr.write(f"发生未捕获异常:\n{tb}\n")
            sys.stderr.flush()
            send_json({"type": "error", "message": f"内部异常: {str(e)}"})

    sys.stderr.write("Task Decomposer GUI 后端引擎已退出。\n")
    sys.stderr.flush()


if __name__ == "__main__":
    main()

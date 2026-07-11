import sys
import os
import json
import traceback
import uuid
from pathlib import Path
from argparse import Namespace

# 保存真正的标准输出，用于 JSON 管道通信
real_stdout = sys.stdout
# 重定向全局 stdout 到 stderr，彻底防止第三方库或 print 语句污染 JSON 通信流
sys.stdout = sys.stderr

from task_decomposer_app import core_engine

# 当前活跃的 plan 数据（内存缓存），用于 GUI 侧任务编辑
_current_plan = None
_current_runtime_dir = None
_current_username = None
_current_project_name = None


def send_json(data):
    """向 C++ 客户端发送单行 JSON 数据"""
    try:
        real_stdout.write(json.dumps(data) + "\n")
        real_stdout.flush()
    except Exception as e:
        sys.stderr.write(f"发送 JSON 失败: {e}\n")


def _persist_plan():
    """将当前内存中的 plan 数据持久化到输出 JSON 文件。"""
    global _current_plan, _current_runtime_dir, _current_username, _current_project_name
    if not all([_current_plan, _current_runtime_dir, _current_username, _current_project_name]):
        return
    try:
        from task_decomposer_app.runtime import ensure_project_runtime_dirs
        from datetime import datetime, timezone
        output_dir = Path(_current_runtime_dir) / "user" / _current_username / "project" / _current_project_name / "output"
        # 写入 latest.json 作为最新的 plan 快照
        latest_path = output_dir / "latest.json"
        latest_path.write_text(json.dumps(_current_plan, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        sys.stderr.write(f"持久化 plan 失败: {e}\n")
        sys.stderr.flush()


def _send_plan_updated():
    """向 GUI 发送 plan 更新通知。"""
    global _current_plan
    if _current_plan:
        send_json({"type": "plan_updated", "plan": _current_plan})


def handle_run_command(cmd_data):
    """处理任务拆解目标运行"""
    global _current_plan, _current_runtime_dir, _current_username, _current_project_name

    goal = cmd_data.get("goal", "").strip()
    if not goal:
        send_json({"type": "error", "message": "输入的目标不能为空。"})
        return

    # 包装 DecomposerArgs 并自动合并默认参数，彻底统一 CLI 与 GUI 参数映射与缺省逻辑
    args = core_engine.DecomposerArgs(**cmd_data)
    project_name = getattr(args, "project", "default") or "default"

    # 状态回调，泵送实时状态回 C++ 客户端
    def status_callback(stage, message):
        send_json({"type": "status", "stage": stage, "message": message})

    try:
        # 核心拆解运行
        result_dict = core_engine.run_core_decomposition(
            args=args,
            goal=goal,
            status_callback=status_callback,
            prompt_api_key_callback=None  # GUI 模式下不进行 CLI 级交互式 Key 录入
        )

        # 缓存当前 plan 到内存
        _current_plan = result_dict["plan"]
        _current_runtime_dir = getattr(args, "runtime_dir", "runtime")
        _current_username = getattr(args, "user", "demo")
        _current_project_name = project_name

        # 返回成功结果
        send_json({
            "type": "success",
            "elapsed": result_dict["elapsed"],
            "tokens": result_dict["tokens"],
            "token_note": result_dict["token_note"],
            "plan": result_dict["plan"],
            "questions": result_dict["questions"],
            "markdown_path": result_dict["markdown_path"]
        })

    except Exception as error:
        tb = traceback.format_exc()
        sys.stderr.write(f"Decomposition run error:\n{tb}\n")
        sys.stderr.flush()
        send_json({"type": "error", "message": str(error)})

def handle_get_config(cmd_data, args):
    """GUI 后端读取配置并返回数据"""
    try:
        from task_decomposer_app.runtime import load_user_runtime_config, UserRuntimeConfig
        user_name = cmd_data.get("user") or getattr(args, "user", "demo")
        config_dir = getattr(args, "config_dir", "config")
        
        user_config = load_user_runtime_config(config_dir, user_name)
        if user_config is None:
            user_config = UserRuntimeConfig(name=user_name)
            
        payload = {
            "name": user_config.name,
            "provider": user_config.provider,
            "model": user_config.model,
            "base_url": user_config.base_url,
            "password": user_config.password,
            "api_keys": user_config.api_keys,
            "key_pool": user_config.raw_data.get("key_pool", []),
            "search": user_config.raw_data.get("search", {}) if isinstance(user_config.raw_data, dict) else {}
        }
        send_json({"type": "config_data", "config": payload})
    except Exception as e:
        send_json({"type": "error", "message": f"加载配置失败: {e}"})


def handle_save_config(cmd_data, args):
    """GUI 后端保存配置并动态生效"""
    try:
        from task_decomposer_app.runtime import save_user_runtime_config, UserRuntimeConfig
        user_name = cmd_data.get("user") or getattr(args, "user", "demo")
        config_payload = cmd_data.get("config", {})
        config_dir = getattr(args, "config_dir", "config")

        user_config = UserRuntimeConfig(
            name=user_name,
            provider=config_payload.get("provider", ""),
            api_keys=config_payload.get("api_keys", {}),
            model=config_payload.get("model", ""),
            base_url=config_payload.get("base_url", ""),
            password=config_payload.get("password", ""),
            raw_data=config_payload
        )
        save_user_runtime_config(config_dir, user_config)

        # Make the saved config dynamically active in backend environment
        from task_decomposer_app.cli import apply_user_config
        apply_user_config(user_config)

        send_json({"type": "status", "stage": "saved", "message": "配置保存成功！"})
    except Exception as e:
        send_json({"type": "error", "message": f"保存配置失败: {e}"})


def _find_task_index(task_id: str) -> int:
    """在当前 plan 中查找 task_id 对应的索引，未找到返回 -1。"""
    global _current_plan
    if not _current_plan:
        return -1
    for i, t in enumerate(_current_plan.get("tasks", [])):
        if t.get("task_id") == task_id:
            return i
    return -1


def handle_update_task(cmd_data):
    """修改单个任务的字段（title, action, output, status）。"""
    global _current_plan
    if not _current_plan:
        send_json({"type": "error", "message": "没有活跃的 plan，请先执行任务分解。"})
        return

    task_id = cmd_data.get("task_id", "")
    idx = _find_task_index(task_id)
    if idx < 0:
        send_json({"type": "error", "message": f"未找到任务 {task_id}。"})
        return

    task = _current_plan["tasks"][idx]
    for field in ("title", "action", "output", "status"):
        if field in cmd_data:
            task[field] = str(cmd_data[field])

    _persist_plan()
    _send_plan_updated()


def handle_update_task_status(cmd_data):
    """快速更新单个任务的状态。"""
    global _current_plan
    if not _current_plan:
        send_json({"type": "error", "message": "没有活跃的 plan，请先执行任务分解。"})
        return

    task_id = cmd_data.get("task_id", "")
    new_status = cmd_data.get("status", "")
    valid_statuses = ("pending", "in_progress", "done", "blocked")
    if new_status not in valid_statuses:
        send_json({"type": "error", "message": f"无效状态 '{new_status}'，可选: {', '.join(valid_statuses)}"})
        return

    idx = _find_task_index(task_id)
    if idx < 0:
        send_json({"type": "error", "message": f"未找到任务 {task_id}。"})
        return

    _current_plan["tasks"][idx]["status"] = new_status
    _persist_plan()
    _send_plan_updated()


def handle_add_task(cmd_data):
    """新增一个任务。"""
    global _current_plan
    if not _current_plan:
        send_json({"type": "error", "message": "没有活跃的 plan，请先执行任务分解。"})
        return

    task_id = cmd_data.get("task_id") or f"task_{uuid.uuid4().hex[:8]}"
    title = str(cmd_data.get("title", "新任务"))
    action = str(cmd_data.get("action", ""))
    output = str(cmd_data.get("output", ""))
    status = str(cmd_data.get("status", "pending"))
    insert_index = cmd_data.get("insert_index", -1)  # -1 表示追加到末尾

    new_task = {
        "task_id": task_id,
        "title": title,
        "action": action,
        "output": output,
        "status": status,
    }

    tasks = _current_plan["tasks"]
    if 0 <= insert_index <= len(tasks):
        tasks.insert(insert_index, new_task)
    else:
        tasks.append(new_task)

    _persist_plan()
    _send_plan_updated()


def handle_delete_task(cmd_data):
    """删除一个任务及其相关的关系。"""
    global _current_plan
    if not _current_plan:
        send_json({"type": "error", "message": "没有活跃的 plan，请先执行任务分解。"})
        return

    task_id = cmd_data.get("task_id", "")
    idx = _find_task_index(task_id)
    if idx < 0:
        send_json({"type": "error", "message": f"未找到任务 {task_id}。"})
        return

    _current_plan["tasks"].pop(idx)
    # 同时删除涉及该任务的所有关系
    _current_plan["relations"] = [
        r for r in _current_plan.get("relations", [])
        if r.get("source_id") != task_id and r.get("target_id") != task_id
    ]

    _persist_plan()
    _send_plan_updated()


def handle_reorder_tasks(cmd_data):
    """改变任务顺序，接收新的 task_id 有序列表。"""
    global _current_plan
    if not _current_plan:
        send_json({"type": "error", "message": "没有活跃的 plan，请先执行任务分解。"})
        return

    new_order = cmd_data.get("task_ids", [])
    if not isinstance(new_order, list):
        send_json({"type": "error", "message": "task_ids 必须是数组。"})
        return

    task_map = {t["task_id"]: t for t in _current_plan["tasks"]}
    reordered = []
    for tid in new_order:
        if tid in task_map:
            reordered.append(task_map.pop(tid))
    # 把未提及的任务追加到末尾
    reordered.extend(task_map.values())

    _current_plan["tasks"] = reordered
    _persist_plan()
    _send_plan_updated()


def handle_add_relation(cmd_data):
    """添加任务间关系。"""
    global _current_plan
    if not _current_plan:
        send_json({"type": "error", "message": "没有活跃的 plan，请先执行任务分解。"})
        return

    source_id = cmd_data.get("source_id", "")
    target_id = cmd_data.get("target_id", "")
    relation_type = cmd_data.get("relation_type", "sequential")

    valid_types = ("sequential", "parallel", "blocking", "nesting")
    if relation_type not in valid_types:
        send_json({"type": "error", "message": f"无效关系类型 '{relation_type}'，可选: {', '.join(valid_types)}"})
        return

    # 验证两端任务存在
    if _find_task_index(source_id) < 0:
        send_json({"type": "error", "message": f"未找到源任务 {source_id}。"})
        return
    if _find_task_index(target_id) < 0:
        send_json({"type": "error", "message": f"未找到目标任务 {target_id}。"})
        return

    # 去重：相同 source+target 不重复添加
    relations = _current_plan.setdefault("relations", [])
    for r in relations:
        if r.get("source_id") == source_id and r.get("target_id") == target_id:
            r["relation_type"] = relation_type  # 已存在则更新类型
            _persist_plan()
            _send_plan_updated()
            return

    relations.append({
        "source_id": source_id,
        "target_id": target_id,
        "relation_type": relation_type,
    })

    _persist_plan()
    _send_plan_updated()


def handle_remove_relation(cmd_data):
    """删除任务间关系。"""
    global _current_plan
    if not _current_plan:
        send_json({"type": "error", "message": "没有活跃的 plan，请先执行任务分解。"})
        return

    source_id = cmd_data.get("source_id", "")
    target_id = cmd_data.get("target_id", "")
    before = len(_current_plan.get("relations", []))
    _current_plan["relations"] = [
        r for r in _current_plan.get("relations", [])
        if not (r.get("source_id") == source_id and r.get("target_id") == target_id)
    ]
    after = len(_current_plan.get("relations", []))

    if before == after:
        send_json({"type": "error", "message": f"未找到从 {source_id} 到 {target_id} 的关系。"})
        return

    _persist_plan()
    _send_plan_updated()
def main():
    """主事件循环，由标准输入行式读取 C++ 的 JSON 报文命令"""
    sys.stderr.write("Task Decomposer GUI 后端引擎已拉起。\n")
    sys.stderr.flush()

    # 运行与 CLI 100% 对齐的自定义账户、配置修复及密码登录验证
    try:
        from task_decomposer_app.cli import parse_args, auto_initialize_user_scaffold, repair_user_config_if_damaged, login_verify_password
        args = parse_args()
        if args.user and args.user != "demo":
            if not auto_initialize_user_scaffold(args):
                sys.exit(1)
            if not repair_user_config_if_damaged(args):
                sys.exit(1)
            if not login_verify_password(args):
                sys.exit(1)
    except Exception as err:
        sys.stderr.write(f"GUI 后端启动前安全校验异常: {err}\n")
        sys.stderr.flush()
        sys.exit(1)

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
            elif command == "get_config":
                handle_get_config(cmd_data, args)
            elif command == "save_config":
                handle_save_config(cmd_data, args)
            elif command == "update_task":
                handle_update_task(cmd_data)
            elif command == "update_task_status":
                handle_update_task_status(cmd_data)
            elif command == "add_task":
                handle_add_task(cmd_data)
            elif command == "delete_task":
                handle_delete_task(cmd_data)
            elif command == "reorder_tasks":
                handle_reorder_tasks(cmd_data)
            elif command == "add_relation":
                handle_add_relation(cmd_data)
            elif command == "remove_relation":
                handle_remove_relation(cmd_data)
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
            sys.stderr.write(f"GUI Backend Event loop error:\n{tb}\n")
            sys.stderr.flush()
            send_json({"type": "error", "message": f"内部异常: {str(e)}"})

    sys.stderr.write("Task Decomposer GUI 后端引擎已退出。\n")
    sys.stderr.flush()


if __name__ == "__main__":
    main()

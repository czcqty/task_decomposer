import sys
import os
import json
import traceback
from pathlib import Path
from argparse import Namespace

# 保存真正的标准输出，用于 JSON 管道通信
real_stdout = sys.stdout
# 重定向全局 stdout 到 stderr，彻底防止第三方库或 print 语句污染 JSON 通信流
sys.stdout = sys.stderr

from task_decomposer_app import core_engine


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


def main():
    """主事件循环，由标准输入行式读取 C++ 的 JSON 报文命令"""
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
            sys.stderr.write(f"GUI Backend Event loop error:\n{tb}\n")
            sys.stderr.flush()
            send_json({"type": "error", "message": f"内部异常: {str(e)}"})

    sys.stderr.write("Task Decomposer GUI 后端引擎已退出。\n")
    sys.stderr.flush()


if __name__ == "__main__":
    main()

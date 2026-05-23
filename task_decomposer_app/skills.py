from pathlib import Path

from task_decomposer_app.models import Skill


class SkillRegistry:
    def __init__(self, root: str = "config"):
        self.root = Path(root)

    def load_project_agent_skills(
        self,
        project_dir: str,
        agent_name: str,
        names: list[str] | None = None,
    ) -> list[Skill]:
        agent_root = Path(project_dir) / agent_name
        if names:
            return [
                self._load_one(name, agent_root)
                for raw_name in names
                for name in self._split_names(raw_name)
            ]
        return self._load_all_from_root(agent_root)

    def list_project_agent_skills(self, project_dir: str, agent_name: str) -> list[str]:
        return self._list_skill_names(Path(project_dir) / agent_name)

    def _split_names(self, raw_name: str) -> list[str]:
        return [name.strip() for name in raw_name.split(",") if name.strip()]

    def _load_one(self, name: str, root: Path) -> Skill:
        path = root / name / "SKILL.md"

        if not path.exists():
            available = ", ".join(self._list_skill_names(root)) or "无"
            raise RuntimeError(f"未找到 Skill：{name}。当前可用：{available}")

        content = path.read_text(encoding="utf-8").strip()
        skill_name = path.parent.name if path.name == "SKILL.md" else path.stem
        return Skill(name=skill_name, content=content, path=str(path))

    def _load_all_from_root(self, root: Path) -> list[Skill]:
        if not root.exists():
            return []
        skills = []
        for path in sorted(root.iterdir()):
            skill_path = path / "SKILL.md"
            if path.is_dir() and skill_path.exists():
                skills.append(
                    Skill(
                        name=path.name,
                        content=skill_path.read_text(encoding="utf-8").strip(),
                        path=str(skill_path),
                    )
                )
        return skills

    def _list_skill_names(self, root: Path) -> list[str]:
        if not root.exists():
            return []
        return [
            path.name
            for path in sorted(root.iterdir())
            if path.is_dir() and (path / "SKILL.md").exists()
        ]


def format_skills_for_prompt(skills: list[Skill]) -> str:
    if not skills:
        return ""

    blocks = []
    for skill in skills:
        content = skill.content[:6000]
        blocks.append(
            f"## Skill: {skill.name}\n"
            f"来源：{skill.path}\n"
            f"{content}"
        )
    return "\n\n".join(blocks)

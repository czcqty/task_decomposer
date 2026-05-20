from pathlib import Path

from task_decomposer_app.models import Skill


class SkillRegistry:
    def __init__(self, root: str = "skills"):
        self.root = Path(root)
        self.global_root = self.root / "global" if (self.root / "global").exists() else self.root
        self.project_root = self.root / "project"

    def list_skills(self) -> list[str]:
        return self.list_global_skills()

    def list_global_skills(self) -> list[str]:
        return self._list_skill_names(self.global_root)

    def load(self, names: list[str]) -> list[Skill]:
        return self.load_global(names)

    def load_global(self, names: list[str]) -> list[Skill]:
        skills: list[Skill] = []
        for raw_name in names:
            for name in self._split_names(raw_name):
                skills.append(self._load_one(name, self.global_root, scope="global", owner="shared"))
        return skills

    def load_project_agent_skills(
        self,
        project_dir: str,
        agent_name: str,
        names: list[str] | None = None,
    ) -> list[Skill]:
        agent_root = Path(project_dir) / agent_name
        if names:
            return [
                self._load_one(name, agent_root, scope="project", owner=agent_name)
                for raw_name in names
                for name in self._split_names(raw_name)
            ]
        return self._load_all_from_root(agent_root, scope="project", owner=agent_name)

    def list_project_agent_skills(self, project_dir: str, agent_name: str) -> list[str]:
        return self._list_skill_names(Path(project_dir) / agent_name)

    def list_projects(self) -> list[str]:
        if not self.project_root.exists():
            return []
        return [path.name for path in sorted(self.project_root.iterdir()) if path.is_dir()]

    def _split_names(self, raw_name: str) -> list[str]:
        return [name.strip() for name in raw_name.split(",") if name.strip()]

    def _load_one(self, name: str, root: Path, scope: str, owner: str) -> Skill:
        explicit_path = Path(name)
        if explicit_path.exists():
            path = explicit_path / "SKILL.md" if explicit_path.is_dir() else explicit_path
        else:
            path = root / name / "SKILL.md"

        if not path.exists():
            available = ", ".join(self._list_skill_names(root)) or "无"
            raise RuntimeError(f"未找到 Skill：{name}。当前可用：{available}")

        content = path.read_text(encoding="utf-8").strip()
        skill_name = path.parent.name if path.name == "SKILL.md" else path.stem
        return Skill(name=skill_name, content=content, path=str(path), scope=scope, owner=owner)

    def _load_all_from_root(self, root: Path, scope: str, owner: str) -> list[Skill]:
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
                        scope=scope,
                        owner=owner,
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
            f"范围：{skill.scope}\n"
            f"归属：{skill.owner}\n"
            f"来源：{skill.path}\n"
            f"{content}"
        )
    return "\n\n".join(blocks)

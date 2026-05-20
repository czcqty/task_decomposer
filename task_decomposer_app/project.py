from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ProjectSubAgentConfig:
    name: str
    role: str = ""
    skills: list[str] = field(default_factory=list)


@dataclass
class ProjectConfig:
    name: str
    root: Path
    main_skills: list[str] = field(default_factory=list)
    sub_agents: list[ProjectSubAgentConfig] = field(default_factory=list)


def resolve_project_root(project_ref: str | None, skills_root: str = "skills") -> Path | None:
    if not project_ref:
        return None

    ref_path = Path(project_ref)
    if ref_path.exists():
        return ref_path

    project_path = Path(skills_root) / "project" / project_ref
    if project_path.exists():
        return project_path

    raise RuntimeError(f"项目不存在：{project_ref}。请使用 skills/project/<项目名> 结构。")


def project_root_for_create(project_ref: str, skills_root: str = "skills") -> Path:
    ref_path = Path(project_ref)
    if ref_path.parent != Path(".") or ref_path.is_absolute():
        return ref_path
    return Path(skills_root) / "project" / project_ref


def load_project_config(project_ref: str | None, skills_root: str = "skills") -> ProjectConfig | None:
    root = resolve_project_root(project_ref, skills_root)
    if root is None:
        return None

    main_skills = list_agent_skill_names(root / "main")
    sub_agents = [
        ProjectSubAgentConfig(name=path.name, skills=list_agent_skill_names(path))
        for path in sorted(root.iterdir())
        if path.is_dir() and path.name != "main"
    ]
    return ProjectConfig(name=root.name, root=root, main_skills=main_skills, sub_agents=sub_agents)


def list_agent_skill_names(agent_root: Path) -> list[str]:
    if not agent_root.exists():
        return []
    return [
        path.name
        for path in sorted(agent_root.iterdir())
        if path.is_dir() and (path / "SKILL.md").exists()
    ]

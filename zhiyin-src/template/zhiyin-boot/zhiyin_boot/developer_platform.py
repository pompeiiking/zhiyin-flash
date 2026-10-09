"""Assemble project storage and source template provider."""
import io
import json
import zipfile

from zhiyin_business.services.developer import DeveloperPlatform
from zhiyin_infrastructure.postgres.database import get_database
from zhiyin_infrastructure.postgres.developer import PostgresDeveloperRepository


def build_developer_platform(container):
    modules = container.extra.get("module_platform")
    if modules is None:
        return

    def template(module_id, name, owner, kind):
        source_id = "plan_progress_skill" if kind == "tool" else "action_progress"
        definition = modules.definition(source_id)
        manifest = definition.manifest.model_dump()
        manifest.update(id=module_id, name=name, owner=owner, kind=kind, parent_id=None, version="0.1.0",
                        tool=f"{module_id}.read" if kind != "application" else None)
        if kind == "tool":
            manifest.update(card=None, detail=None, conversation=None, actions=[])
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(definition.root.iterdir()):
                if not path.is_file() or path.suffix not in {".py", ".vue", ".json"}:
                    continue
                if kind == "tool" and path.suffix == ".vue":
                    continue
                content = json.dumps(manifest, ensure_ascii=False, indent=2) if path.name == "manifest.json" else path.read_text(encoding="utf-8").replace(source_id, module_id)
                archive.writestr(path.name, content)
        return output.getvalue()

    container.extra["developer_platform"] = DeveloperPlatform(modules,
        PostgresDeveloperRepository(get_database(container.settings.postgres_dsn)), container.users, template)

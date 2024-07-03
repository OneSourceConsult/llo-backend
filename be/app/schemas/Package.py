from pydantic import BaseModel, Field, validator
from uuid import UUID, uuid4


class Package(BaseModel):
    name: str = ""
    version: str = ""
    dependencies: list = []
    status: str = ""

    def __repr__(self):
        return self.json()

class BashScript(Package):
    installScriptPath: str = ""
    uninstallScriptPath: str = ""

    @validator("installScriptPath", always=True)
    def set_installScriptPath(cls, v, values, **kwargs):
        return v or str(values.get("name")) + "/install.sh"

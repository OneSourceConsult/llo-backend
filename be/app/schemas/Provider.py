from uuid import UUID, uuid4
from pydantic import BaseModel, Field


class Provider(BaseModel):
    uuid: UUID = Field(default_factory=uuid4)
    type: str
    name: str
    rootConfigPath: str
    cloudsPath: str
    caCert: str

    class Config:
        schema_extra = {
                "uuid": "4e67bf46-61e0-439b-932b-017f6db1a311",
                "type": "openstack",
                "name": "c01",
                "rootConfigPath": "path/to/Config",
                "cloudsPath": "path/to/clouds",
                "caCert": "path/to/caCert"
        }

    def __repr__(self):
        return self.json()

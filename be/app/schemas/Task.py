from pydantic import BaseModel, Field, validator
from uuid import UUID, uuid4


class Task(BaseModel):
    uuid: UUID = Field(default_factory=uuid4)
    status: str = "accepted"
    href: str = ""

    @validator("href", always=True)
    def set_href(cls, v, values, **kwargs):
        return v or "status/" + str(values.get("uuid"))

    def __repr__(self):
        return self.json()

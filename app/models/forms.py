"""Modelos Pydantic: validan TODO lo que llega de formularios antes de tocar la base de datos."""
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from app.config import today_local

Username = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=50,
                                            pattern=r"^[A-Za-z0-9._-]+$")]
Email = Annotated[str, StringConstraints(strip_whitespace=True, max_length=120,
                                         pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]
Role = Literal["admin", "teacher", "student"]


def _empty_to_none(value):
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


class FormModel(BaseModel):
    model_config = ConfigDict(extra="ignore")  # campos de más se descartan


class LoginForm(FormModel):
    # Sin patrón en username: el login no debe dar pistas sobre el formato
    username: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
    password: str = Field(min_length=1, max_length=128)  # sin strip: los espacios cuentan


class MfaCodeForm(FormModel):
    code: Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\d{6}$")]


class UserCreateForm(FormModel):
    username: Username
    email: Email
    role: Role
    password: str = Field(min_length=12, max_length=128)
    student_id: int | None = Field(default=None, gt=0)
    teacher_id: int | None = Field(default=None, gt=0)

    blank_ids = field_validator("student_id", "teacher_id", mode="before")(_empty_to_none)

    @model_validator(mode="after")
    def check_link(self):
        # Cada cuenta de estudiante/docente se vincula a su persona
        if self.role == "student":
            if self.student_id is None:
                raise ValueError("Una cuenta de estudiante debe vincularse a un estudiante")
            self.teacher_id = None
        elif self.role == "teacher":
            if self.teacher_id is None:
                raise ValueError("Una cuenta de docente debe vincularse a un docente")
            self.student_id = None
        else:
            self.student_id = self.teacher_id = None
        return self


class EnrollmentCreateForm(FormModel):
    student_id: int = Field(gt=0)
    class_group_id: int = Field(gt=0)
    enrollment_date: date


class EnrollmentStatusForm(FormModel):
    status: Literal["active", "withdrawn", "completed"]


class GradeEntry(FormModel):
    score: Decimal = Field(ge=0, le=5, max_digits=3, decimal_places=2)  # escala 0.00 - 5.00
    observation: Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)] | None = None

    @field_validator("score", mode="before")
    @classmethod
    def comma_decimal(cls, value):
        # En Colombia se escribe 4,5: se acepta y se convierte a 4.5
        if isinstance(value, str):
            return value.strip().replace(",", ".")
        return value

    blank_obs = field_validator("observation", mode="before")(_empty_to_none)


class AttendanceEntry(FormModel):
    status: Literal["present", "absent", "late", "excused"]


class ClassDateForm(FormModel):
    class_date: date

    @field_validator("class_date")
    @classmethod
    def not_in_future(cls, value: date) -> date:
        if value > today_local():
            raise ValueError("La fecha no puede estar en el futuro")
        return value


DocType = Literal["ENROLLMENT_FORM", "REPORT_CARD", "ID_DOCUMENT", "MEDICAL_EXCUSE", "OTHER"]


class DocumentUploadForm(FormModel):
    """Campos de texto del formulario de subida (el archivo se valida aparte)."""
    student_id: int = Field(gt=0)
    doc_type: DocType


class AuditFilter(FormModel):
    action: str | None = None
    user_id: int | None = Field(default=None, gt=0)
    page: int = Field(default=1, ge=1, le=10000)

    blank = field_validator("action", "user_id", mode="before")(_empty_to_none)

    @field_validator("page", mode="before")
    @classmethod
    def default_page(cls, value):
        return 1 if value is None or str(value).strip() == "" else value

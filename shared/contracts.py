from datetime import date
from typing import Literal
from urllib.parse import urlsplit
import ipaddress
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict


def web_url(value):
    if not value:
        return value
    try:
        p = urlsplit(value)
        host = p.hostname or ''
        if p.scheme not in ('https', 'http') or '.' not in host or p.username or p.password or p.port not in (None, 80, 443) or host.endswith(('.local', '.localhost', '.internal')):
            raise ValueError('A public web URL is required')
        try:
            ipaddress.ip_address(host)
        except ValueError:
            return value
        raise ValueError('Literal IP addresses are not allowed')
    except Exception:
        raise ValueError('A public web URL is required') from None


def public_web_url(value):
    if not value:
        return None
    try:
        return web_url(value)
    except ValueError:
        return None


class Training(BaseModel):
    model_config = ConfigDict(extra='forbid', protected_namespaces=())
    title: str = Field(min_length=3, max_length=200)
    provider: str = Field(min_length=2, max_length=200)
    description: str = Field(max_length=3000, default='')
    start_date: date | None = None
    end_date: date | None = None
    timezone: str | None = Field(default=None, max_length=80)
    venue: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)
    country: Literal['MY'] = 'MY'
    mode: Literal['in_person', 'online', 'hybrid']
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)
    fee: float | None = Field(default=None, ge=0, le=1000000, allow_inf_nan=False)
    currency: str | None = Field(default=None, pattern=r'^[A-Z]{3}$')
    points: float | None = Field(default=None, ge=0, le=10000, allow_inf_nan=False)
    credit_label: str | None = Field(default=None, max_length=30)
    difficulty: Literal['beginner', 'intermediate', 'advanced'] | None = None
    prerequisites: str | None = Field(default=None, max_length=2000)
    registration_url: str | None = Field(default=None, max_length=2000)
    source_url: str = Field(max_length=2000)
    evidence: dict[str, str] = Field(default_factory=dict)
    source_text: str = Field(max_length=50000, default='')
    model_id: str | None = None
    retrieved_at: str | None = None
    model_weights_url: str | None = None
    model_license_url: str | None = None
    model_publisher: str | None = Field(default=None, max_length=200)
    model_host: str | None = Field(default=None, max_length=200)

    @field_validator('latitude', 'longitude', 'fee', 'points', mode='before')
    @classmethod
    def reject_bool_numbers(cls, value):
        # JSON true/false must not become 1.0/0.0 fee/points/coords (parity with Jev/usage bool reject).
        if isinstance(value, bool):
            raise ValueError('Numeric fields must be numbers, not booleans')
        return value

    @field_validator('source_url', 'registration_url', 'model_weights_url', 'model_license_url')
    @classmethod
    def urls(cls, value):
        return web_url(value)

    @model_validator(mode='after')
    def constraints(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError('Supply both coordinates or neither')
        if self.fee is not None and not self.currency:
            raise ValueError('Known fees need a currency')
        if self.mode != 'online' and not self.city:
            raise ValueError('In-person sessions need a city')
        if self.points is not None and not self.credit_label:
            raise ValueError('Known points need their original credit label')
        if self.end_date and self.start_date and self.end_date < self.start_date:
            raise ValueError('End date cannot be before start date')
        if len(self.evidence) > 30 or any(len(v) > 2000 for v in self.evidence.values()):
            raise ValueError('Evidence is too large')
        return self


def validate_evidence(training):
    required = ['title', 'provider', 'country', 'mode']
    required += [key for key in ('start_date', 'end_date', 'timezone', 'venue', 'city', 'state', 'fee', 'currency', 'points', 'credit_label', 'difficulty', 'prerequisites', 'registration_url') if getattr(training, key) is not None]
    for field in required:
        quote = training.evidence.get(field, '')
        if not quote.strip() or quote not in training.source_text:
            raise ValueError('Missing source evidence for ' + field)
    # Coordinates are not model-inferred; geocoding is not part of this extraction contract.
    if training.latitude is not None or training.longitude is not None:
        raise ValueError('Extracted coordinates require a separate verified geocoding step')
    return training

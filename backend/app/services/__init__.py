"""Infrastructure service abstractions (mail, storage, rate-limit, jobs).

Each service has a Protocol, a memory implementation (tests), a local/dev
implementation (file), and a production implementation (SMTP/S3/Redis/ARQ).
Factories in app.deps wire the configured backend from Settings.
"""

from app.services.jobs import JobRunner, MemoryJobRunner, get_job_runner, job  # noqa: F401
from app.services.mail import Mailer, Message, get_mailer  # noqa: F401
from app.services.otp_store import OtpRecord, OtpStore, get_otp_store  # noqa: F401
from app.services.ratelimit import RateLimiter, RateLimitResult, get_rate_limiter  # noqa: F401
from app.services.storage import Storage, get_storage  # noqa: F401

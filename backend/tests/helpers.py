"""Shared async test helpers (imported by test modules)."""

import re

CODE_RE = re.compile(r"code is: (\d{6})")


def last_code(memory_services, email: str) -> str:
    message = memory_services["mailer"].last_to(email)
    assert message is not None, f"no mail for {email}"
    return CODE_RE.search(message.text_body).group(1)


async def login_as(client, memory_services, email: str) -> str:
    """Register/verify via OTP; returns the session cookie value."""
    response = await client.post("/v1/auth/request-code", json={"email": email})
    assert response.status_code == 202, response.text
    code = last_code(memory_services, email)
    login = await client.post("/v1/auth/verify", json={"email": email, "code": code})
    assert login.status_code == 200, login.text
    return login.cookies["ml_session"]


async def create_space(client, cookie: str, theme_id: str, **overrides) -> dict:
    body = {"title": "Test Space", "occasion": "birthday", "theme_id": theme_id,
            "visibility": "link"}
    body.update(overrides)
    response = await client.post("/v1/spaces", json=body, cookies={"ml_session": cookie})
    assert response.status_code == 201, response.text
    return response.json()["data"]

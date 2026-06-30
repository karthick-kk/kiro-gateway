# -*- coding: utf-8 -*-

# Kiro Gateway
# https://github.com/jwadow/kiro-gateway
# Copyright (C) 2025 Jwadow
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
Kiro usage/credits lookup.

Calls the control-plane endpoint that powers `kiro-cli`'s `/usage` slash command:

    GET https://management.{region}.kiro.dev/Get-Usage-Limits
        ?profileArn=...&origin=AI_EDITOR&resourceType=CREDIT
    Authorization: Bearer <access_token>

Key detail: the host region is taken from the **profileArn** (e.g. eu-central-1),
which may differ from the token/SSO region. Auth is a plain Bearer token (no
SigV4 signing), so we reuse the gateway's existing KiroAuthManager - this module
is a pure reader of auth state and never performs its own token refresh logic
beyond the standard 403 -> force_refresh retry the rest of the gateway uses.
"""

from datetime import datetime, timezone
from typing import Optional

import httpx
from loguru import logger

from kiro.config import KIRO_MANAGEMENT_HOST_TEMPLATE
from kiro.auth import KiroAuthManager


def _region_from_arn(profile_arn: str) -> Optional[str]:
    """
    Extract the AWS region from a CodeWhisperer profile ARN.

    arn:aws:codewhisperer:eu-central-1:177603749556:profile/XXXX
                          ^^^^^^^^^^^^ region (4th field)
    """
    if not profile_arn:
        return None
    parts = profile_arn.split(":")
    if len(parts) >= 4 and parts[3]:
        return parts[3]
    return None


def _parse_usage(data: dict) -> dict:
    """
    Map the raw Get-Usage-Limits response into a small, stable shape.

    Picks the CREDIT breakdown entry (falls back to the first entry) and
    prefers the *WithPrecision fields for accuracy.
    """
    breakdowns = data.get("usageBreakdownList") or []
    credit = None
    for entry in breakdowns:
        if entry.get("resourceType") == "CREDIT":
            credit = entry
            break
    if credit is None and breakdowns:
        credit = breakdowns[0]

    used = 0.0
    total = 0.0
    if credit:
        used = credit.get("currentUsageWithPrecision")
        if used is None:
            used = credit.get("currentUsage") or 0
        total = credit.get("usageLimitWithPrecision")
        if total is None:
            total = credit.get("usageLimit") or 0

    used = float(used or 0)
    total = float(total or 0)
    percentage = (used / total * 100.0) if total else 0.0

    subscription = data.get("subscriptionInfo") or {}
    plan_name = subscription.get("subscriptionTitle")

    overage_cfg = data.get("overageConfiguration") or {}
    overages = overage_cfg.get("overageStatus")

    # Reset date: epoch seconds, may live at top level or inside the breakdown
    reset_epoch = data.get("nextDateReset")
    if reset_epoch is None and credit:
        reset_epoch = credit.get("nextDateReset")
    reset_date = None
    if reset_epoch:
        try:
            reset_date = datetime.fromtimestamp(
                float(reset_epoch), tz=timezone.utc
            ).strftime("%Y-%m-%d")
        except (ValueError, OverflowError, OSError):
            reset_date = None

    return {
        "used": round(used, 2),
        "total": round(total, 2),
        "percentage": round(percentage, 2),
        "reset_date": reset_date,
        "plan_name": plan_name,
        "overages": overages,
    }


async def fetch_usage(
    auth_manager: KiroAuthManager,
    shared_client: httpx.AsyncClient,
) -> dict:
    """
    Fetch current usage/credits for the given account.

    Reuses auth_manager.get_access_token() (which already handles reload + refresh)
    and force_refresh() on a 401/403, mirroring KiroHttpClient's behaviour. Uses a
    minimal Bearer-only header set - the chat-specific x-amz-target headers are NOT
    valid for this REST endpoint.

    Returns the parsed usage dict (see _parse_usage).

    Raises:
        ValueError: if the account has no profileArn (cannot resolve host region).
        httpx.HTTPStatusError: on non-200 after a refresh retry.
    """
    profile_arn = auth_manager.profile_arn
    if not profile_arn:
        raise ValueError("Account has no profileArn; cannot resolve usage endpoint region")

    region = _region_from_arn(profile_arn)
    if not region:
        raise ValueError(f"Could not extract region from profileArn: {profile_arn}")

    url = f"{KIRO_MANAGEMENT_HOST_TEMPLATE.format(region=region)}/Get-Usage-Limits"
    params = {
        "profileArn": profile_arn,
        "origin": "AI_EDITOR",
        "resourceType": "CREDIT",
    }

    last_response: Optional[httpx.Response] = None
    for attempt in range(2):
        token = await auth_manager.get_access_token()
        headers = {"Authorization": f"Bearer {token}"}

        logger.debug(f"Fetching usage: region={region}, attempt={attempt + 1}")
        response = await shared_client.get(
            url, params=params, headers=headers, timeout=20.0
        )
        last_response = response

        if response.status_code == 200:
            return _parse_usage(response.json())

        # Token problem - refresh once and retry
        if response.status_code in (401, 403) and attempt == 0:
            logger.warning(
                f"Usage request returned {response.status_code}, refreshing token and retrying"
            )
            await auth_manager.force_refresh()
            continue

        # Any other status, or already retried - stop
        break

    if last_response is not None:
        logger.error(
            f"Usage request failed: status={last_response.status_code}, "
            f"body={last_response.text[:300]}"
        )
        last_response.raise_for_status()

    raise RuntimeError("Usage request failed with no response")

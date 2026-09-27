#!/usr/bin/env python3
"""Small, manifest-owned Azure workshop provisioner. Dry-run is the default.

Never emits Azure CLI output (which may contain keys). No SDK dependencies.
Cloud changes require --apply; shared Foundry/APIM parent resources are read-only.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

from security import API_ID, API_PATH, ATTENDEES, EMBEDDING, MODEL, OPERATIONS, render_policy

ARM = "https://management.azure.com"
APIM_VERSION = "2024-05-01"
AI_VERSION = "2025-06-01"
SEARCH_VERSION = "2025-05-01"
RG_VERSION = "2022-09-01"
ROLE_VERSION = "2022-04-01"
SEARCH_ROLES = ("7ca78c08-252a-4471-8644-bb5ff32d4ba0", "8ebe5a00-799e-43f5-93ac-243d3dce84a7")
OPENAI_ROLE = "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd"
ROOT = Path(__file__).resolve().parents[1]
OWNER = "agent-rag-workshop"


class SafeError(Exception):
    """Only messages known not to contain credentials may reach stdout/stderr."""


def private_write(path, text):
    path = Path(path)
    if path.is_symlink() or path.parent.is_symlink():
        raise SafeError("Refusing a symlink in a private output path")
    # macOS /var and /tmp are OS-provided aliases; canonicalize ancestors.
    path = path.parent.resolve() / path.name
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".workshop-")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def write_attendee(directory, name, gateway, key):
    if name not in ATTENDEES or not re.fullmatch(r"[A-Za-z0-9_-]+", key):
        raise SafeError("Invalid attendee or subscription secret format")
    if not re.fullmatch(r"https://[a-z0-9-]+\.azure-api\.net", gateway):
        raise SafeError("Invalid gateway origin")
    values = {
        "OPENAI_BASE_URL": f"{gateway}/{API_PATH}/openai/v1",
        "OPENAI_MODEL": MODEL,
        "AZURE_OPENAI_DEPLOYMENT": MODEL,
        "EMBEDDING_MODEL": EMBEDDING,
        "EMBEDDING_DIMENSIONS": "1536",
        "AZURE_SEARCH_ENDPOINT": f"{gateway}/{API_PATH}/search",
        "AZURE_SEARCH_INDEX": name,
        "WORKSHOP_API_KEY": key,
    }
    private_write(Path(directory) / f"{name}.env", "".join(f"{k}={v}\n" for k, v in values.items()))


class Azure:
    def __init__(self, subscription, apply=False):
        self.subscription = subscription
        self.apply = apply

    def request(
        self, method, resource_id, version, body=None, missing_ok=False, query="", headers=None
    ):
        if method not in ("GET", "HEAD") and not self.apply:
            raise SafeError("Cloud writes and listSecrets are disabled in dry-run")
        url = resource_id if resource_id.startswith(ARM + "/") else ARM + resource_id
        if not url.startswith(ARM + "/subscriptions/" + self.subscription + "/"):
            raise SafeError("Refusing a request outside the selected subscription")
        if "?" not in url:
            url += "?api-version=" + version + query
        command = [
            "az",
            "rest",
            "--method",
            method,
            "--url",
            url,
            "--subscription",
            self.subscription,
            "--only-show-errors",
            "--output",
            "json",
        ]
        with tempfile.TemporaryDirectory(prefix="workshop-az-") as tmp:
            if body is not None:
                payload = Path(tmp) / "body.json"
                private_write(payload, json.dumps(body))
                command += ["--body", "@" + str(payload)]
            request_headers = {"Content-Type": "application/json", **(headers or {})}
            if method == "DELETE" and "/Microsoft.ApiManagement/" in resource_id:
                request_headers["If-Match"] = "*"
            command += ["--headers"] + [k + "=" + v for k, v in request_headers.items()]
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=180,
                    check=False,
                    env=dict(os.environ, AZURE_CORE_COLLECT_TELEMETRY="false"),
                )
            except (OSError, subprocess.TimeoutExpired):
                raise SafeError(
                    "Azure CLI unavailable or timed out; no response content shown"
                ) from None
        if result.returncode:
            # Inspect only to classify 404; never echo raw stderr/stdout or a command containing secrets.
            if missing_ok and any(
                token in result.stderr
                for token in ("ResourceNotFound", "ResourceGroupNotFound", "NotFound", "(404)")
            ):
                return None
            codes = re.findall(r"\(([A-Za-z][A-Za-z0-9]+)\)", result.stderr)
            safe_code = (
                codes[0]
                if codes
                and codes[0]
                in {
                    "AuthorizationFailed",
                    "Forbidden",
                    "Conflict",
                    "BadRequest",
                    "InvalidRequestContent",
                    "ValidationError",
                    "ResourceNotFound",
                    "RequestDisallowedByPolicy",
                    "InsufficientQuota",
                    "InvalidResourceProperties",
                }
                else "redacted"
            )
            raise SafeError(
                f"Azure {method} failed ({safe_code}); response suppressed. Inspect Azure Activity Log securely."
            )
        try:
            output = result.stdout.lstrip("\ufeff").strip()
            if resource_id.split("?")[0].endswith("/policies/policy") and output.startswith("<"):
                # rawxml may contain unescaped C# generics; verify later with format=xml.
                return {"properties": {"format": "rawxml", "value": output}}
            return json.loads(output) if output else {}
        except (json.JSONDecodeError, ET.ParseError):
            raise SafeError("Azure CLI returned invalid JSON/XML; response suppressed") from None

    def get(self, rid, version, missing_ok=False, query=""):
        return self.request("GET", rid, version, missing_ok=missing_ok, query=query)

    def collection(self, rid, version, query=""):
        page = self.get(rid, version, query=query)
        values = list(page.get("value", []))
        while page.get("nextLink"):
            page = self.get(page["nextLink"], version)
            values.extend(page.get("value", []))
        return values

    def wait(self, rid, version, deleted=False, timeout=900):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = self.get(rid, version, missing_ok=True)
            if deleted and value is None:
                return None
            if value is not None and not deleted:
                state = (
                    value.get("properties", {}).get("provisioningState") or "Succeeded"
                ).lower()
                if state in ("failed", "canceled"):
                    raise SafeError(
                        "Resource provisioning failed; inspect Azure Activity Log securely"
                    )
                if state == "succeeded":
                    return value
            time.sleep(5)
        raise SafeError(
            "Timed out waiting for verified Azure resource state; retain the manifest and rerun"
        )


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    for flag in ["subscription", "foundry-rg", "foundry-name", "apim-rg", "apim-name"]:
        p.add_argument("--" + flag, required=True)
    p.add_argument("--new-rg", default="rg-agent-rag-workshop")
    p.add_argument(
        "--search-name", help="Default: srch-agent-rag-<deterministic 10-character suffix>"
    )
    p.add_argument("--location", default="koreacentral")
    p.add_argument(
        "--embedding-sku",
        choices=["Standard", "GlobalStandard", "DataZoneStandard"],
        default="Standard",
    )
    p.add_argument("--manifest", type=Path, default=ROOT / ".local/provision-manifest.json")
    p.add_argument("--attendee-dir", type=Path, default=ROOT / ".local/attendees")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    return p


def resource_ids(args):
    if not re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", args.subscription):
        raise SafeError("Subscription must be a UUID")
    for name in [
        args.foundry_rg,
        args.foundry_name,
        args.apim_rg,
        args.apim_name,
        args.new_rg,
        args.location,
    ]:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,89}", name):
            raise SafeError("Invalid resource name")
    if args.new_rg.lower() in {args.foundry_rg.lower(), args.apim_rg.lower()}:
        raise SafeError("Workshop RG must differ from both shared resource groups")
    suffix = hashlib.sha256(
        f"{args.subscription.lower()}:{args.new_rg.lower()}".encode()
    ).hexdigest()[:10]
    search = args.search_name or "srch-agent-rag-" + suffix
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,58}[a-z0-9]", search):
        raise SafeError("Invalid Search service name")
    sub = "/subscriptions/" + args.subscription
    foundry = f"{sub}/resourceGroups/{args.foundry_rg}/providers/Microsoft.CognitiveServices/accounts/{args.foundry_name}"
    apim = f"{sub}/resourceGroups/{args.apim_rg}/providers/Microsoft.ApiManagement/service/{args.apim_name}"
    rg = f"{sub}/resourceGroups/{args.new_rg}"
    return {
        "rg": rg,
        "search": f"{rg}/providers/Microsoft.Search/searchServices/{search}",
        "foundry": foundry,
        "apim": apim,
        "api": apim + "/apis/" + API_ID,
        "embedding": foundry + "/deployments/" + EMBEDDING,
    }


def deletable_ids(ids):
    return {ids["rg"], ids["search"], ids["api"], ids["embedding"]} | {
        ids["apim"] + "/subscriptions/" + API_ID + "-" + name for name in ATTENDEES
    }


def embedding_version(models, sku):
    candidates = []
    supported = set()
    for record in models:
        model = record.get("model", record)
        if model.get("name") != EMBEDDING:
            continue
        skus = {s["name"] for s in record.get("skus", model.get("skus", []))}
        supported.update(skus)
        if sku in skus:
            candidates.append(model)
    defaults = [m for m in candidates if m.get("isDefaultVersion")]
    if len(defaults) == 1:
        return defaults[0]["version"]
    if len(candidates) == 1:
        return candidates[0]["version"]
    raise SafeError(
        "Embedding SKU/version unavailable or ambiguous: requested "
        + sku
        + "; metadata supports "
        + ", ".join(sorted(supported))
        + ". No silent fallback; explicitly approve another --embedding-sku if appropriate."
    )


def role_id(search_id, principal, role):
    name = str(
        uuid.uuid5(uuid.NAMESPACE_URL, search_id.lower() + "/" + principal.lower() + "/" + role)
    )
    return search_id + "/providers/Microsoft.Authorization/roleAssignments/" + name


def assert_subset(expected, actual, label="resource"):
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            raise SafeError("Readback mismatch: " + label)
        for key, value in expected.items():
            # apiType is a create-only APIM selector. REST GET exposes type,
            # and omits the legacy default HTTP type entirely.
            if key == "apiType":
                assert_subset(
                    value, actual.get("apiType") or actual.get("type") or "http", label + ".type"
                )
                continue
            if key not in actual:
                raise SafeError("Missing readback field: " + label + "." + key)
            assert_subset(value, actual[key], label + "." + key)
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(expected) != len(actual):
            raise SafeError("Readback mismatch: " + label)
        for wanted, observed in zip(expected, actual):
            assert_subset(wanted, observed, label + "[]")
    elif label.endswith(".location") and isinstance(expected, str) and isinstance(actual, str):
        # Search ARM returns the region display name; other identifiers stay exact.
        if expected.replace(" ", "").casefold() != actual.replace(" ", "").casefold():
            raise SafeError("Readback mismatch: " + label)
    elif expected != actual:
        raise SafeError("Readback mismatch: " + label)


def diagnostics_safe(azure, rid):
    for diagnostic in azure.collection(rid + "/diagnostics", APIM_VERSION):
        p = diagnostic.get("properties", {})
        for side in ("frontend", "backend"):
            for direction in ("request", "response"):
                setting = p.get(side, {}).get(direction, {})
                if setting.get("body", {}).get("bytes", 0) or setting.get("headers"):
                    raise SafeError(
                        "Existing APIM diagnostics capture bodies/headers; owner must disable this before apply"
                    )
        if p.get("logClientIp") or p.get("verbosity") == "verbose" or p.get("largeLanguageModel"):
            raise SafeError("Unsafe existing APIM diagnostics; owner review required")


class Manifest:
    def __init__(self, args, ids):
        self.path = args.manifest
        config = {
            k: v
            for k, v in vars(args).items()
            if k not in {"apply", "dry_run", "manifest", "attendee_dir"}
        }
        self.data = (
            json.loads(self.path.read_text())
            if self.path.exists()
            else {"schema": 1, "owner": OWNER, "config": config, "ids": ids, "resources": []}
        )
        if (
            self.data.get("owner") != OWNER
            or self.data.get("ids") != ids
            or self.data.get("config") != config
        ):
            raise SafeError(
                "Manifest belongs to a different deployment/configuration; do not reuse or overwrite it"
            )

    def save(self):
        private_write(self.path, json.dumps(self.data, indent=2) + "\n")

    def owns(self, rid):
        return any(r["id"].lower() == rid.lower() for r in self.data["resources"])

    def put(self, azure, rid, version, payload):
        existing = azure.get(rid, version, missing_ok=True)
        if existing is not None and not self.owns(rid):
            raise SafeError("An unowned target already exists; refusing to adopt or modify it")
        if existing is not None:
            try:
                assert_subset(payload, existing)
            except SafeError:
                pass  # A manifest-owned resource needs a deliberate update.
            else:
                readback = azure.wait(rid, version)
                assert_subset(payload, readback)
                for item in self.data["resources"]:
                    if item["id"] == rid:
                        item["status"] = "verified"
                self.save()
                return readback
        if not self.owns(rid):
            self.data["resources"].append({"id": rid, "version": version, "status": "pending"})
            self.save()  # Journal BEFORE a write so interruption does not orphan a resource.
        azure.request(
            "PUT",
            rid,
            version,
            payload,
            headers={"If-Match": "*"} if existing is not None else None,
        )
        readback = azure.wait(rid, version)
        assert_subset(payload, readback)
        for item in self.data["resources"]:
            if item["id"] == rid:
                item["status"] = "verified"
        self.save()
        return readback


def provision(args):
    ids = resource_ids(args)
    azure = Azure(args.subscription, args.apply)
    manifest = Manifest(args, ids)
    foundry = azure.get(ids["foundry"], AI_VERSION)
    apim = azure.get(ids["apim"], APIM_VERSION)
    principal = apim.get("identity", {}).get("principalId")
    if not principal or "SystemAssigned" not in apim.get("identity", {}).get("type", ""):
        raise SafeError("Existing APIM must already have a system-assigned managed identity")
    assignments = azure.collection(
        ids["foundry"] + "/providers/Microsoft.Authorization/roleAssignments", ROLE_VERSION
    )
    if not any(
        a["properties"].get("principalId", "").lower() == principal.lower()
        and a["properties"].get("scope", "").lower() == ids["foundry"].lower()
        and a["properties"].get("roleDefinitionId", "").lower().endswith("/" + OPENAI_ROLE)
        for a in assignments
    ):
        raise SafeError(
            "APIM MI needs pre-existing Cognitive Services OpenAI User at exact Foundry scope; no broad assignment will be created"
        )
    version = embedding_version(
        azure.collection(ids["foundry"] + "/models", AI_VERSION), args.embedding_sku
    )
    response_deployment = azure.get(ids["foundry"] + "/deployments/" + MODEL, AI_VERSION)
    if response_deployment.get("properties", {}).get("provisioningState") != "Succeeded":
        raise SafeError("Required existing responses deployment is not ready")
    endpoints = foundry["properties"].get("endpoints", {})
    endpoint = endpoints.get("OpenAI Language Model Instance API", "").rstrip("/")
    policy = render_policy(
        endpoint, "https://" + ids["search"].split("/")[-1] + ".search.windows.net"
    )
    diagnostics_safe(azure, ids["apim"])
    # Fail closed on name collisions, including all shared-account child resources.
    for key, api_version in [
        ("rg", RG_VERSION),
        ("search", SEARCH_VERSION),
        ("api", APIM_VERSION),
        ("embedding", AI_VERSION),
    ]:
        existing = azure.get(ids[key], api_version, missing_ok=True)
        if existing is not None and not manifest.owns(ids[key]):
            raise SafeError(
                "Target " + key + " already exists without this manifest; refusing adoption"
            )
    if azure.get(ids["api"], APIM_VERSION, missing_ok=True):
        diagnostics_safe(azure, ids["api"])
    for name in ATTENDEES:
        rid = ids["apim"] + "/subscriptions/" + API_ID + "-" + name
        if azure.get(rid, APIM_VERSION, missing_ok=True) is not None and not manifest.owns(rid):
            raise SafeError("An attendee subscription ID already exists without manifest ownership")
    print(
        json.dumps(
            {
                "mode": "apply" if args.apply else "dry-run",
                "resource_group": args.new_rg,
                "search_name": ids["search"].split("/")[-1],
                "search_sku": "basic 1 partition / 1 replica",
                "embedding_model_version": version,
                "embedding_sku": args.embedding_sku,
                "embedding_capacity": 30,
                "api_path": API_PATH,
                "attendees": len(ATTENDEES),
            },
            indent=2,
        )
    )
    if not args.apply:
        print(
            "Read-only preflight passed. No cloud writes, key retrieval, or attendee files created."
        )
        return
    # No secrets may be written inside a public tracked path.
    for private_path in (args.manifest, args.attendee_dir / "student01.env"):
        check = subprocess.run(
            ["git", "check-ignore", "--quiet", str(private_path)],
            cwd=ROOT,
            capture_output=True,
            check=False,
        )
        if check.returncode:
            raise SafeError(
                "Private output is not gitignored; add .local/ to repository .gitignore first"
            )
    manifest.data["principal_id"] = principal
    manifest.save()
    manifest.put(
        azure, ids["rg"], RG_VERSION, {"location": args.location, "tags": {"workshop": OWNER}}
    )
    manifest.put(
        azure,
        ids["search"],
        SEARCH_VERSION,
        {
            "location": args.location,
            "sku": {"name": "basic"},
            "tags": {"workshop": OWNER},
            "properties": {
                "replicaCount": 1,
                "partitionCount": 1,
                "hostingMode": "Default",
                "publicNetworkAccess": "Enabled",
                "disableLocalAuth": True,
            },
        },
    )
    for role in SEARCH_ROLES:
        rid = role_id(ids["search"], principal, role)
        manifest.put(
            azure,
            rid,
            ROLE_VERSION,
            {
                "properties": {
                    "principalId": principal,
                    "principalType": "ServicePrincipal",
                    "roleDefinitionId": "/subscriptions/"
                    + args.subscription
                    + "/providers/Microsoft.Authorization/roleDefinitions/"
                    + role,
                }
            },
        )
        assert_subset({"properties": {"scope": ids["search"]}}, azure.get(rid, ROLE_VERSION))
    manifest.put(
        azure,
        ids["embedding"],
        AI_VERSION,
        {
            "sku": {"name": args.embedding_sku, "capacity": 30},
            "properties": {
                "model": {"format": "OpenAI", "name": EMBEDDING, "version": version},
                "versionUpgradeOption": "NoAutoUpgrade",
            },
        },
    )
    manifest.put(
        azure,
        ids["api"],
        APIM_VERSION,
        {
            "properties": {
                "displayName": API_ID,
                "description": "Dedicated manifest-owned workshop API. No shared API changes.",
                "path": API_PATH,
                "protocols": ["https"],
                "subscriptionRequired": True,
                "subscriptionKeyParameterNames": {
                    "header": "Ocp-Apim-Subscription-Key",
                    "query": "subscription-key",
                },
                "apiType": "http",
            }
        },
    )
    for op, method, path in OPERATIONS:
        payload = {
            "properties": {
                "displayName": op,
                "method": method,
                "urlTemplate": path,
                "templateParameters": (
                    [{"name": "indexName", "required": True, "type": "string"}]
                    if "{indexName}" in path
                    else []
                ),
                "responses": [],
            }
        }
        manifest.put(azure, ids["api"] + "/operations/" + op, APIM_VERSION, payload)
    policy_id = ids["api"] + "/policies/policy"
    # APIM returns policy format as rawxml or xml and normalizes its serialization.
    if not manifest.owns(policy_id):
        manifest.data["resources"].append(
            {"id": policy_id, "version": APIM_VERSION, "status": "pending"}
        )
        manifest.save()
    azure.request(
        "PUT",
        policy_id,
        APIM_VERSION,
        {"properties": {"format": "xml", "value": policy}},
        headers={"If-Match": "*"},
    )
    actual_policy = azure.get(policy_id, APIM_VERSION, query="&format=xml")["properties"]["value"]

    def tree(node):
        return (
            node.tag,
            sorted(node.attrib.items()),
            (node.text or "").strip(),
            [tree(c) for c in node],
        )

    if tree(ET.fromstring(policy)) != tree(ET.fromstring(actual_policy)):
        raise SafeError(
            "Policy readback differs from the generated policy; subscriptions have not been issued"
        )
    actual_ops = azure.collection(ids["api"] + "/operations", APIM_VERSION)
    if {o["name"] for o in actual_ops} != {o[0] for o in OPERATIONS}:
        raise SafeError("Unexpected API operations present; refusing to issue keys")
    diagnostics_safe(azure, ids["api"])
    for name in ATTENDEES:
        rid = ids["apim"] + "/subscriptions/" + API_ID + "-" + name
        expected = {
            "properties": {
                "scope": ids["api"],
                "displayName": name,
                "state": "active",
                "allowTracing": False,
            }
        }
        existing = azure.get(rid, APIM_VERSION, missing_ok=True)
        if existing is None:
            # Omit primaryKey/secondaryKey: APIM generates random secrets. Never rotate on rerun.
            manifest.put(azure, rid, APIM_VERSION, expected)
        else:
            assert_subset(expected, existing)
        secrets = azure.request("POST", rid + "/listSecrets", APIM_VERSION)
        write_attendee(
            args.attendee_dir,
            name,
            apim["properties"]["gatewayUrl"].rstrip("/"),
            secrets["primaryKey"],
        )
        del secrets
    generated = {p.stem for p in args.attendee_dir.glob("*.env")}
    if generated != set(ATTENDEES):
        raise SafeError("Attendee directory has an unexpected file count/name set")
    for item in manifest.data["resources"]:
        if azure.get(item["id"], item["version"], missing_ok=True) is None:
            raise SafeError("Final resource verification failed")
        item["status"] = "verified"
    manifest.data["verified"] = True
    manifest.save()
    print(
        "Verified cloud resources and 11 private attendee files. Run live positive/negative gateway tests before distribution."
    )
    print("Manifest: " + str(args.manifest))
    print("Private attendee directory: " + str(args.attendee_dir))


def main():
    try:
        provision(parser().parse_args())
    except SafeError as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 1
    except Exception:  # noqa: BLE001 — redact unexpected SDK/CLI response secrets
        print(
            "ERROR: unexpected failure; response details suppressed to protect credentials. Retain manifest for recovery.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

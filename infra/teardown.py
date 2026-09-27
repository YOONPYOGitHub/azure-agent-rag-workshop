#!/usr/bin/env python3
"""Delete only manifest-owned workshop resources. Dry-run unless --apply.

Shared Foundry and APIM parents are never deletion targets. --confirm must equal
exactly the dedicated resource group name, and is required even for dry-run.
"""

import argparse
import json
import sys
from pathlib import Path

from provision import (
    AI_VERSION,
    APIM_VERSION,
    OWNER,
    RG_VERSION,
    ROLE_VERSION,
    ROOT,
    SEARCH_ROLES,
    SEARCH_VERSION,
    Azure,
    SafeError,
    private_write,
    resource_ids,
    role_id,
)
from security import API_ID, ATTENDEES, OPERATIONS


def cleanup_plan(manifest):
    if manifest.get("schema") != 1 or manifest.get("owner") != OWNER:
        raise SafeError("Unrecognized manifest")
    ids = resource_ids(argparse.Namespace(**manifest["config"]))
    if manifest.get("ids") != ids:
        raise SafeError("Manifest resource IDs differ from validated configuration")
    allowed = {
        ids["rg"]: RG_VERSION,
        ids["search"]: SEARCH_VERSION,
        ids["api"]: APIM_VERSION,
        ids["embedding"]: AI_VERSION,
        ids["api"] + "/policies/policy": APIM_VERSION,
    }
    allowed.update({ids["api"] + "/operations/" + op: APIM_VERSION for op, _, _ in OPERATIONS})
    allowed.update(
        {ids["apim"] + "/subscriptions/" + API_ID + "-" + name: APIM_VERSION for name in ATTENDEES}
    )
    principal = manifest.get("principal_id")
    if principal:
        allowed.update(
            {role_id(ids["search"], principal, role): ROLE_VERSION for role in SEARCH_ROLES}
        )
    owned = {}
    for item in manifest["resources"]:
        rid, version = item["id"], item["version"]
        if allowed.get(rid) != version or rid in owned:
            raise SafeError("Unsafe, duplicate, or unrecognized resource in manifest")
        owned[rid] = version
    # Parent API deletion covers its policy/operations. RG deletion covers Search.
    targets = [
        (rid, version)
        for rid, version in owned.items()
        if not (rid.startswith(ids["api"] + "/") and ids["api"] in owned)
        and not (rid == ids["search"] and ids["rg"] in owned)
    ]

    def order(item):
        rid = item[0]
        if "/subscriptions/" + API_ID + "-" in rid:
            return 0
        if rid == ids["api"] or rid.startswith(ids["api"] + "/"):
            return 1
        if rid == ids["embedding"]:
            return 2
        if "/roleAssignments/" in rid:
            return 3
        return 5 if rid == ids["rg"] else 4

    return sorted(targets, key=order)


def teardown(args):
    manifest = json.loads(args.manifest.read_text())
    targets = cleanup_plan(manifest)
    config, ids = manifest["config"], manifest["ids"]
    if args.confirm != config["new_rg"]:
        raise SafeError("--confirm must exactly match the manifest dedicated resource group name")
    azure = Azure(config["subscription"], args.apply)
    rg = azure.get(ids["rg"], RG_VERSION, missing_ok=True)
    if rg is not None:
        if rg.get("tags", {}).get("workshop") != OWNER:
            raise SafeError("Dedicated RG ownership tag is missing; refusing deletion")
        contents = azure.collection(ids["rg"] + "/resources", "2021-04-01")
        if any(r["id"].lower() != ids["search"].lower() for r in contents):
            raise SafeError(
                "Dedicated RG contains an unrecognized resource; refusing group deletion"
            )
    print(
        json.dumps(
            {
                "mode": "apply" if args.apply else "dry-run",
                "delete_only": [rid for rid, _ in targets],
            },
            indent=2,
        )
    )
    if not args.apply:
        print("No cloud changes. Re-run with --apply and the same --confirm to delete.")
        return
    # Re-check exact targets before deletion; missing targets are idempotently skipped.
    for rid, version in targets:
        if azure.get(rid, version, missing_ok=True) is not None:
            azure.request(
                "DELETE", rid, version, query="&deleteRevisions=true" if rid == ids["api"] else ""
            )
            azure.wait(rid, version, deleted=True, timeout=1800)
        for item in manifest["resources"]:
            if (
                item["id"] == rid
                or (rid == ids["api"] and item["id"].startswith(rid + "/"))
                or (rid == ids["rg"] and item["id"].startswith(rid + "/"))
            ):
                item["status"] = "deleted"
        private_write(args.manifest, json.dumps(manifest, indent=2) + "\n")
    # Verify every original resource, including children, is gone.
    for item in manifest["resources"]:
        if azure.get(item["id"], item["version"], missing_ok=True) is not None:
            raise SafeError("A manifest resource remains; cleanup is incomplete")
    if (
        azure.get(ids["foundry"], AI_VERSION, missing_ok=True) is None
        or azure.get(ids["apim"], APIM_VERSION, missing_ok=True) is None
    ):
        raise SafeError("Shared resource verification failed")
    manifest["deleted"] = True
    manifest["verified"] = False
    private_write(args.manifest, json.dumps(manifest, indent=2) + "\n")
    print(
        "Verified deletion of manifest-owned workshop resources. Shared Foundry/APIM still exist."
    )
    print(
        "Local attendee .env files remain private but revoked; remove them securely when no longer needed."
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, default=ROOT / ".local/provision-manifest.json")
    p.add_argument("--confirm", required=True)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    try:
        teardown(p.parse_args())
    except SafeError as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 1
    except Exception:  # noqa: BLE001 — redact unexpected SDK/CLI response secrets
        print(
            "ERROR: teardown failed; details suppressed. Retain the manifest and inspect Azure securely.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

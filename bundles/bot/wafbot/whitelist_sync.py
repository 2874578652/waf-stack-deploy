"""Sync the Nginx CC whitelist include from the ModSecurity whitelist source."""

from pathlib import Path

from . import config


def read_waf_whitelist() -> list[str]:
    path = Path(config.IP_WHITELIST)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]


def write_cc_whitelist_include(ips: list[str]) -> None:
    path = Path(config.CC_WHITELIST_INCLUDE)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{ip} 1;" for ip in ips]
    path.write_text("\n".join(lines) + "\n" if lines else "", encoding="utf-8")


def sync_cc_whitelist_include() -> int:
    ips = read_waf_whitelist()
    write_cc_whitelist_include(ips)
    return len(ips)


def main() -> None:
    count = sync_cc_whitelist_include()
    print(f"synced {count} whitelist entries into {config.CC_WHITELIST_INCLUDE}")


if __name__ == "__main__":
    main()

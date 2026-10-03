import re
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Institution:
    id: str
    name: str
    login_url: str
    domains: tuple[str, ...]
    aliases: tuple[str, ...]
    ofx_orgs: tuple[str, ...] = ()
    ofx_fids: tuple[str, ...] = ()


# URLs in this directory are maintained by FinLeash. Uploaded documents are
# never trusted as a source for a browser destination.
INSTITUTIONS = (
    Institution("pnc", "PNC Bank", "https://www.pnc.com/", ("pnc.com",), ("pnc", "pnc bank", "pnc financial services")),
    Institution("capital-one", "Capital One", "https://www.capitalone.com/", ("capitalone.com",), ("capital one", "capital one bank")),
    Institution("fidelity", "Fidelity", "https://www.fidelity.com/", ("fidelity.com",), ("fidelity", "fidelity investments")),
    Institution("mission-lane", "Mission Lane", "https://dashboard.missionlane.com/", ("missionlane.com",), ("mission lane", "mission lane llc")),
    Institution("paypal", "PayPal", "https://www.paypal.com/", ("paypal.com",), ("paypal", "paypal credit")),
    Institution("td-bank", "TD Bank", "https://www.td.com/us/en/personal-banking", ("td.com",), ("td bank", "td auto finance", "td autofinance")),
    Institution("suncoast", "Suncoast Credit Union", "https://www.suncoast.com/", ("suncoast.com",), ("suncoast", "suncoast credit union")),
    Institution("best-egg", "Best Egg", "https://www.bestegg.com/", ("bestegg.com",), ("best egg",)),
    Institution("affirm", "Affirm", "https://www.affirm.com/", ("affirm.com",), ("affirm", "affirm inc")),
)


def _normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _tag(text: str, name: str) -> str:
    match = re.search(rf"<{name}>\s*([^<\r\n]+)", text, re.I)
    return match.group(1).strip() if match else ""


def match_institution(text: str, detected_name: str = "") -> tuple[Institution | None, str, str]:
    """Return a trusted directory match, confidence, and the signal used."""
    org = _normalized(_tag(text, "ORG"))
    fid = _normalized(_tag(text, "FID"))
    name = _normalized(detected_name)
    normalized_text = _normalized(text)
    for institution in INSTITUTIONS:
        if fid and fid in {_normalized(value) for value in institution.ofx_fids}:
            return institution, "high", "OFX institution identifier"
        if org and org in {_normalized(value) for value in institution.ofx_orgs + institution.aliases}:
            return institution, "high", "OFX institution metadata"
        aliases = {_normalized(institution.name), *(_normalized(value) for value in institution.aliases)}
        if name and name in aliases:
            return institution, "high", "statement institution name"
        if any(re.search(rf"\b{re.escape(alias)}\b", normalized_text) for alias in aliases if len(alias) >= 4):
            return institution, "medium", "statement text"
    return None, "low", "no trusted directory match"


def public_institution(institution: Institution, confidence: str, source: str) -> dict:
    result = asdict(institution)
    result.pop("aliases")
    result.pop("ofx_orgs")
    result.pop("ofx_fids")
    result["confidence"] = confidence
    result["source"] = source
    result["verified"] = True
    return result


def search_institutions(query: str = "") -> list[dict]:
    needle = _normalized(query)
    matches = [item for item in INSTITUTIONS if not needle or needle in _normalized(item.name) or any(needle in _normalized(alias) for alias in item.aliases)]
    return [public_institution(item, "directory", "FinLeash directory") for item in matches[:20]]


def get_institution(institution_id: str) -> Institution | None:
    return next((item for item in INSTITUTIONS if item.id == institution_id), None)

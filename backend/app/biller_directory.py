import re
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Biller:
    id: str
    name: str
    website_url: str
    domains: tuple[str, ...]
    aliases: tuple[str, ...]
    support_url: str | None = None
    chat_url: str | None = None
    customer_service_phone: str | None = None


BILLERS=(
    Biller("frontier","Frontier Communications","https://frontier.com/resources/pay-bill-online",("frontier.com",),("frontier","frontier communications","frontier commu")),
    Biller("verizon","Verizon","https://www.verizon.com/support/pay-bill-faqs/",("verizon.com",),("verizon","verizon wireless","my verizon")),
    Biller("att","AT&T","https://www.att.com/acctmgmt/login",("att.com",),("at&t","att","at t")),
    Biller("duke-energy","Duke Energy","https://www.duke-energy.com/home/billing/pay-bill",("duke-energy.com",),("duke energy","duke energy fl")),
    Biller("pasco-utilities","Pasco County Utilities","https://pascoeasypay.pascocountyfl.net/",("pascocountyfl.net",),("pasco county utilities","pasco county fl utilities","pasco utilities")),
    Biller("netflix","Netflix","https://www.netflix.com/login",("netflix.com",),("netflix",)),
    Biller("sunpass","SunPass","https://www.sunpass.com/vector/account/home/accountLogin.do",("sunpass.com",),("sunpass",)),
    Biller("florida-prepaid","Florida Prepaid","https://www.myfloridaprepaid.com/",("myfloridaprepaid.com",),("florida prepaid","florida prepaipayment")),
    Biller("waste-connections","Waste Connections","https://www.wasteconnections.com/",("wasteconnections.com",),("waste connections",)),
    Biller(
        "esurance",
        "Esurance",
        "https://www.esurance.com/customer-login",
        ("esurance.com",),
        ("esurance", "esurance car insurance", "esurance insurance", "800 378 7262"),
        support_url="https://www.esurance.com/company/contact-us",
        customer_service_phone="1-800-378-7262",
    ),
)


def normalized(value:str)->str:return " ".join(re.sub(r"[^a-z0-9]+"," ",value.lower()).split())


def match_biller(*values:str)->tuple[Biller|None,str]:
    haystack=" ".join(normalized(value) for value in values if value)
    for biller in BILLERS:
        aliases={normalized(biller.name),*(normalized(alias) for alias in biller.aliases)}
        if any(re.search(rf"\b{re.escape(alias)}\b",haystack) for alias in aliases if len(alias)>=3):return biller,"high"
    return None,"low"


def public_biller(biller:Biller,confidence:str="directory")->dict:
    value=asdict(biller);value.pop("aliases");value["confidence"]=confidence;value["verified"]=True;return value


def search_billers(query:str="")->list[dict]:
    needle=normalized(query)
    matches=[biller for biller in BILLERS if not needle or needle in normalized(biller.name) or any(needle in normalized(alias) or normalized(alias) in needle for alias in biller.aliases)]
    return [public_biller(biller) for biller in matches[:10]]


def get_biller(biller_id:str)->Biller|None:return next((biller for biller in BILLERS if biller.id==biller_id),None)

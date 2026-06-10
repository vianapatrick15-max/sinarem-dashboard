#!/usr/bin/env python3
"""
Pipeline de dados do Dashboard SINAREM (Aristo + MedQ).
Le a planilha DASH_ENAMED (abas DADOS_GERENCIADOR, DADOS_GERENCIADOR_MEDQ
e DADOS_HUBSPOT_SiNAREM), soma as duas frentes de captacao e escreve
data.json + index.html.

Fonte canonica:
  - Spend/impr/clicks/LPV Aristo -> DADOS_GERENCIADOR, filtrado p/ campanhas "sinarem"
  - Spend/impr/clicks/LPV MedQ   -> DADOS_GERENCIADOR_MEDQ (aba ja so tem sinarem)
  - Inscritos                    -> DADOS_HUBSPOT_SiNAREM (todas as linhas)

Atribuicao: as UTMs do HubSpot NAO carregam as campanhas sinarem (vem
vazias ou com a conversao antiga do contato), entao nao ha split
pago/organico. Todos os indicadores de custo sao BLENDED:
verba total (2 frentes) / inscritos totais.
"""
import os, json, datetime as dt
from pathlib import Path
from collections import defaultdict

SID = "1uExbyUCZ3fKqfZCayHRf-UzxgafDORPmUqucFR5OKRs"
OUT = Path(__file__).parent / "data.json"

SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]
LOCAL_CRED = os.path.expanduser("~/.claude/skills/ga4/credentials/ga4-instituto-andhela.json")

def get_client():
    """Funciona no CI (secret GOOGLE_SHEETS_CREDENTIALS_JSON) e local (arquivo da SA)."""
    import gspread
    from google.oauth2.service_account import Credentials
    raw = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON")
    if raw:
        creds = Credentials.from_service_account_info(json.loads(raw), scopes=SCOPES)
    else:
        path = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_PATH", LOCAL_CRED)
        creds = Credentials.from_service_account_file(path, scopes=SCOPES)
    return gspread.authorize(creds)

# ---------------- METAS (tabela do cliente; editar aqui) ----------------
CPL_TARGET         = 20.0       # por lead pago na tabela; aqui comparado ao blended
BUDGET             = 64000.0    # verba total das duas frentes
LEADS_PAGOS_TARGET = 3200
ORGANICO_TARGET    = 1400
TOTAL_TARGET       = 4600
CAMPAIGN_START     = dt.date(2026, 6, 4)    # 1o lead na base
EVENT_START        = dt.date(2026, 6, 19)   # abertura da prova, sexta 08h
CAPTURE_END        = dt.date(2026, 6, 21)   # ultimo horario p/ iniciar, domingo 17h
# perfis que contam como "publico certo" (em preparacao p/ residencia)
TARGET_PROFILES = {
    "Médico(a) em preparação para residência",
    "Estudante de Medicina (internato)",
    "Médico(a) recém-formado(a)",
}
try:
    from zoneinfo import ZoneInfo
    TODAY = dt.datetime.now(ZoneInfo("America/Sao_Paulo")).date()
except Exception:
    TODAY = (dt.datetime.utcnow() - dt.timedelta(hours=3)).date()
# -----------------------------------------------------------------------

def num(x):
    if x is None: return 0.0
    s = str(x).strip().replace(".", "").replace(",", ".")
    if s in ("", "-"): return 0.0
    try: return float(s)
    except: return 0.0

def is_sinarem(c): return "sinarem" in (c or "").lower()

gc = get_client()
sh = gc.open_by_key(SID)

# ---------- GERENCIADOR (2 frentes) ----------
def read_front(title, front, camp_filter, ad_col):
    """Le uma aba de gerenciador e devolve agregados + linhas por criativo."""
    g = sh.worksheet(title).get_all_values()
    gh = {h.strip(): i for i, h in enumerate(g[0])}
    C_DAY, C_CAMP = gh["Day"], gh["Campaign Name"]
    C_IMPR, C_SPEND, C_CLK = gh["Impressions"], gh["Amount Spent"], gh["Link Clicks"]
    C_LPV, C_AD = gh["Landing Page Views"], gh[ad_col]
    rows = [r for r in g[1:] if any(c.strip() for c in r) and len(r) > C_CAMP
            and (not camp_filter or is_sinarem(r[C_CAMP]))]
    agg = {"front": front, "spend": 0.0, "impressions": 0.0, "clicks": 0.0, "lpv": 0.0}
    by_day = defaultdict(float)
    by_ad = defaultdict(lambda: {"spend": 0.0, "clicks": 0.0, "lpv": 0.0})
    for r in rows:
        s = num(r[C_SPEND]) if len(r) > C_SPEND else 0
        agg["spend"] += s
        agg["impressions"] += num(r[C_IMPR])
        agg["clicks"] += num(r[C_CLK]) if len(r) > C_CLK else 0
        agg["lpv"] += num(r[C_LPV]) if len(r) > C_LPV else 0
        by_day[r[C_DAY]] += s
        ad = r[C_AD] if len(r) > C_AD else ""
        by_ad[ad]["spend"] += s
        if len(r) > C_CLK: by_ad[ad]["clicks"] += num(r[C_CLK])
        if len(r) > C_LPV: by_ad[ad]["lpv"] += num(r[C_LPV])
    return agg, by_day, by_ad

aristo, aristo_day, aristo_ads = read_front("DADOS_GERENCIADOR", "Aristo", True, "Ad Name")
medq, medq_day, medq_ads = read_front("DADOS_GERENCIADOR_MEDQ", "MedQ", False, "Ad Set Name")

spend = aristo["spend"] + medq["spend"]
impr = aristo["impressions"] + medq["impressions"]
clk = aristo["clicks"] + medq["clicks"]
lpv = aristo["lpv"] + medq["lpv"]
spend_by_day = defaultdict(float)
for d, v in list(aristo_day.items()) + list(medq_day.items()):
    spend_by_day[d] += v

# ---------- HUBSPOT (inscritos) ----------
h = sh.worksheet("DADOS_HUBSPOT_SiNAREM").get_all_values()
hh = {x.strip(): i for i, x in enumerate(h[0])}
H_DATA, H_PERFIL = hh["Data de conversão recente"], hh["Momento do Perfil"]
hrows = [r for r in h[1:] if any(c.strip() for c in r) and len(r) > H_DATA and r[H_DATA].strip()]

def daykey(s):  # "05/06/2026 16:56:38" -> "2026-06-05"
    d = s.strip().split(" ")[0]
    try:
        dd, mm, yy = d.split("/"); return f"{yy}-{mm}-{dd}"
    except: return ""

total_inscritos = len(hrows)
leads_by_day = defaultdict(int)
perfil_count = defaultdict(int)
for r in hrows:
    leads_by_day[daykey(r[H_DATA])] += 1
    p = r[H_PERFIL].strip() if len(r) > H_PERFIL else ""
    perfil_count[p or "Não informado"] += 1

publico_n = sum(n for p, n in perfil_count.items() if p in TARGET_PROFILES)
pct_publico = round(100 * publico_n / total_inscritos, 1) if total_inscritos else 0

# ---------- PACE / PROJECAO (janela ate o fim da captacao 21/06) ----------
all_days = sorted(set(spend_by_day) | set(leads_by_day))
all_days = [d for d in all_days if d]
full_days = [d for d in all_days if d < TODAY.isoformat()]
n_full = max(len(full_days), 1)
days_left = max(0, (CAPTURE_END - TODAY).days)        # ate o fim da captacao
days_to_event = max(0, (EVENT_START - TODAY).days)    # ate a abertura da prova

leads_per_day_full = sum(leads_by_day[d] for d in full_days) / n_full
spend_per_day_full = sum(spend_by_day[d] for d in full_days) / n_full

cpl_blended = spend / total_inscritos if total_inscritos else 0
proj_total = round(total_inscritos + leads_per_day_full * (days_left + 1))
proj_spend = round(spend + spend_per_day_full * (days_left + 1), 2)
need_per_day = (TOTAL_TARGET - total_inscritos) / (days_left + 1) if days_left >= 0 else 0
budget_left = BUDGET - spend
budget_per_day_needed = budget_left / (days_left + 1) if days_left >= 0 else 0

# ---------- series acumuladas ----------
cum_leads = cum_spend = 0
series = []
for d in all_days:
    cum_leads += leads_by_day.get(d, 0)
    cum_spend += spend_by_day.get(d, 0)
    series.append({
        "day": d,
        "leads": leads_by_day.get(d, 0),
        "spend": round(spend_by_day.get(d, 0), 2),
        "cum_leads": cum_leads,
        "cum_spend": round(cum_spend, 2),
    })

# ---------- por criativo (Aristo por ad, MedQ por conjunto) ----------
ads = []
for front, by_ad in (("Aristo", aristo_ads), ("MedQ", medq_ads)):
    for ad, m in by_ad.items():
        ads.append({
            "front": front, "ad": ad,
            "spend": round(m["spend"], 2),
            "clicks": int(m["clicks"]),
            "lpv": int(m["lpv"]),
            "cplpv": round(m["spend"] / m["lpv"], 2) if m["lpv"] else None,
        })
ads.sort(key=lambda a: -a["spend"])

perfil = sorted(({"label": p, "n": n, "pct": round(100 * n / total_inscritos, 1)}
                 for p, n in perfil_count.items()), key=lambda x: -x["n"])

data = {
    "updated_at": dt.datetime(TODAY.year, TODAY.month, TODAY.day, 12, 0).isoformat(),
    "today": TODAY.isoformat(),
    "event_start": EVENT_START.isoformat(),
    "capture_end": CAPTURE_END.isoformat(),
    "campaign_start": CAMPAIGN_START.isoformat(),
    "days_left": days_left,
    "days_to_event": days_to_event,
    "targets": {
        "cpl": CPL_TARGET, "budget": BUDGET,
        "leads_pagos": LEADS_PAGOS_TARGET, "organico": ORGANICO_TARGET, "total": TOTAL_TARGET,
    },
    "kpis": {
        "inscritos": total_inscritos,
        "publico_n": publico_n,
        "pct_publico": pct_publico,
        "spend": round(spend, 2),
        "spend_aristo": round(aristo["spend"], 2),
        "spend_medq": round(medq["spend"], 2),
        "impressions": int(impr),
        "clicks": int(clk),
        "lpv": int(lpv),
        "cpl_blended": round(cpl_blended, 2),
        "cpc": round(spend / clk, 2) if clk else 0,
        "cplpv": round(spend / lpv, 2) if lpv else 0,
        "pct_budget_gasto": round(100 * spend / BUDGET, 1),
    },
    "pace": {
        "full_days": n_full,
        "leads_per_day": round(leads_per_day_full, 1),
        "spend_per_day": round(spend_per_day_full, 2),
        "need_per_day": round(need_per_day, 1),
        "budget_per_day_needed": round(budget_per_day_needed, 2),
        "proj_total": proj_total,
        "proj_spend": proj_spend,
        "on_track_leads": proj_total >= TOTAL_TARGET,
        "on_track_cpl": cpl_blended <= CPL_TARGET,
    },
    "series": series,
    "fronts": [
        {"front": "Aristo", **{k: round(v, 2) if isinstance(v, float) else v
                               for k, v in aristo.items() if k != "front"}},
        {"front": "MedQ", **{k: round(v, 2) if isinstance(v, float) else v
                             for k, v in medq.items() if k != "front"}},
    ],
    "ads": ads,
    "perfil": perfil,
}
OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2))

# ---------- render index.html (dados embutidos, graficos em SVG nativo) ----------
base = Path(__file__).parent
tpl = (base / "template.html").read_text()
html = tpl.replace("__DATA__", json.dumps(data, ensure_ascii=False))
(base / "index.html").write_text(html)

# ---------- resumo no terminal ----------
print(f"INSCRITOS: {total_inscritos} (meta {TOTAL_TARGET}) | publico certo: {publico_n} ({pct_publico}%)")
print(f"SPEND: R$ {spend:,.2f} (Aristo {aristo['spend']:,.0f} + MedQ {medq['spend']:,.0f}) / R$ {BUDGET:,.0f} ({data['kpis']['pct_budget_gasto']}%)")
print(f"CPL blended: R$ {cpl_blended:,.2f} (meta R$ {CPL_TARGET:.0f}) | CPC: R$ {data['kpis']['cpc']} | custo/LPV: R$ {data['kpis']['cplpv']}")
print(f"PACE (dias cheios={n_full}): {leads_per_day_full:.1f} inscritos/dia | spend {spend_per_day_full:.0f}/dia")
print(f"DIAS: {days_to_event} ate a abertura (19/06) | {days_left} ate o fim da captacao (21/06)")
print(f"PRECISA: {need_per_day:.1f} inscritos/dia p/ {TOTAL_TARGET} | budget/dia p/ gastar tudo: R$ {budget_per_day_needed:,.0f}")
print(f"PROJECAO run-rate: {proj_total} inscritos | R$ {proj_spend:,.0f} gastos")
print("\n-- por criativo/conjunto (spend desc) --")
for a in ads:
    print(f"  [{a['front']:<6}] {a['ad']:<38} R$ {a['spend']:>9,.0f} | {a['lpv']:>4} LPV | {a['clicks']:>4} cliques")
print(f"\nOK -> {OUT}")

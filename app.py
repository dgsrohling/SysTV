"""Painel de acompanhamento de licitações (dados de uma planilha pública do Google Sheets)."""
import csv
import io
import os
import re
import time
import unicodedata
from collections import Counter
from datetime import datetime

import requests
from flask import Flask, jsonify, redirect, render_template, request, url_for

SHEET_ID = os.getenv("SHEET_ID", "1pjmYgf38g9kS13gOAOBNsRiSpF3ZdQR9VqCNKIVfeEo")
SHEET_GID = os.getenv("SHEET_GID", "")            # aba (gid na URL); vazio = primeira aba
REFRESH = int(os.getenv("REFRESH", "60"))         # segundos entre atualizações automáticas da tela
# O cache expira um pouco antes do intervalo da tela, para que cada atualização traga dados novos
CACHE_TTL = int(os.getenv("CACHE_TTL", str(max(REFRESH - 5, 10))))

app = Flask(__name__)
_cache = {}  # gid -> (timestamp, dados)

# Campos internos -> trecho do nome da coluna na planilha (comparação sem acento/maiúscula)
FIELDS = {
    "id": "id",
    "obra": "obras",
    "secretaria": "secretaria",
    "sei": "sei",
    "responsavel": "responsavel",
    "envio_proge": "envio proge",
    "publicacao": "publicacao edital",
    "abertura": "abertura licitacao",
    "fase": "fases do certame",
    "presidente": "presidente",
    "observacao": "observacao",
    "homologacao": "homologacao",
    "valor_orcado": "valor orcado",
    "valor_vencedor": "valor vencedor",
    "desconto": "desc",
    "atualizado": "atualizado em",
}

MONEY_RE = re.compile(r"\d{1,3}(?:\.\d{3})*(?:,\d+)?|\d+(?:,\d+)?")


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", text).strip().lower()


def clean(value: str) -> str:
    """Remove espaços e trata '0' como vazio (a planilha usa 0 em células sem informação)."""
    value = (value or "").strip()
    return "" if value == "0" else value


def to_number(text: str):
    """'23.482.146,23' -> 23482146.23. Para textos com vários valores (lotes), soma todos."""
    text = (text or "").replace("R$", "")
    # ignora números de lote ("LOTE 01:")
    text = re.sub(r"lote\s*\d+\s*:", "", text, flags=re.I)
    nums = [float(m.replace(".", "").replace(",", ".")) for m in MONEY_RE.findall(text)]
    return sum(nums) if nums else None


def to_date(text: str):
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y"):
        try:
            return datetime.strptime((text or "").strip(), fmt)
        except ValueError:
            pass
    return None


def brl(v) -> str:
    if v is None:
        return "—"
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def short_brl(v) -> str:
    if v is None:
        return "—"
    for div, suf in ((1e9, "bi"), (1e6, "mi"), (1e3, "mil")):
        if abs(v) >= div:
            return f"R$ {v / div:,.1f} {suf}".replace(".", ",")
    return brl(v)


def phase_parts(fase: str):
    """'9 - FASE RECURSAL' -> (9, 'FASE RECURSAL')."""
    m = re.match(r"\s*(\d+)\s*-\s*(.+)", fase or "")
    return (int(m.group(1)), m.group(2).strip()) if m else (None, fase or "")


def load_sheet(gid: str, force: bool = False) -> dict:
    now = time.time()
    if not force and gid in _cache and now - _cache[gid][0] < CACHE_TTL:
        return _cache[gid][1]

    url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"
    if gid:
        url += f"&gid={gid}"
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
    except requests.RequestException:
        if gid in _cache:  # falha temporária: mantém os últimos dados obtidos
            return _cache[gid][1]
        raise
    resp.encoding = "utf-8"
    rows = list(csv.reader(io.StringIO(resp.text)))

    # Localiza a linha de cabeçalho (primeira célula "ID")
    hdr_idx = next((i for i, r in enumerate(rows) if r and norm(r[0]) == "id"), None)
    if hdr_idx is None:
        raise SheetError("Cabeçalho não encontrado: a planilha precisa ter uma linha começando com \"ID\".")
    header = [norm(h) for h in rows[hdr_idx]]
    info_row = rows[hdr_idx - 1] if hdr_idx > 0 else []
    title = " ".join(c for c in (rows[0] if hdr_idx > 1 else []) if c.strip())

    col = {}
    for key, needle in FIELDS.items():
        for i, h in enumerate(header):
            if needle in h and i not in col.values() and (key != "id" or h == "id"):
                col[key] = i
                break
    # Coluna sem cabeçalho no fim = HABILITADO (o rótulo está na linha de cima)
    hab_idx = next((i for i, c in enumerate(info_row) if norm(c) == "habilitado"), None)

    items = []
    for r in rows[hdr_idx + 1:]:
        r = r + [""] * (len(header) - len(r))
        get = lambda k: clean(r[col[k]]) if k in col else ""  # noqa: E731
        if not get("obra"):
            continue
        num, nome_fase = phase_parts(get("fase"))
        orcado, vencedor = to_number(get("valor_orcado")), to_number(get("valor_vencedor"))
        desconto = (1 - vencedor / orcado) * 100 if orcado and vencedor else None
        items.append({
            **{k: get(k) for k in FIELDS},
            "fase_num": num,
            "fase_nome": nome_fase or "Sem fase informada",
            "orcado_num": orcado,
            "vencedor_num": vencedor,
            "orcado_fmt": brl(orcado),
            "vencedor_fmt": brl(vencedor) if vencedor else "—",
            "desconto_calc": f"{desconto:.2f}%".replace(".", ",") if desconto is not None else "—",
            "habilitado": hab_idx is not None and norm(r[hab_idx]) in ("true", "verdadeiro", "sim"),
            "abertura_dt": to_date(get("abertura")),
        })

    data = {
        "title": title or "Licitações",
        "data_ref": info_row[0].strip() if info_row else "",
        "equipes": [c.strip() for c in info_row[1:] if c.strip() and norm(c) != "habilitado"],
        "items": items,
        "fetched": now,
    }
    _cache[gid] = (now, data)
    return data


def apply_filters(items, args):
    out = items
    for key in ("secretaria", "responsavel", "presidente", "fase_nome"):
        if args.get(key):
            out = [i for i in out if i[key] == args[key]]
    q = norm(args.get("q", ""))
    if q:
        out = [i for i in out if q in norm(" ".join(str(v) for v in i.values()))]
    return out


FILTER_KEYS = ("fase_nome", "secretaria", "responsavel", "presidente")
VIEWS = [("dashboard", "Painel"), ("cards", "Cards"), ("secretarias", "Por secretaria")]


class SheetError(Exception):
    """A planilha não pôde ser lida ou não está no formato esperado."""


@app.errorhandler(requests.RequestException)
@app.errorhandler(SheetError)
def sheet_error(exc):
    return render_template("error.html", error=str(exc)), 502


def contexto(**extra):
    """Dados e variáveis comuns a todas as exibições."""
    gid = request.args.get("gid", SHEET_GID)
    data = load_sheet(gid)
    filters = {k: v for k, v in request.args.items() if v and (k in FILTER_KEYS or k == "q")}
    return dict(
        data=data,
        items=apply_filters(data["items"], request.args),
        filters=filters,
        gid=gid,
        tv=request.args.get("tv") == "1",
        refresh=REFRESH,
        views=VIEWS,
        updated=time.strftime("%d/%m/%Y %H:%M:%S", time.localtime(data["fetched"])),
        sheet_url=f"https://docs.google.com/spreadsheets/d/{SHEET_ID}",
        **extra,
    )


@app.route("/")
def dashboard():
    ctx = contexto()
    items = ctx["items"]
    hoje = datetime.now().date()

    total_orcado = sum(i["orcado_num"] or 0 for i in items)
    proximas = sorted(
        (i for i in items if i["abertura_dt"] and i["abertura_dt"].date() >= hoje),
        key=lambda i: i["abertura_dt"],
    )
    kpis = [
        {"label": "Processos", "value": len(items)},
        {"label": "Valor orçado total", "value": short_brl(total_orcado), "hint": brl(total_orcado)},
        {"label": "Homologados", "value": sum(1 for i in items if i["homologacao"])},
        {"label": "Próxima abertura",
         "value": proximas[0]["abertura"] if proximas else "—",
         "hint": proximas[0]["obra"] if proximas else ""},
    ]

    def count(key):
        c = Counter(i[key] or "Não informado" for i in items)
        return {"labels": list(c.keys()), "values": list(c.values())}

    fases = sorted(Counter((i["fase_num"], i["fase_nome"]) for i in items).items(),
                   key=lambda kv: (kv[0][0] is None, kv[0][0] or 0))
    charts = [
        {"title": "Processos por fase",
         "labels": [f"{n} - {nome}" if n is not None else nome for (n, nome), _ in fases],
         "values": [v for _, v in fases]},
        {"title": "Processos por secretaria", **count("secretaria")},
        {"title": "Processos por responsável", **count("responsavel")},
    ]
    options = {k: sorted({i[k] for i in ctx["data"]["items"] if i[k]}) for k in FILTER_KEYS}
    return render_template("dashboard.html", kpis=kpis, charts=charts, options=options, **ctx)


@app.route("/cards")
def cards():
    return render_template("cards.html", **contexto())


@app.route("/secretarias")
def secretarias():
    ctx = contexto()
    grupos = {}
    for i in ctx["items"]:
        grupos.setdefault(i["secretaria"] or "Não informada", []).append(i)
    lista = []
    for nome, itens in sorted(grupos.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        total = sum(i["orcado_num"] or 0 for i in itens)
        lista.append({"nome": nome, "itens": itens, "total": short_brl(total), "total_full": brl(total)})
    return render_template("secretarias.html", secretarias=lista, **ctx)


@app.route("/refresh")
def refresh():
    gid = request.args.get("gid", SHEET_GID)
    load_sheet(gid, force=True)
    view = request.args.get("view", "dashboard")
    return redirect(url_for(view if view in dict(VIEWS) else "dashboard", gid=gid or None))


@app.route("/api/licitacoes")
def api():
    data = load_sheet(request.args.get("gid", SHEET_GID))
    items = [{k: v for k, v in i.items() if k != "abertura_dt"} for i in data["items"]]
    return jsonify({**data, "items": items})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8050")), debug=True)

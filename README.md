# Dashboard — SINAREM 2026 (Captação do Simulado)

Relatório de acompanhamento da captação do SINAREM (simulado nacional de
residência médica — Aristo + MedQ). Atualiza sozinho todo dia às **07:00 BRT**
via GitHub Action, lendo a planilha de acompanhamento e republicando no
GitHub Pages.

- **Link:** https://vianapatrick15-max.github.io/sinarem-dashboard/
- **Fonte:** planilha `DASH_ENAMED` — abas:
  - `DADOS_GERENCIADOR` (Meta Aristo, filtrado p/ campanhas contendo `sinarem`)
  - `DADOS_GERENCIADOR_MEDQ` (Meta MedQ, aba já só com sinarem)
  - `DADOS_HUBSPOT_SiNAREM` (inscrições — todas as linhas)
- **Evento:** prova 19 a 21/06/2026 (abertura sex 19/06 08h, último início dom 21/06 17h).

## Modelagem
- O dash **soma as duas frentes** de mídia (Aristo + MedQ) e conta **todos**
  os leads da aba HubSpot.
- **Sem split pago/orgânico**: as UTMs do HubSpot não carregam as campanhas
  sinarem (vêm vazias ou com a conversão antiga do contato). Por isso o
  custo por inscrito é **blended** = verba total ÷ inscritos totais,
  comparado à referência de CPL da meta (R$ 20).
- Tabela por criativo traz só métricas de mídia (investido, cliques, LPV) —
  Aristo por anúncio, MedQ por conjunto (a aba MedQ não exporta Ad Name).
- "Público certo" = Momento do Perfil em preparação para residência
  (preparação p/ residência + internato + recém-formado).

## Metas (tabela do cliente)
CPL R$ 20 · verba R$ 64.000 · ~3.200 leads pagos · ~1.400 orgânico (31%) · ~4.600 total.

## Como funciona
- `refresh.py` lê a planilha, calcula os indicadores e gera `data.json` +
  `index.html` (auto-contido, gráficos em SVG nativo, sem dependências externas).
- O Action roda `refresh.py` no cron e commita o resultado; o Pages serve o `index.html`.

## Editar metas
As metas (CPL, verba, leads, datas) ficam no topo do `refresh.py`.

## Rodar local
```
pip install -r requirements.txt
python refresh.py   # usa a credencial local da service account
```

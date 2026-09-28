# Deploy

O site é HTML estático servido por um Caddy dentro de um container, atrás do
edge Caddy compartilhado da VPS (mesmo molde do peladex). O container não
publica porta: o edge o alcança pelo alias `fund-monitor-web` na rede Docker
externa `web`.

O repositório é privado até a entrega. O `git pull` na VPS precisa de acesso
só leitura ao GitHub: use o mesmo mecanismo dos outros sites.

## Fluxo diário

1. A GitHub Action `daily` (`.github/workflows/daily.yml`) roda em dia útil às
   20h de Brasília (23:00 UTC). Ela restaura o bruto de `data/raw` do cache,
   roda os testes e o pipeline, compila o site como verificação e, se
   `data/parquet` ou `data/site` mudaram, commita "Atualiza dados até
   {as_of}" e faz push.
2. Às 21h30 de Brasília um cron na VPS faz `git pull` e reconstrói a imagem.
   A imagem compila o site a partir de `data/site` e `docs/` do checkout.

## Primeira instalação na VPS

Pré-requisitos: Docker com Compose, a rede `web` e o edge já rodando (é o
caso na VPS do autor).

```bash
git clone <url do repositório> /srv/fund-monitor
```

O compose do app não lê variável nenhuma. O `.env.example` da raiz documenta
o valor de `FUND_MONITOR_DOMAIN`, que vai no `.env` do edge. No diretório do
edge:

```bash
cp /srv/fund-monitor/deploy/edge/sites/fund-monitor.caddy <edge>/sites/
echo 'FUND_MONITOR_DOMAIN=fund-monitor.rastrovin.org' >> <edge>/.env
```

Suba o app e depois recarregue o edge (o `.env` do edge só é relido quando o
container é recriado, por isso `up -d --force-recreate` e não `caddy reload`):

```bash
cd /srv/fund-monitor && docker compose up -d --build
cd <edge> && docker compose up -d --force-recreate
```

Valide pela própria VPS, passando pelo edge:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -H 'Host: fund-monitor.rastrovin.org' http://localhost/
curl -s -o /dev/null -w '%{http_code}\n' -H 'Host: fund-monitor.rastrovin.org' http://localhost/fundo/04820026000137
```

Os dois devem devolver `200`. Depois do DNS, valide pelo domínio:
`curl -I https://fund-monitor.rastrovin.org`.

## Cron na VPS

Uma linha no crontab do usuário que roda o Docker. O horário é 21h30 de
Brasília, depois da Action; ajuste ao fuso da VPS (em UTC seria
`30 0 * * 2-6`):

```cron
30 21 * * 1-5 cd /srv/fund-monitor && git pull --ff-only && docker compose up -d --build >> /var/log/fund-monitor-deploy.log 2>&1
```

Cada rebuild deixa a imagem anterior órfã. Um `docker image prune -f` semanal
no mesmo crontab evita acumular.

## DNS no Cloudflare

Registro `A` de `fund-monitor` apontando para o IP da VPS, com proxy ligado
(nuvem laranja). O edge escuta em HTTP e o Cloudflare termina o TLS no modo
Flexible, igual ao peladex.

## Forçar uma atualização à mão

- Dados novos agora: GitHub, aba Actions, workflow `daily`, **Run workflow**
  (ou `gh workflow run daily.yml`). Espere terminar.
- Publicar sem esperar o cron, na VPS:

```bash
cd /srv/fund-monitor && git pull --ff-only && docker compose up -d --build
```

## Se a Action falhar

Rode o pipeline na própria VPS (precisa do `uv`; ele instala o Python 3.12):

```bash
cd /srv/fund-monitor/pipeline
uv sync --frozen
uv run python -m fund_monitor.run
cd .. && docker compose up -d --build
```

Sem o bruto em `data/raw` a primeira coleta baixa ~290 MB e leva ~12 min por
causa da ANBIMA; as seguintes usam o cache e levam ~35 s.

Os dados gerados assim ficam só na VPS e deixam o checkout sujo, o que faz o
`git pull --ff-only` do cron falhar. Quando a Action voltar a commitar,
descarte a versão local antes do próximo pull:

```bash
cd /srv/fund-monitor && git checkout -- data/parquet data/site && git clean -fd data/parquet data/site
```

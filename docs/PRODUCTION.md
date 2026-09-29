# Como seria em produção

Este protótipo roda num processo só, uma vez por dia, e publica JSON estático. Funciona para 75 séries de uma gestora e um leitor. Uma mesa que decide com esses números precisa de mais: saber quando um dado chegou atrasado, reproduzir o que viu num dia passado e não publicar um número errado. Abaixo, o que eu mudaria, em que ordem, e o que conseguiria fazer sozinho.

## 1. Ponto de partida

O caminho é contínuo, não uma reescrita. O protótipo já tem as peças que um sistema de produção reaproveita:

- **Resposta conferida antes de gravar.** O Bacen só grava o JSON se ele for a série (a resposta HTML com status 200 é descartada, com até 3 tentativas). A ANBIMA só grava o dia se o arquivo tiver o cabeçalho esperado ou o aviso de "não há dados"; qualquer outra resposta não é gravada e o dia volta na execução seguinte. A B3 só grava o ano se a resposta for legível e, para ano passado, tiver fechamentos. Na CVM, o bruto é gravado como veio: o informe vai para um `.part` que só substitui o arquivo anterior no fim do download, e o cabeçalho e o CNPJ são conferidos na leitura, antes de gravar o Parquet; o cadastro também só é conferido na leitura. Uma resposta ruim da CVM faz a execução falhar. No cadastro, o ZIP ruim fica em disco e a execução seguinte do mesmo dia não o baixa de novo, porque só baixa quando o snapshot do dia não existe.
- **Coleta que só busca o que mudou.** O informe diário só é baixado de novo quando o tamanho ou o Last-Modified mudam. Um dia da ANBIMA já gravado só é pedido de novo se veio vazio e é recente (até 7 dias) ou se o arquivo gravado não é uma resposta esperada. Um ano passado da B3 só é pedido até o arquivo ser final. O Bacen e o ano corrente da B3 são pedidos a cada execução. Rodar duas vezes seguidas, com as fontes paradas, dá os mesmos dados; muda só a hora de geração.
- **Universo por subclasse informada.** Uma subclasse só vira série quando está em funcionamento normal e já publicou cota; até lá, a classe é monitorada como ela mesma. O cadastro normalizado guarda essa marca (`subclass_reported`).
- **Recálculo a partir do git.** O bruto fica fora do git, no cache da Action, só na versão mais recente de cada arquivo. O Parquet normalizado, as métricas e o JSON do site ficam versionados, e as etapas de cálculo, qualidade e publicação leem só Parquet. Rodar essas três etapas no commit de um dia, com `REFERENCE_DATE` daquele dia, refaz o site publicado; conferido para a rodada de 28/09/2026, só a hora de geração muda.
- **Rotina diária.** Uma GitHub Action roda de segunda a sexta às 20h17 de Brasília (`17 23 * * 1-5` em UTC), com `TZ=America/Sao_Paulo`: instala as dependências travadas (`uv sync --frozen`, com o índice público do PyPI declarado no `pyproject.toml`), roda os testes e o pipeline com `uv run --frozen` e, se `data/parquet` ou `data/site` mudaram além do `meta.json`, commita como `github-actions[bot]` e faz push. Depois compila o site com `BASE_PATH=/fund-monitor`, confere que `web/build/index.html` existe e publica o build no GitHub Pages. Push feito pela própria Action não dispara outro workflow, por isso o `daily.yml` publica sozinho; o `pages.yml` publica a cada push humano na `main`. Endereço inexistente cai no `404.html`, que mostra a página de erro do site. O GitHub Pages não deixa configurar cabeçalho de cache e serve tudo com o cache padrão dele, de 10 minutos. Qualquer pessoa reproduz a rodada com `cd pipeline && uv run --frozen python -m fund_monitor.run` e o site com `cd web && npm ci && npm run build`.
- **Contrato do JSON.** Os modelos pydantic de `publish/site_json.py` recusam campo a mais ou a menos. A publicação termina relendo todos os JSON escritos com esses modelos (`verify_site`) e conferindo que o número de séries, de resumos e de arquivos de fundo bate, que a soma dos alertas por severidade bate com a lista e que cada arquivo de fundo tem a série do próprio nome. Os testes publicam um site com dados sintéticos (`pipeline/tests/builders.py`) e conferem que `verify_site` recusa um site sem um arquivo de fundo ou com campo a mais. O front depende desse contrato, não do formato do Parquet.
- **Regras como código testado.** As 9 regras de qualidade estão em `quality/checks.py`, com limiares em constantes com nome e testes em `pipeline/tests/`.

## 2. Dado interno e dado público

Este monitor olha a gestora de fora, pelo que ela envia à CVM. Dentro da gestora, a ordem das fontes se inverte.

- **Fundos da casa: administrador e sistema interno.** A cota oficial de cada fundo sai do administrador no D0 ou no D+1, e a carteira sai do sistema interno. A CVM só publica o informe diário com 2 a 3 dias úteis de atraso: na rodada de 29/09/2026, o último dia completo era 24/09/2026. Em produção, os indicadores dos fundos próprios são calculados sobre a cota do administrador, e o informe da CVM não é a fonte deles.
- **CVM: pares e conferência do que foi enviado.** O informe continua sendo a única fonte dos pares, que são fundos de outras gestoras. E serve para conferir o que a gestora mandou ao regulador contra a cota interna. A linha zerada de 16/03/2026 e a duplicidade `FI` × `CLASSES - FIF` de 24/04/2025 (`findings.md`, itens 4 e 5) são erros de envio: a cota interna estava certa, e o erro só aparece no dado público. Uma regra nova, "cota da CVM diferente da cota do administrador no mesmo dia", pega esse caso no dia em que ele entra.
- **Horário.** O número da mesa precisa estar pronto antes da abertura: a cota D0 do administrador processada até cerca de 9h do D+1. O monitor público roda às 20h17 e mostra o dia D-2 ou D-3; ele serve para a comparação com o mercado, não para a decisão do dia.
- **Fonte atrasada.** Quando uma fonte não chega no horário, a publicação sai assim mesmo: o que depende dela fica marcado com o alerta de fonte atrasada e com a data do último dado, e o resto não espera. Hoje a regra 8 já marca o atraso, mas a execução é uma só (ver 3). Se o administrador atrasa, a mesa vê a cota de ontem com a marca, não uma tela vazia.
- **Precisão das regras.** Cada alerta tratado tem um desfecho (`explained`, `source_error`, `limitation`; `DECISIONS.md` §5.3). Por regra, a fração de alertas que viraram erro da fonte ou evento real, contra a fração explicada por mercado e a que ficou aberta, é a medida de precisão. Uma regra cujo desfecho mais comum é "era mercado" está com o limiar ou a referência de mercado errados e precisa de recalibração. É com esse número, e não com a intuição, que 5 desvios-padrão ou 1 % do PL se defendem.

## 3. Orquestração

- **Um fluxo por fonte**, em Dagster ou Airflow: cadastro CVM, informe diário, Bacen, ANBIMA e B3. Hoje, se a CVM cai, tudo espera; foi o que aconteceu em 26 e 27/09/2026. Separado, só o que depende da CVM espera, e o resto publica com o alerta de fonte atrasada.
- **Partição por `(fonte, data)`.** Backfill é reprocessar partições. Como a coleta já regrava cada mês, dia ou ano inteiro, reprocessar não duplica nada.
- **Dependências explícitas.** O cálculo só roda quando o dia do informe está completo. A regra dos 90 % das séries vira um sensor, em vez de um filtro dentro do cálculo.
- **Retry com espera crescente** nas fontes instáveis (portal da CVM, formulário da ANBIMA). Depois do último retry, alerta. Hoje só o Bacen tem nova tentativa, 3 vezes com 2 s fixos; nas outras fontes, a falha derruba a execução, e a ANBIMA pede o dia de novo na execução seguinte.
- **Por que Dagster:** o modelo de "ativos" (arquivo bruto → Parquet → métricas → JSON) é o desenho que o pipeline já tem. Airflow também serve; a escolha depende do que a casa já usa.

## 4. Armazenamento

| Camada | Hoje | Em produção |
| --- | --- | --- |
| Bruto | `data/raw/`, fora do git, no cache da Action; sobrescrito quando a fonte republica | S3 imutável, particionado por fonte e data, **guardando cada versão** do arquivo |
| Normalizado | Parquet no git | Parquet no lake, particionado por fonte e mês |
| Analítico | Parquet de métricas | Postgres, ou DuckDB/Athena sobre o lake |
| Entrega | JSON estático por fundo | API com cache, lida pelo site e por outras ferramentas da mesa |

Guardar cada versão do bruto importa porque a CVM regrava o histórico. Em 27/09/2026 ela regravou 25 meses. Hoje, nas séries que o pipeline guarda, a revisão fica no git como diferença entre dois commits do Parquet: foi assim que as 17 linhas revisadas foram contadas (`findings.md`, item 11). O que se perde é o resto do arquivo antigo, as colunas descartadas e os CNPJs fora do filtro. Sem o bruto antigo, não dá para refazer o passado com um CNPJ ou uma coluna nova.

## 5. Qualidade

- **As 9 regras como testes de dados** dentro do fluxo, com as mesmas funções de hoje ou com Great Expectations.
- **Severidade alta bloqueia a publicação da série afetada**, não do site inteiro. Uma linha zerada num fundo não deveria segurar os outros 74.
- **Relatório diário para a mesa com o que é novo.** Hoje a lista acumula os alertas de 24 meses, e o alerta de ontem se perde entre eles.
- **Estado do alerta.** Visto, explicado, erro da fonte. Hoje o estado vem de `data/triage.json`, editado à mão (`DECISIONS.md` §5.3), e o alerta ainda não tem dono nem prazo. Em produção, o `triage.json` vira uma tabela com dono e prazo por alerta, alimentada pela mesa.
- **Limiares revisados com a mesa.** 5 desvios-padrão, 0,1 %, 1 % do PL e 10 % do mercado foram calibrados olhando 24 meses de uma gestora. Precisam de uma revisão com quem usa o alerta.

## 6. Observabilidade

- **Log estruturado** em JSON por etapa: linhas lidas, séries, alertas, duração. Hoje o log já traz essas contagens, mas em texto.
- **Frescor por fonte como métrica.** Hoje o JSON traz só a última data de cada fonte (`meta.sources`); o atraso em dias de semana é calculado pela regra 8, mas só aparece como alerta quando passa da tolerância. Em produção, o atraso de toda fonte, todo dia, vai para um painel.
- **Painel de saúde:** última execução, duração, fontes atrasadas, alertas novos por severidade.
- **Alerta no canal da mesa** quando a execução falha ou uma fonte passa da tolerância. Hoje só existe o aviso padrão do GitHub quando a Action falha.

## 7. Governança

- **Dicionário de dados.** Cada campo publicado com unidade, fonte e coluna de origem. Exemplo: `pct_cdi_12m` é fração, razão de retornos acumulados, vazia com menos de 12 meses, com a série parada há mais de 7 dias ou com CDI do período não positivo.
- **Versão das fórmulas.** Um número de versão do cálculo gravado junto de cada publicação. Quando um limiar muda, dá para saber qual versão gerou cada número.
- **Reprodutibilidade por data de referência.** Hoje já dá para recalcular o que a mesa viu num dia: o commit daquele dia tem o código e o Parquet, e as etapas de cálculo, qualidade e publicação não leem o bruto (ver 1). Falta o passo manual virar rotina, com a data de referência como parâmetro do orquestrador. O bruto imutável serve para outra coisa: derivar de novo o passado com CNPJs ou colunas que o Parquet não guardou.
- **Cadastro por data.** Guardar a foto diária do cadastro, para que uma mudança de classificação não reescreva o passado. Hoje só o snapshot do dia fica em `data/raw`, e o `registry.parquet` versionado é a única foto antiga.

## 8. Extensões

Em ordem de valor para a mesa, como eu vejo:

1. **Decomposição diária do PL.** Resolve o resíduo inflado de fundos com fluxo grande no mês, como `54198519000155-TY3I61766775472` em fev/2026. É a menor das mudanças e usa só o dado que já existe.
2. **Cota ajustada por evento.** Precisa de uma fonte de amortizações e distribuições, que o informe não tem. Corrige o retorno e a posição entre pares dos incentivados.
3. **Carteiras (CDA da CVM)** para exposição por emissor e por setor. Teria dito qual emissor explica o 09/12/2024. A CDA é mensal: serve para exposição, não para o dia a dia.
4. **Benchmark ANBIMA completo com contrato**, com o índice do regulamento de cada fundo (IMA-B 5, IRF-M, IMA-S), no lugar da regra por classificação e do download dia a dia.
5. **Comparação entre gestoras.** O cadastro e o informe já cobrem o país, e os pares já leem 3.392 séries (rodada de 28/09/2026). Trocar o CNPJ da gestora por uma lista é pouco código; o custo é de leitura e armazenamento.
6. **Pares para Qualificado e Profissional**, com o mesmo método.
7. **Marcação a mercado das posições com curva de juros.** É o passo seguinte natural, e foi deixado de fora de propósito neste case. Não está construído.

## 9. Custo e equipe

Os dados são públicos e de graça. O custo está no tempo das pessoas e, se a ANBIMA for por contrato, na licença.

| Eu faria sozinho | Pediria à engenharia |
| --- | --- |
| Regras e fórmulas novas, com teste | Conta, permissões e buckets no S3 |
| Decomposição diária do PL e coletor da CDA | Orquestrador em produção, com deploy e segredos |
| Dicionário de dados e versão das fórmulas | API com cache e autenticação |
| Relatório diário de alertas novos | Painel de observabilidade e alerta no canal |
| Fluxos no Dagster rodando localmente | Plantão e acordo de nível de serviço |
| Calibrar limiares com a mesa | Contrato com a ANBIMA (com compras e jurídico) |

A divisão é: o que é regra de negócio e dado fica comigo; o que é infraestrutura compartilhada, segurança e plantão fica com quem mantém a infraestrutura da casa.

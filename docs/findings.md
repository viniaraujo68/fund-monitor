# Achados nos dados reais

O que o pipeline encontrou nos dados públicos. Rodada de referência: dados até **25/09/2026**, commit de dados `fe0458df453ab6aca6ad8e832b9f7c855e82cbfc`, com a regra nova de dia de mercado, o benchmark declarado e as tratativas de 29/09/2026. A Action diária fica pausada até a entrevista: site e documentos ficam nessa rodada, e as contagens abaixo são dela. Universo: 75 séries não exclusivas da Icatu Vanguarda (44 de Público Geral).

As regras, os limiares e os cortes estão em `docs/DECISIONS.md`; a página "Como funciona" do site resume os dois. Este arquivo não repete regra: aponta para a seção e registra só o que os dados mostraram.

De onde vêm os números:

- Alertas e contagens: `data/site/quality.json`, escrito pela etapa `publish` (`publish/site_json.py`) a partir de `data/parquet/metrics/quality_issues.parquet`, que a etapa `quality` grava (`quality/checks.py` e `quality/report.py`).
- Frações de dia de mercado: não são publicadas. A etapa `quality` as calcula em memória (`market_jump_share`, chamada em `quality/report.py`) e só grava a marca `market-wide` no alerta. Os números abaixo foram recalculados com essas funções sobre o Parquet desta rodada.
- Casos fora das séries monitoradas e contagens de linhas do informe: `data/parquet/daily/`.

## Resumo

| Regra | Severidade | Alertas | Leitura |
| --- | --- | --- | --- |
| Salto de cota isolado | média | 56 | Movimento fora do padrão do próprio fundo e **não** explicado pelo mercado |
| Salto de cota em dia de mercado | info | 51 | Salto num dia em que o índice mais correlacionado com o fundo também saiu do padrão no mesmo sentido, ou em que ≥ 10 % das séries do universo de pares na mesma classificação CVM saltaram |
| PL sem explicação | média | 21 | Variação mensal do PL que captação e rentabilidade não explicam (resíduo acima de 1 % do PL, em módulo) |
| Histórico curto | info | 14 | Série sem 12 meses: fora dos pares e sem % do CDI; continua na tabela e nos destaques de captação, com `*` |
| Informe duplicado | média | 4 | Mesma série e dia informados duas vezes, como `FI` e `CLASSES - FIF` |
| Dia sem informe | baixa | 1 | O dia que a linha zerada de 16/03/2026 deixa (item 5) |
| Valores zerados | alta | 1 | A linha zerada de 16/03/2026 |
| Fonte atrasada | média ou alta | 0 | Nesta rodada, nenhuma (item 8) |
| Cadastro divergente | média | 0 | Cadastro e informe da gestora batem |
| Cota repetida | média | 0 | |

Foram verificados **33.054 pares série × dia útil** em 75 séries.

Depois das tratativas de 29/09/2026 (`DECISIONS.md` §5.3): 148 alertas, **30 abertos** (todos médios: 28 saltos de cota e 2 PL sem explicação), 53 tratados (24 explicados, 6 erros da fonte, 23 limitações) e 65 informativos. Só 4 dos 30 abertos são dos últimos 30 dias. Na rodada de 26 a 28/09/2026, antes da regra nova do índice e das tratativas de 29/09, eram 69 abertos.

**Taxa de acerto do salto de cota** (107 alertas): 13 eram evento de crédito real (de mercado, com 13 séries da casa: o 09/12/2024, item 1); 62 eram mercado (51 reconhecidos pela regra e 11 dias de mercado global em fundos no exterior, confirmados pelo S&P 500 no FRED); 4 eram limitação do informe (pagamento mensal dos incentivados); 28 seguem sem leitura. Os 51 de mercado foram rotulados pela própria regra, então a precisão medida lendo um por um é sobre os 56 saltos médios: 13 evento de crédito, 11 mercado global, 4 limitação e 28 sem leitura. Três dias entre os abertos são dias de crédito no mercado, com fundos de crédito de várias gestoras caindo: 18/03/2026 (na casa, uma série só, o CDI IU `62571624000116`), 19/03/2026 (dia do Copom; CDI IU `62571624000116`, BB Debêntures Incentivadas CDI `63053090000107` e Infra Alocação Fundos 95 `63826355000154`) e 13/08/2026 (Absoluto FIFE `34081211000118` e as duas subclasses do Iporã PG, `35609382000130-A8AAW1750173152` e `35609382000130-ZN9EI1750172960`), a investigar com a carteira. **PL sem explicação** (21): 19 são limitação (distribuição como resgate e fluxo no meio do mês, com resíduo diário zero) e 2 seguem abertos.

**Benchmark declarado** (achado da revisão de 29/09/2026, `DECISIONS.md` §4.5): a manchete anterior, 6 de 36 séries de Público Geral acima do próprio benchmark em 12 meses, incluía a Inflação Curta FIC (`12682783000110`), com +0,47 p.p. sobre o IMA-B. Ela declara IMA-B 5 no cadastro, e contra o IMA-B 5 perde 1,12 p.p. Com o índice declarado, a manchete é **5 de 36**. A Inflação Curta `10922432000103` declara "OUTROS" e segue contra o IMA-B (+1,22 p.p.); contra o IMA-B 5 ela também perde (−0,38 p.p.), e a manchete seria 4 de 36.

Uma ressalva vale para as contagens: numa classe com duas subclasses, um fato anterior à divisão aparece como um alerta em cada subclasse (`DECISIONS.md` §5, "Linhas herdadas"). Os itens 1 e 4 dizem quantos fatos distintos há por trás de cada contagem.

## 1. Evento de crédito: 09/12/2024

**13 séries de crédito, de 10 CNPJs,** caíram no mesmo dia, entre −0,11 % e −0,53 %, em fundos cujo retorno médio nos 60 retornos anteriores era de +0,04 % ao dia: Absoluto FIFE, Absoluto Plus, Credit Plus, Credit Plus Master, Credit Plus VC, Crédito Privado, Crédito Privado Liquidez, Institucional IS, Iporã PG e Plus. Crédito Privado (`07900255000150`), Crédito Privado Liquidez (`44917374000141`) e Iporã PG (`35609382000130`) ainda não tinham subclasses: cada uma tinha uma cota só, que hoje aparece nas duas subclasses que a herdam. São 10 quedas distintas, não 13.

Não foi só a casa. No mesmo dia caíram fundos de crédito e de infraestrutura de outras gestoras: JGP Deb Incent Juros Reais (`41594333000173`) −1,50 %, Premium Institucional (`37780270000172`) −2,07 %, Tagus (`16599959000125`) −0,51 %, e ainda Régia (`53828295000155`), XP Corporate Top (`04621721000170`), Principal Claritas (`11447136000160`) e Itaú Active Fix (`17051205000107`). Nos fundos ANBIMA "Crédito Livre" de outras gestoras, 2,83 % saltaram nesse dia, o 10.º maior dia entre 459 (mediana 0,15 %). O feeder `32835611000146` (ICATU VANGUARDA CRÉDITO PRIVADO LONGO PRAZO IU FIF DA CIC, gestor Itaú no cadastro) caiu −0,21 % junto. Foi um dia de crédito no mercado, sem movimento de índice que explique: o Ibovespa e o IMA-B ficaram dentro do padrão. Leitura provável: remarcação de um emissor presente em várias carteiras, **a confirmar** com a carteira.

O que o caso mostra: a fração de pares por classificação CVM não enxergava crédito (só 2,3 % dos fundos de Renda Fixa do universo de pares saltaram, porque a classe é dominada por fundos DI), e o índice também não enxerga. Falta um índice de crédito, como o IDA da ANBIMA. É o tipo de coisa que o monitor deve mostrar e que a regra sem o piso e sem o dia de mercado escondia no meio de 127 alertas (`DECISIONS.md` §5.1).

## 2. Dias de mercado: 05/12/2025 e 13/03/2026

Em **05/12/2025**, 72 % dos fundos de ações, 32 % dos multimercados e 16 % dos de renda fixa do universo de pares tiveram salto. O Dividendos (`08279304000141-9WCV01767643284`) caiu −4,53 % e o IBX (`06224719000192`) −4,29 %; os 24 alertas do dia ficaram informativos. Em **13/03/2026**, 12 % da renda fixa do universo de pares saltou, e os 13 alertas do dia ficaram informativos.

## 3. Distribuição informada como resgate: Incentivado em Infraestrutura

`54023112000197` (1 cotista, R$ 49,4 mi): o informe traz **resgate de cerca de R$ 505 mil todo mês**, cerca de 1 % do PL, e nenhuma aplicação. O PL cai uma vez só, pela cota; o que não tem contrapartida no PL é o resgate informado. Nas 25 datas de pagamento, o resíduo diário é igual ao resgate informado, no centavo (em 06/12/2024: resgate de R$ 502.000,00, resíduo de R$ 501.999,99). O resíduo mensal da decomposição fica entre +0,97 % e +1,03 % em **todos os 24 meses**; 11 deles passam do limite de 1 %. A cota cai 3,1 % em dez/2024.

Leitura provável (**a confirmar**): pagamento de rendimentos ou amortização, que sai da cota **e** aparece como resgate. Dois efeitos:

- a decomposição do PL conta o pagamento duas vezes, e o alerta de PL é legítimo;
- o retorno pela cota subestima o que o cotista recebeu: o fundo aparece com −4,13 % em 12 meses e P4 entre 361 pares (`DECISIONS.md` §7, "Cota não ajustada por evento").

## 4. Duplicidade na passagem para a RCVM 175

No Parquet do informe da gestora, **72 linhas de 23 CNPJs** aparecem duas vezes no mesmo dia, uma como `FI` e outra como `CLASSES - FIF`, em 19 datas entre 15/10/2024 e 01/07/2025. Nas séries monitoradas, duas linhas de classe têm **cota, PL e resgates diferentes**, ambas em **24/04/2025**, antes da divisão em subclasses de 17/06/2025: Crédito Privado (`07900255000150`) e Crédito Privado Liquidez (`44917374000141`). Cada uma gera um alerta em cada subclasse que herda a cota, e daí os 4 alertas: `07900255000150-BQMVJ1750171627`, `07900255000150-FR33D1750172064`, `44917374000141-UYXKV1750167974` e `44917374000141-WJPUK1750168728`.

Fora das monitoradas: CNPJ `03537494000136` em 06/11/2024, com captação de R$ 9.082,08 numa linha e R$ 64.743,05 na outra.

## 5. Linha zerada: Incentivada de Investimento em Infraestrutura

`34793170000192-BNAX91750170440`, em **16/03/2026**: cota 0, PL 0 e 0 cotistas, entre dias com cerca de 1.470 cotistas e R$ 119 mi. A linha sai de todo o cálculo e aparece como alerta **alto**, junto com o dia sem informe que ela deixa.

## 6. Subclasses: história herdada e o caso que não herda

Oito classes da gestora passaram a informar por subclasse. Das 14 subclasses monitoradas, 13 começam a informar no dia útil seguinte ao último informe da classe e herdam a história de cota dela (ex.: `44917374000141-UYXKV1750167974` herda até 16/06/2025).

A exceção é `58327943000103-NANFG1779473395` (Dinâmico CDI IU). Ela nasceu em 12/08/2026 de uma subclasse irmã, três meses depois de a classe parar de publicar. Herdar a cota da classe criaria um "retorno diário" de +3,6 % que não existiu. A regra dos 7 dias impede (`DECISIONS.md` §4.1).

## 7. PL sem explicação em fundos novos ou com fluxo grande

- `67775604000180` (Credit Plus K, desde jul/2026): em set/2026, resgates de R$ 150,4 mi contra queda de PL de só R$ 9,9 mi. Em 14/09/2026 o informe traz resgate de R$ 139.758.102,45, e o PL passa de R$ 142.918.687,61 para R$ 142.956.492,31. Em 21/09/2026 o resgate de R$ 10,6 mi aparece no PL. Nenhum CNPJ da Icatu Vanguarda recebeu uma aplicação equivalente. Leitura: resgate informado sem contrapartida no PL, provável erro de envio; pergunta para o administrador. **Em aberto.**
- `54198519000155-TY3I61766775472` (Igaraté Long Biased IBOV), fev/2026: resíduo de 44 % do PL inicial. O PL passou de R$ 1,8 mi para R$ 42,5 mi com aplicação de R$ 39,9 mi no mês, e o dinheiro que entra no meio do mês rende só parte dele. É limitação da regra, não do dado (`DECISIONS.md` §7).

## 8. Fonte atrasada: portal da CVM fora do ar

Em 26 e 27/09/2026, sábado e domingo, `dados.cvm.gov.br` não respondeu nem por IPv4 nem por IPv6, enquanto Bacen e GitHub respondiam. A Action não roda no fim de semana; foi uma execução local. Quando o portal não responde, a coleta da CVM falha, a execução para e o site fica na última rodada boa. A regra 8 não pega esse caso: ela pega a fonte que responde com dado velho. O que ela marcou foi o informe que já estava em disco: numa execução local de 27/09, não publicada, a última data era 22/09/2026, 3 dias de semana de atraso contra a tolerância de 2. Tentar de novo e publicar com o alerta de fonte atrasada é próximo passo de produção (`PRODUCTION.md` §3). Na rodada de 28/09, com o portal de volta, não há alerta: as cinco fontes têm dado até 25/09/2026.

## 9. Classe em transição some do cadastro: Igaraté Long Biased

Entre 24 e 27/09/2026, a classe `35637151000130` (Igaraté Long Biased, Público Geral, R$ 600 mi) criou as subclasses `HGO9N1790345272` e `S8AUG1790345378`, ambas em **Fase Pré-Operacional** desde 25/09. O cadastro normalizado passou a ter só as linhas das subclasses, e o informe continuou publicando a cota da classe. Pela regra antiga, o fundo sumia do monitor: da coleta, do cálculo, dos pares e do PL agregado. Hoje ele é monitorado como a própria classe (`DECISIONS.md` §3.5).

## 10. Dia parcial no informe

No arquivo de setembro baixado em 28/09, o dia **25/09/2026 tinha só 8 das 246 classes** da gestora. Usar "última data com cota" como data de referência deixaria as outras séries com um falso dia sem informe e fundos terminando em dias diferentes. A data de referência ficou em 24/09/2026 (`DECISIONS.md` §4.1). Na rodada atual, com o dia completo, os dados vão até 25/09/2026.

## 11. Republicação do histórico

Em 27/09, a CVM regravou os 25 meses do informe (tamanho e Last-Modified mudaram em todos). Comparando o Parquet versionado da coleta de 24/09 (commit `6456e6376faaeed91c2937d68cddea9696778633`) com o de 28/09 (commit `78b3d30e5a630ebf0009b3eb172833915dc9b935`), nas datas até 22/09/2026: **17 linhas** mudaram, em 13 CNPJs, todas de 18 a 22/09/2026, sem nenhuma mudança de cota, captação ou resgate (PL em 12 linhas, patrimônio total em 8, cotistas em 2; a maior revisão de PL foi de R$ 27.650,62). Além delas, 9 linhas de 17/09/2026 que não estavam na coleta de 24/09 apareceram. O coletor baixa de novo quando o arquivo muda e refiltra o bruto a cada execução, então revisões desse tipo entram sozinhas.

## 12. Armadilhas das fontes

As armadilhas encontradas na coleta, com as contagens, estão em `DECISIONS.md` §2.1 a §2.6: cadastro com uma linha por gestor, classe repetida por custodiante ou controlador, aspas literais nos nomes das subclasses, `CNPJ_Classe` repetido, cadastro legado com tudo cancelado, séries do Bacen paradas, informe histórico só até 2020, republicação de meses antigos, feriado vazio na ANBIMA e fechamento do dia antes do fim do pregão na B3.

## 13. Achado da revisão: dias de mercado que a regra não reconhecia

Na revisão de 29/09/2026, o site dizia "queda isolada: fora do padrão da própria série e não compartilhada pelo mercado" em dias em que o mercado mexeu forte:

| Data | Mercado no dia | Séries marcadas como isoladas |
| --- | --- | --- |
| 18/12/2024 | Ibovespa −3,15 % (−3,30σ) | Data Alvo 2050 e 2060, Igaraté Long Biased, FIFE, FIC, Long Biased IBOV e Long Biased IMA B-5 |
| 04/04/2025 | Ibovespa −2,96 % (−2,96σ) | os cinco Igaraté |
| 13/03/2026 | IMA-B −1,21 % (−4,86σ) | Iporã PG Inflação, IPCA Dinâmico |
| 16/03/2026 | IMA-B +1,56 % (+5,12σ) | Inflação Longa, Inflação Longa FIC |

A causa estava na própria regra. O "dia de mercado" era medido pela fração de fundos da mesma classificação CVM que saltaram no dia, e o Multimercado e a Renda Fixa do universo de pares são dominados por fundos DI: um dia forte de bolsa ou de IMA-B quase nunca chegava a 10 % da classe. Na prática, a regra só reconhecia mercado em Ações.

O conserto foi olhar o índice que mais se parece com cada fundo. Se o Ibovespa ou o IMA-B, com correlação de pelo menos 0,5 nos 60 retornos anteriores, também saiu do padrão no mesmo dia e no mesmo sentido (acima de 2,5σ), o salto vira informativo. Os 16 alertas da tabela deixaram de ser isolados. O evento de crédito de 09/12/2024 continuou isolado nas 13 séries: nesse dia o Ibovespa subiu 1,00 % e o IMA-B caiu 0,24 %, ambos dentro do padrão. Não é que os fundos de crédito não se pareçam com os índices: o Plus (`05755769000133`) tem ρ 0,82 com o IMA-B e só continuou isolado porque o IMA-B andou −0,65σ no dia. O índice não vê crédito (item 1; `DECISIONS.md` §5.1).

Os fundos no exterior não têm índice coletado: os dias de mercado global deles (03/04/2025, 04/04/2025 e 09/04/2025, por exemplo) viraram tratativa à mão, com o movimento do mercado na nota.

A lição para a apresentação: uma regra que parecia certa nos 24 meses de calibração tinha um ponto cego que só apareceu quando alguém leu os alertas um por um. Ler os alertas é parte do trabalho, e a tratativa é o registro disso.

## Conferência externa

O IMA-B de 12 e 24 meses publicado nesta rodada bate nas 4 casas com a variação que a própria ANBIMA publica no arquivo de 24/09/2026 (`DECISIONS.md` §2.4).

Os casos dos itens 1, 3, 4, 5 e 7 e os dias de mercado global do item 13 estão registrados como tratativas em `data/triage.json` (`DECISIONS.md` §5.3).

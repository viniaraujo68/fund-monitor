# Achados nos dados reais

Primeira leitura dos problemas que o pipeline encontrou nos dados públicos. Rodada de referência: último dia completo do informe **24/09/2026**, índices até 25/09/2026, pipeline executado em 28/09/2026. Universo: 75 séries não exclusivas da Icatu Vanguarda (44 de Público Geral).

Os números vêm de `data/site/quality.json`, gerado pela etapa `quality` (`pipeline/src/fund_monitor/quality/checks.py`). Cada regra está descrita em `docs/DECISIONS.md` (a escrever).

## Resumo

| Regra | Severidade | Alertas | Leitura |
| --- | --- | --- | --- |
| Salto de cota isolado | média | 72 | Movimento fora do padrão do próprio fundo e **não** compartilhado pelo mercado |
| Salto de cota em dia de mercado | info | 35 | Salto em dia em que ≥ 10 % das séries do país na mesma classificação CVM também saltaram |
| PL sem explicação | média | 21 | Variação mensal do PL que captação + rentabilidade não explicam (resíduo > 1 % do PL) |
| Série com menos de 12 meses | info | 14 | Fora de rankings e pares |
| Duplicidade com valores diferentes | média | 4 | Mesma série e dia informados duas vezes, como `FI` e `CLASSES - FIF` |
| Fonte atrasada | média | 0 | Nesta rodada, nenhuma; na de 27/09 foram 4, com o portal da CVM fora do ar (ver abaixo) |
| Dia útil sem informe | baixa | 1 | A linha zerada de 16/03/2026 (item 5) |
| Cota, PL ou cotistas zerados | alta | 1 | |
| Divergência de cadastro | — | 0 | Cadastro e informe da gestora batem |

Foram verificados **32.979 pares série × dia útil**.

## 1. Evento de crédito da casa: 09/12/2024

**13 séries de crédito da Icatu** caíram no mesmo dia, entre −0,11 % e −0,53 %, em fundos cujo dia normal é +0,04 %: Absoluto FIFE, Absoluto Plus, Credit Plus, Credit Plus Master, Credit Plus VC, Crédito Privado (as duas subclasses), Crédito Privado Liquidez (as duas subclasses), Institucional IS, Iporã PG (as duas subclasses) e Plus.

No país, só 4,3 % dos fundos de Renda Fixa tiveram salto nesse dia. Não foi mercado: foi algo comum às carteiras da gestora, provavelmente a remarcação de um mesmo emissor. É exatamente o tipo de coisa que o monitor deve mostrar e que a regra "5σ, sem contexto" escondia no meio de 127 alertas.

## 2. Dias de mercado: 05/12/2025 e 13/03/2026

Em **05/12/2025**, 72 % dos fundos de ações do país, 32 % dos multimercados e 19 % dos de renda fixa tiveram salto de 5σ. O Dividendos (`08279304000141-9WCV01767643284`) caiu −4,53 % e o IBX (`06224719000192`) −4,29 %. Em **13/03/2026**, 13 % da renda fixa do país. Esses alertas ficam como **info**: são reais, mas explicados pelo mercado.

**Decisão tomada** (26/09/2026): salto compartilhado por ≥ 10 % das séries do país na mesma classificação CVM vira "info", e desvio menor que 0,1 % da cota não conta como salto. Sem isso, a regra gerava 127 alertas médios, 19 deles imateriais (fundo DI com desvio-padrão de 0,001 % ao dia).

## 3. Distribuição informada como resgate: Incentivado em Infraestrutura

`54023112000197` (1 cotista, R$ 49,4 mi): o informe traz **resgate de cerca de R$ 505 mil todo mês**, cerca de 1 % do PL, mas o PL não cai esse valor. O resíduo da decomposição fica entre +0,97 % e +1,03 % em **todos os 24 meses**; 11 deles passam do limite de 1 %. Ao mesmo tempo, a cota tem quedas como −3,1 % em dez/2024.

Leitura provável (**a confirmar**): pagamento de rendimentos ou amortização, que sai da cota **e** aparece como resgate. Dois efeitos:

- a decomposição do PL conta o pagamento duas vezes, e o alerta de PL é legítimo;
- o retorno pela cota subestima o que o cotista recebeu. É a limitação "o informe não tem cota ajustada por evento": o fundo aparece com −4,4 % em 12 meses e percentil 4 % entre os pares, provavelmente por isso.

## 4. Duplicidade no dia da migração para a RCVM 175

No bruto de 25 meses, **72 linhas de 23 CNPJs** aparecem duas vezes no mesmo dia, uma como `FI` (regime antigo) e outra como `CLASSES - FIF`. Nas séries monitoradas, 4 têm **cota, PL e resgates diferentes** entre as duas linhas, todas em **24/04/2025**:

- `07900255000150-BQMVJ1750171627` e `07900255000150-FR33D1750172064` (Crédito Privado)
- `44917374000141-UYXKV1750167974` e `44917374000141-WJPUK1750168728` (Crédito Privado Liquidez)

Fora das monitoradas: CNPJ `03537494000136` em 06/11/2024, com captação de R$ 9.082,08 numa linha e R$ 64.743,05 na outra.

**Regra aplicada**: vale a linha `CLASSES - FIF`; a divergência fica registrada.

## 5. Linha zerada: Incentivada de Investimento em Infraestrutura

`34793170000192-BNAX91750170440`, em **16/03/2026**: cota 0, PL 0 e 0 cotistas, no meio de uma série com cerca de 1.380 cotistas e R$ 120 mi. A linha é excluída do cálculo (cota ≤ 0 não gera retorno) e aparece como alerta **alto**, junto com o "dia útil sem informe" que ela deixa.

## 6. Subclasses: história herdada e o caso que não herda

Oito classes da gestora passaram a informar por subclasse. Em 13 das 14 passagens, a subclasse nasce com a mesma cota da classe no dia seguinte, e a série herda a cota da classe (ex.: `44917374000141-UYXKV1750167974` herda até 16/06/2025).

A exceção é `58327943000103-NANFG1779473395` (Dinâmico CDI IU). Ela nasceu em 12/08/2026 de uma subclasse irmã, três meses depois de a classe parar de publicar. Herdar a cota da classe criaria um "retorno diário" de +3,6 % que não existiu. **Regra**: só herda se a classe publicou cota nos 7 dias anteriores.

## 7. PL sem explicação em fundos novos ou com fluxo grande

- `67775604000180` (Credit Plus K, desde jul/2026): em set/2026, resgates de R$ 150,4 mi contra queda de PL de só R$ 10 mi. O resgate pode ter sido compensado por uma aplicação que não aparece como captação (movimento entre veículos). **A investigar.**
- `54198519000155-TY3I61766775472` (Igaraté Long Biased IBOV), fev/2026: resíduo de 44 % do PL inicial. É efeito de base: o PL passou de R$ 1,8 mi para R$ 42,5 mi com aplicação de R$ 39,9 mi no mês, e o dinheiro que entra no meio do mês rende só parte dele. **Limitação da regra**, não do dado: medir o resíduo contra o PL do início do mês exagera quando o fluxo é grande perto do PL.

## 8. Fonte atrasada: portal da CVM fora do ar

Em 26 e 27/09/2026, `dados.cvm.gov.br` não respondeu nem por IPv4 nem por IPv6, enquanto Bacen e GitHub respondiam. Na rodada de 27/09, a última data do informe estava em 22/09/2026, 3 dias úteis de atraso contra a tolerância de 2, e a regra 8 marcou isso (os índices também, com 2 dias, porque não houve coleta nova). Na rodada de 28/09, com o portal de volta, o alerta sumiu.

## 9. Classe em transição some do cadastro: Igaraté Long Biased

Entre 24 e 27/09/2026, a classe `35637151000130` (Igaraté Long Biased, Público Geral, R$ 600 mi) criou as subclasses `HGO9N1790345272` e `S8AUG1790345378`, ambas em **Fase Pré-Operacional** desde 25/09. O cadastro deixou de ter a linha da classe, e o informe continuou publicando a cota da classe. Pela regra antiga, o fundo sumia do monitor: da coleta, do cálculo, dos pares e do PL agregado.

**Regra aplicada** (28/09/2026): classe ativa sem nenhuma subclasse operacional é monitorada como a própria classe; exclusividade e público-alvo vêm do consenso das subclasses. Quando as subclasses começarem a informar, elas herdam a cota da classe, e o identificador da série muda.

## 10. Dia parcial no informe

No arquivo de setembro baixado em 28/09, o dia **25/09/2026 tinha só 8 das 246 classes** da gestora. Usar "última data com cota" como data de referência deixava as outras 74 séries com um falso "dia útil sem informe" e fundos terminando em dias diferentes. **Regra**: a data de referência é o último dia em que pelo menos 90 % das séries informaram, comparando com o dia de maior cobertura entre os 20 últimos. Linhas posteriores ficam de fora até o dia completar.

## 11. Republicação do histórico

Em 27/09, a CVM regravou os 25 meses do informe (tamanho e Last-Modified mudaram em todos). Comparando com a coleta de 24/09, só **13 linhas** mudaram nas séries da gestora, todas de 18 a 22/09/2026. São revisões de PL de centavos a alguns milhares de reais, com a cota inalterada. O coletor baixa de novo só quando o arquivo muda e refiltra o bruto a cada execução, então revisões desse tipo entram sozinhas.

## 12. Armadilhas das fontes (encontradas na coleta)

- `cad_fi.csv` é o cadastro legado: todas as 59 classes da gestora aparecem como canceladas. O cadastro certo é `registro_fundo_classe.zip`.
- `registro_fundo.csv` tem uma linha por **gestor**. São 1.042 fundos em cogestão; um da Icatu, o FII GRU Logístico, cogerido com a DOJO Capital.
- `registro_classe.csv` repete a classe por custodiante (8 linhas).
- `registro_subclasse.csv` tem aspas literais nos nomes (`SUBCLASSE "A"`), então não dá para ler o CSV com aspas como delimitador.
- `CNPJ_Classe` não é único no país: 16 repetidos entre classes ativas.
- Série SGS 7 do Bacen (Ibovespa) parou em 30/09/2019; série 12466 (IMA-B) parou em maio/2023. Ibovespa vem da B3; IMA-B, da ANBIMA.
- O informe histórico anual (`HIST/`) só vai até 2020; de 2021 em diante é mensal e republicado.
- A B3 publica o fechamento do dia antes do fim do pregão; o coletor descarta a data corrente.

## Conferência externa

O IMA-B de 12 e 24 meses calculado pelo motor (13,0158 % e 19,7719 %) bate nas 4 casas decimais com a variação publicada pela ANBIMA para 22/09/2026.

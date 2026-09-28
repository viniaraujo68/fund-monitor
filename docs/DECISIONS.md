# Decisões e metodologia

Este documento explica o que o fund-monitor calcula, de onde vêm os dados e por que cada corte foi feito. Os números citados são da rodada de 28/09/2026, com dados até **24/09/2026** (último dia completo do informe diário). A fonte da verdade é o código em `pipeline/src/fund_monitor/`; cada limiar citado aqui é uma constante com nome nesse código.

## 1. O que é o projeto

Um monitor diário dos fundos geridos pela **Icatu Vanguarda Gestão de Recursos Ltda.** (CNPJ `68622174000120`), feito só com dados públicos da CVM, do Bacen, da ANBIMA e da B3.

Ele responde a três perguntas:

1. **Como cada fundo rendeu** contra o seu benchmark e contra os seus pares?
2. **Para onde o dinheiro está indo?** Captação líquida por fundo e por classificação.
3. **Em que dado não dá para confiar?** Nove regras de qualidade, com alerta por fundo e por dia.

O fluxo tem quatro etapas: coleta → cálculo → qualidade → publicação. O pipeline em Python grava Parquet e depois JSON; o site é estático e só lê o JSON. Uma GitHub Action roda tudo de segunda a sexta, às 20h de Brasília.

Convenções que valem para o documento inteiro:

- **Dia útil** é dia com CDI publicado pelo Bacen (série 12 do SGS). É esse calendário que conta dias para anualizar e para saber se faltou informe.
- **Anualização em 252** dias úteis, a convenção do mercado brasileiro.
- **Cota e dinheiro** entram como `Decimal` (a cota tem 12 casas na CVM). O cálculo usa ponto flutuante e arredonda na saída: 6 casas para retornos, 4 para razões (Sharpe, % do CDI, percentil), 2 para dinheiro.
- No JSON, percentuais são frações: `0,1444` = 14,44 %.

## 2. Fontes

| Fonte | Endereço | Formato | Frequência | Uso |
| --- | --- | --- | --- | --- |
| Cadastro CVM (RCVM 175) | `https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip` | ZIP com 3 CSV, Latin-1, `;` | Baixado uma vez por dia de execução | Quem é da gestora, classificação, público, exclusividade, benchmark declarado |
| Informe diário CVM | `https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_AAAAMM.zip` | ZIP mensal com 1 CSV, Latin-1, `;`, ponto decimal | Dado diário, arquivo mensal, republicado | Cota, PL, captação, resgate, cotistas |
| Bacen SGS | `https://api.bcb.gov.br/dados/serie/bcdata.sgs.{id}/dados?formato=json` | JSON, datas e valores como texto | Diário (CDI) | CDI como benchmark e taxa livre de risco |
| ANBIMA IMA | `POST https://www.anbima.com.br/informacoes/ima/ima-sh-down.asp` | CSV, Latin-1, `;`, vírgula decimal | Um arquivo por dia útil | IMA-B |
| B3 Ibovespa | `GET https://sistemaswebb3-listados.b3.com.br/indexStatisticsProxy/IndexCall/GetPortfolioDay/{base64}` | JSON, números em texto pt-BR | Um arquivo por ano | Ibovespa |

A janela coletada começa em **01/09/2024** (`WINDOW_START`), o que dá 24 meses até setembro de 2026, para a gestora e para os pares.

### 2.1 Cadastro CVM

- Três arquivos: `registro_fundo.csv` (90.307 linhas), `registro_classe.csv` (36.766) e `registro_subclasse.csv` (10.028), contados em 23/09/2026.
- A gestora é filtrada por `CPF_CNPJ_Gestor = 68622174000120`. Por CNPJ, e não por nome, porque o CNPJ é exato.
- O CNPJ que liga cadastro e informe é `registro_classe.CNPJ_Classe`.

Armadilhas verificadas em 24/09/2026:

- `registro_fundo.csv` tem **uma linha por gestor**. São 1.042 fundos em cogestão no país; um é da gestora (o FII GRU Logístico, com a DOJO Capital). Os gestores viram uma lista por fundo antes do join.
- `registro_classe.csv` repete a classe por custodiante e controlador (8 linhas). Essas colunas são descartadas e a linha é deduplicada.
- `registro_subclasse.csv` tem aspas literais nos nomes (`SUBCLASSE "A"`). O CSV é lido sem caractere de aspas.
- `CNPJ_Classe` não é único no país: 16 repetidos entre classes ativas. A chave do cadastro normalizado é `(ID_Registro_Classe, ID_Subclasse)`.
- Em 27/09/2026 uma classe em transição sumiu do cadastro (ver 3.5).

### 2.2 Informe diário CVM

- Colunas usadas: `TP_FUNDO_CLASSE`, `CNPJ_FUNDO_CLASSE`, `ID_SUBCLASSE`, `DT_COMPTC`, `VL_TOTAL`, `VL_QUOTA`, `VL_PATRIM_LIQ`, `CAPTC_DIA`, `RESG_DIA`, `NR_COTST`. Se o cabeçalho mudar, a coleta para com erro.
- O arquivo é lido em streaming e filtrado pelos CNPJs da gestora e dos pares **na leitura**. Sem isso, 24 meses do país ocupam gigabytes. Dos pares, só cota e PL são guardados.
- O CNPJ vem com máscara (`00.017.024/0001-53`) e é normalizado para 14 dígitos antes de qualquer join.

Armadilhas:

- Confirmado em 24/09/2026: todo mês desde jan/2021 está em `DADOS/`; `HIST/` só tem arquivos anuais até 2020.
- A CVM **republica meses antigos**. O de 202409 tinha Last-Modified de 30/08/2025. Em 27/09/2026 ela regravou os 25 meses; só 13 linhas mudaram nas séries da gestora, todas de 18 a 22/09/2026, com revisões de PL e a cota inalterada. Por isso o coletor pergunta tamanho e Last-Modified antes de baixar e refiltra o bruto a cada execução.
- No dia da migração para a RCVM 175, 72 linhas de 23 CNPJs aparecem duas vezes: uma como `FI` e outra como `CLASSES - FIF` (ver 4.1).
- O último dia do arquivo pode estar incompleto: em 28/09/2026, o dia 25/09/2026 tinha só 8 das 246 classes da gestora (ver 4.1).
- Em 26 e 27/09/2026 o portal `dados.cvm.gov.br` não respondeu. A regra 8 marcou o atraso (ver 5).

### 2.3 Bacen SGS

- Séries coletadas: 12 (CDI diário), 11 (Selic diária), 433 (IPCA mensal) e 189 (IGP-M mensal). **Só o CDI entra no cálculo** nesta versão.
- O CDI vem em percentual ao dia: `0,050788` significa 0,050788 % no dia. Fator diário = `1 + valor / 100`.
- A taxa publicada para o dia d rende de d até o dia útil seguinte. No código, o nível do CDI acumulado do dia d entra na data d + 1.
- A API aceita até 10 anos por chamada; a janela inteira cabe numa só.

### 2.4 ANBIMA IMA

- Um POST por dia útil, sem login, com a data no corpo do formulário. São cerca de 500 chamadas para 24 meses, com pausa de 1 s entre elas.
- Cada arquivo baixado fica gravado e não é pedido de novo. A exceção é um dia recente (até 7 dias) que veio vazio: esse é pedido outra vez.
- Linhas guardadas: IMA-B, IMA-B 5, IMA-B 5+, IRF-M, IMA-S e IMA-GERAL. **Só o IMA-B entra no cálculo.**
- Histórico confirmado em 24/09/2026: a linha do IMA-B vem preenchida desde pelo menos 03/01/2022. A janela de 24 meses cabe inteira.
- Fim de semana devolve um arquivo de 46 bytes, sem dados. Linha com data diferente da pedida é descartada.
- Conferência externa: o IMA-B de 12 e 24 meses calculado pelo motor (13,0158 % e 19,7719 %) bate nas 4 casas com a variação publicada pela ANBIMA para 22/09/2026.

### 2.5 B3 Ibovespa

- Uma chamada por ano, com `{"index":"IBOV","language":"pt-br","year":"AAAA"}` em base64 no caminho. A resposta tem uma linha por dia do mês e uma coluna por mês (`rateValue1` a `rateValue12`), com o fechamento em texto (`"183.965,91"`).
- Cobertura verificada em 24/09/2026: 2024 com 251 pregões; 2026 com 183 pregões até 24/09.
- Armadilha: **o valor do dia corrente aparece antes do fechamento**. O coletor descarta a data de execução e fica só com dias encerrados.
- O ano corrente é baixado de novo a cada execução.

### 2.6 O que foi descartado

| Fonte | Motivo |
| --- | --- |
| `cad_fi.csv` (cadastro legado) | Só tem 22 fundos "EM FUNCIONAMENTO NORMAL" no país; os 59 da gestora aparecem como cancelados. O cadastro certo é `registro_fundo_classe.zip`. |
| SGS 12466 (IMA-B no Bacen) | Parou em maio/2023. O IMA-B vem da ANBIMA. |
| SGS 7 (Ibovespa no Bacen) | Parou em 30/09/2019 (verificado em 24/09/2026). O Ibovespa vem da B3. |
| Curva zero da ANBIMA (ETTJ) | Sem login, só os últimos 5 dias úteis. E o monitor não precifica títulos. |
| Focus (Bacen) | Expectativa de mercado não entra em nenhum indicador do monitor. |
| Taxas referenciais da B3 | Deu timeout no teste e não é necessária. |

## 3. Universo

### 3.1 Os cortes, em números

| Etapa | Fica | Sai | Por quê |
| --- | --- | --- | --- |
| Classes da gestora em funcionamento normal | 248 classes | Canceladas e pré-operacionais | Só o que está operando hoje |
| Só classes FIF | 246 classes | 2 FII | FII não entrega informe diário |
| Em séries de cota | 253 séries | Subclasses pré-operacionais | 8 classes informam por subclasse (ver 3.5) |
| Sem exclusivos | **75 séries** em 69 classes | 178 séries exclusivas | Ver 3.2 |
| Público Geral | **44 séries** em 38 classes | 18 Profissional e 13 Qualificado ficam no filtro | Ver 3.3 |
| Sem veículo estrutural (padrão do site) | 43 séries | Veículo Especial Bancário | Ver 3.4 |

As 75 séries monitoradas são 45 de Renda Fixa, 24 Multimercado e 6 de Ações. As 44 de Público Geral são 25, 15 e 4.

### 3.2 Por que só não exclusivos

Decidido em 24/09/2026.

- Fundo exclusivo tem um cotista só. A captação e o resgate são decisão desse cliente, não reflexo da gestão.
- Não tem par: é um produto sob medida.
- Distorce qualquer agregado. Em 24/09/2026, as séries exclusivas somam R$ 66,2 bi dos R$ 93,3 bi da gestora, 71 % do PL.
- O interruptor "Incluir exclusivos" existe, mas só muda os números "Da gestora" e o gráfico de captação por classificação. Tabela, rankings e pares nunca incluem exclusivos.

### 3.3 Por que Público Geral em destaque

- É o produto de prateleira, que qualquer investidor pode comprar. É onde o desempenho da gestora fica exposto à comparação.
- É o público com pares suficientes no mercado. Os pares só foram calculados para ele (ver 4.6).
- Profissional e Qualificado continuam no site, pelo filtro de público.

### 3.4 Veículo estrutural

Decidido em 28/09/2026.

- É uma classe cujo nome tem "VEÍCULO ESPECIAL" ou "FIFE" (`publish/names.py`). São estruturas que atendem outros veículos, não produtos de varejo.
- Das 75 séries monitoradas, 11 são estruturais. Em Público Geral só uma: o Veículo Especial Bancário (`64203379000110`), com R$ 6,5 bi, 36 % do PL de Público Geral.
- Ele começou a informar em 06/01/2026 e captou R$ 6,0 bi em 12 meses. Sozinho, dominaria o tile de captação.
- Por isso fica fora por padrão, com o interruptor "Incluir veículos estruturais". Na tabela, a série leva a marca "estrutural".

### 3.5 Unidade de análise: série de cota

Decidido em 24/09/2026.

- A unidade é a **série de cota** `(CNPJ_Classe, ID_Subclasse)`, com subclasse nula quando a classe não tem subclasse.
- O identificador (`series_id`) é o CNPJ, ou `CNPJ-ID_SUBCLASSE` quando há subclasse. Exemplo: `44917374000141-UYXKV1750167974`.
- **Por quê:** 8 classes da gestora publicam a cota por subclasse. Duas subclasses do mesmo CNPJ têm duas cotas no mesmo dia. Uma chave só por CNPJ misturaria as duas.
- Nessas classes, `Exclusivo`, `Publico_Alvo` e `Forma_Condominio` vêm vazios na classe e preenchidos na subclasse. Esses três campos vêm da subclasse quando ela existe. Classificação CVM, classificação ANBIMA e `Indicador_Desempenho` vêm da classe.
- **Classe sem subclasse operacional** (28/09/2026): é monitorada como a própria classe. Exclusividade e público vêm do consenso das subclasses. Caso real: entre 24 e 27/09/2026, a classe `35637151000130` (Igaraté Long Biased, Público Geral, R$ 600 mi) criou as subclasses `HGO9N1790345272` e `S8AUG1790345378`, ambas pré-operacionais desde 25/09/2026. O cadastro deixou de ter a linha da classe, mas o informe continuou publicando a cota da classe. Sem a regra, o fundo sumia do monitor. Quando as subclasses começarem a informar, elas herdam a cota da classe e o `series_id` muda.

### 3.6 FII fora

Decidido em 24/09/2026. O filtro é `Tipo_Classe = "Classes de Cotas de Fundos FIF"`. FII não entrega informe diário. Eram as 2 classes "sem classificação" da contagem original.

## 4. Indicadores

### 4.1 Montagem da série de cota

**Dia de referência.** É o último dia em que pelo menos 90 % das séries informaram cota, comparando com o dia de maior cobertura entre os 20 últimos dias com informe. Linhas posteriores ficam de fora até o dia completar. Por quê: em 28/09/2026, o dia 25/09/2026 tinha só 8 das 246 classes. Usar "a última data com cota" criaria um falso "dia sem informe" para as outras séries e faria cada fundo terminar num dia diferente.

**FI × CLASSES - FIF** (24/09/2026). Quando a mesma série tem uma linha `FI` e outra `CLASSES - FIF` no mesmo dia, vale `CLASSES - FIF`, que é o regime atual. A divergência vira alerta da regra 7. Por quê: 72 linhas de 23 CNPJs vêm duplicadas no dia da migração, e em alguns casos com cota e captação diferentes.

**Herança de cota da subclasse** (24/09/2026).

- Quando a classe cria subclasses, cada subclasse nasce com a mesma cota da classe. Antes disso, a história está na linha sem subclasse.
- A série da subclasse herda **só a cota** das linhas da classe anteriores ao seu primeiro dia. Exemplo: `44917374000141-UYXKV1750167974` herda a cota até 16/06/2025. O site avisa no cadastro do fundo.
- PL, captação e cotistas **não** são herdados: usam só as linhas da própria série. Herdar a linha inteira contaria o PL em dobro nas classes com duas subclasses não exclusivas. A janela de captação fica marcada como parcial.
- Os agregados da gestora somam as linhas cruas sem dupla contagem: a linha da classe antes da divisão, as subclasses depois.
- **Regra dos 7 dias:** a herança só vale se a classe publicou cota nos 7 dias corridos antes da primeira cota da subclasse. Caso real: `58327943000103-NANFG1779473395` (Dinâmico CDI IU) nasceu em 12/08/2026 de uma subclasse irmã, três meses depois de a classe parar de publicar. Herdar a cota da classe criaria um "retorno diário" de +3,6 % que não existiu. Das 14 passagens de classe para subclasse, 13 herdam.

**Cota inválida.** Linha com cota ≤ 0 não entra na série: não gera retorno. É a única linha que o cálculo descarta (ver regra 5).

### 4.2 Retornos

**Retorno diário.** `r_t = cota_t / cota_(t-1) − 1`, entre dois informes seguidos da série.

- Sem ajuste por come-cotas: o come-cotas reduz a quantidade de cotas do cotista, não o valor da cota.
- A cota do informe já é líquida da taxa de administração.

**Retorno acumulado.** `R = cota_fim / cota_base − 1`, que é o mesmo que `∏(1 + r_t) − 1`. A cota base é a última cota até a data-âncora da janela.

**Janelas.**

| Janela | Data-âncora |
| --- | --- |
| No mês | Último dia do mês anterior |
| No ano | 31/12 do ano anterior |
| 3, 6, 12 e 24 meses | Mesma data, N meses antes do dia de referência |
| Desde o início | Primeira cota da série **no período coletado** (desde 02/09/2024), não a data de criação do fundo |

Se a série começou depois da âncora, a janela fica vazia ("sem histórico"). O número de dias úteis `n` de cada janela é o número de dias de CDI entre a base e o fim.

**Retorno anualizado.** `(1 + R)^(252 / n) − 1`. Só para as janelas de 12 e 24 meses, e para "desde o início" com `n ≥ 252`. Por quê: anualizar uma janela curta multiplica o ruído. Um mês bom vira uma taxa anual que ninguém recebeu.

**Benchmark no período.**

- CDI: `∏(1 + CDI_d / 100) − 1` sobre os dias de CDI entre a base e o fim.
- IMA-B: número-índice no fim / número-índice na base − 1.
- Ibovespa: pontos no fim / pontos na base − 1.
- Em cada data vale o último nível publicado, com tolerância de 7 dias.

**% do CDI.** `R_fundo / R_CDI` no mesmo período. É a razão dos retornos acumulados, não das taxas anualizadas. Só é calculado com CDI positivo e janela de 12 meses ou mais. Por quê: em janela curta ou com CDI perto de zero, a razão explode. Com retorno negativo, o % do CDI fica negativo: `54023112000197` tem −30,09 % do CDI em 12 meses.

**Excesso de retorno.** `R_fundo − R_benchmark`, diferença simples dos acumulados no período. É calculado contra CDI, IMA-B e Ibovespa; o site mostra o excesso sobre o CDI.

**Janela móvel de 12 meses.** É calculada e publicada no JSON (`rolling_12m`), mas o gráfico ficou fora desta versão (corte de 28/09/2026).

### 4.3 Risco

Os indicadores de risco usam as janelas de 12 e 24 meses: os retornos diários com data depois da base e até o fim.

**Volatilidade.** `desvio-padrão amostral(r_t) × √252`.

- Amostral (divide por n − 1) porque 12 meses de retornos são uma amostra, não a população.
- `√252` leva o desvio diário para a escala anual, supondo retornos diários independentes.
- **Mínimo de 60 observações.** Abaixo disso, vol, Sharpe, beta, tracking error e as métricas auxiliares ficam vazios. Com menos de três meses de dias úteis, o desvio-padrão ainda é instável.

**Drawdown.** `DD_t = cota_t / max(cota_s, s ≤ t) − 1`, com o máximo contado a partir da base da janela.

- Drawdown máximo = o menor `DD_t` da janela.
- Pico: último dia com a cota máxima antes do vale. Vale: dia do drawdown máximo. Recuperação: primeiro dia depois do vale em que a cota volta ao pico. Se não voltou, "sem recuperação".
- Se a cota nunca ficou abaixo da máxima, drawdown zero e "sem queda".

**Sharpe (ex-post).** `(R_anual_fundo − R_anual_CDI) / volatilidade`, em 12 e 24 meses.

- É um Sharpe com o **CDI como taxa livre de risco**. O CDI é o que o investidor brasileiro ganha sem risco de mercado, e é o que um fundo DI entrega.
- Leitura: quanto de retorno acima do CDI o fundo entregou por unidade de oscilação.
- Cuidado: em fundo de volatilidade muito baixa, uma diferença pequena contra o CDI vira um Sharpe grande em módulo.

**Beta e tracking error.** Só contra o benchmark de mercado da série: IMA-B para Renda Fixa, Ibovespa para Ações. Multimercado não tem.

- `beta = cov(r_fundo, r_bench) / var(r_bench)`, com os retornos do benchmark medidos entre as mesmas datas dos informes do fundo.
- `tracking error = desvio-padrão amostral(r_fundo − r_bench) × √252`.
- Mínimo de 60 observações, como a volatilidade.
- **Nunca para série "DI de um dia"** (decidido em 28/09/2026). 24 das 45 séries de Renda Fixa declaram "DI de um dia" como indicador de desempenho. Um fundo DI não tenta seguir o IMA-B; o beta dele contra o IMA-B pareceria informação e seria ruído. Foi escolhida a versão mais simples por prazo, em vez de um mapa de benchmark por fundo.

**Métricas auxiliares.** Fração de dias positivos, melhor dia e pior dia, com a data de cada um.

### 4.4 Fluxos e tamanho

**Captação líquida.** Diária: `CAPTC_DIA − RESG_DIA`. Mensal: soma dos dias do mês. Em 12 meses: soma dos dias depois de (dia de referência − 12 meses). Usa só as linhas da própria série. Quando a série começou depois do início da janela, a captação é marcada como parcial (`*` na tabela).

**PL.** Último `VL_PATRIM_LIQ` da série até o dia de referência.

**Decomposição do PL.** Para cada mês:

```
resíduo = PL_fim − PL_início − captação_líquida − PL_início × r_mês
```

- `PL_início` é o PL do último informe do mês anterior. `r_mês` é a cota no fim do mês sobre a cota no fim do mês anterior, menos 1.
- O resíduo é publicado como fração de `PL_início`.
- Por quê: o PL só deveria mudar por dinheiro que entra ou sai e pela rentabilidade. O que sobra aponta dado errado ou evento que o informe não descreve. Acima de 1 %, vira alerta da regra 4.
- Supõe que todo fluxo acontece no fim do mês (ver limitação em 7).

**Cotistas.** Último `NR_COTST` da série, e o número no fim de cada mês na tabela de captação. A variação em 12 meses é calculada no pipeline, mas não é publicada no site nesta versão.

**Agregados da gestora.** PL total (soma do último PL de cada classe), captação em 12 meses e captação mensal por classificação CVM e ANBIMA, em dois escopos:

| Escopo | Classes | PL em 24/09/2026 | Captação em 12 meses |
| --- | --- | --- | --- |
| Não exclusivas | 69 | R$ 27,1 bi | R$ 9,2 bi |
| Toda a gestora | 246 | R$ 93,3 bi | R$ 13,5 bi |

### 4.5 Benchmark por série

| Classificação CVM | Comparado com | Benchmark de mercado (beta e tracking error) |
| --- | --- | --- |
| Renda Fixa | CDI e IMA-B | IMA-B |
| Multimercado | CDI | — |
| Ações | CDI e Ibovespa | Ibovespa |
| Qualquer uma com `Indicador_Desempenho` = "DI de um dia" | CDI | — |

- A regra é por classificação porque o `Indicador_Desempenho` do cadastro não é uniforme. Nas 75 séries: 32 "DI de um dia", 15 "OUTROS", 14 "Não se aplica", 4 IPCA, 4 IMA-B 5, 3 IBrX, e um cada de IMA-B 5+, IMA-B e IRF-M.
- A exceção DI é a versão mínima da decisão de 28/09/2026 (ver 4.3). Ela afeta 24 séries de Renda Fixa e 8 Multimercado; nestas últimas nada muda, porque Multimercado já é comparado só com o CDI.
- O cadastro do fundo no site mostra o indicador declarado e, ao lado, com o que ele está sendo comparado.

### 4.6 Pares

Implementado em 26–28/09/2026.

**Grupo.** Todas as séries **do país** com a mesma `Classificacao_Anbima` e o mesmo `Publico_Alvo` do fundo, não exclusivas, em funcionamento normal.

**Só Público Geral.** Por custo de leitura, os pares foram calculados só para as séries de Público Geral: **3.392 séries candidatas** (3.291 classes em 13 classificações ANBIMA).

**Elegibilidade de um par.**

- Retorno de 12 meses calculado, ou seja, pelo menos 12 meses de informe.
- Volatilidade e drawdown de 12 meses calculados (pelo menos 60 observações).
- PL acima de R$ 50 milhões. Por quê: tira fundos pequenos demais para serem alternativa real e mais sujeitos a cota ruidosa (fundo começando ou encerrando).
- Resultado: **1.653 elegíveis**. Saíram 387 sem 12 meses e 1.352 com PL até R$ 50 milhões.

**O fundo avaliado.**

- A própria classe e as subclasses irmãs (mesmo CNPJ) ficam fora do grupo: o fundo não é par de si mesmo.
- O limite de PL vale para os pares, não para o fundo avaliado. `54023112000197`, com R$ 49,4 mi, tem posição entre 363 pares.
- O percentil só é publicado com **pelo menos 5 pares**.
- 36 das 44 séries de Público Geral têm posição; as outras 8 ainda não têm 12 meses de série.

**Percentil.**

```
percentil = (pares com valor abaixo + ½ × pares com valor igual) / número de pares
```

- Empate conta pela metade para não favorecer nem penalizar o fundo.
- É calculado para retorno, volatilidade e drawdown máximo de 12 meses. Os quartis dos pares (P25, mediana, P75) são publicados com interpolação linear.
- Leitura: no retorno, percentil alto é ter rendido mais que a maioria. Na volatilidade, percentil alto é ter oscilado mais. No drawdown, que é negativo, percentil alto é ter caído menos.

Os pares usam 24 meses de informe (18 MB de Parquet, 7 s de leitura).

## 5. Regras de qualidade

**Princípio: marcar, não excluir.** Um alerta não tira o dado do cálculo. Ele aparece na página do fundo, na página Qualidade e na contagem do topo do site. Há três exceções, todas explícitas:

- a linha com cota ≤ 0 não entra na série de cota (regra 5);
- na duplicidade, vale a linha `CLASSES - FIF` (regra 7);
- a série sem 12 meses fica fora dos pares (regra 6).

**Severidades.** Alta: dado claramente errado. Média: pede investigação. Baixa: falha pequena. Informativo: real, mas explicado.

| # | Regra (código) | O que detecta | Limiar no código | Severidade | O que fazer |
| --- | --- | --- | --- | --- | --- |
| 1 | Dia sem informe (`missing_report`) | Dia útil, depois da primeira cota da série, sem cota da série. Dias seguidos viram um alerta só. | Qualquer dia | Média com 5 ou mais dias úteis seguidos; baixa com menos | Ver se o fundo suspendeu a cota. O retorno do informe seguinte cobre os dias que faltaram. |
| 2 | Salto de cota (`quota_jump`) | Retorno diário fora do padrão do próprio fundo | `abs(r_t − média) > 5 × desvio-padrão` dos 60 retornos anteriores **e** desvio ≥ 0,1 %; ou fundo de Renda Fixa com `abs(r_t) > 3 %` | Média; informativo se for dia de mercado | Procurar evento de crédito ou remarcação. Comparar com fundos irmãos no mesmo dia. |
| 3 | Cota repetida (`repeated_quota`) | Mesma cota em informes seguidos | 3 ou mais informes | Média | Fundo parado ou dado congelado. Perguntar ao administrador. |
| 4 | PL sem explicação (`unexplained_net_assets`) | Variação mensal do PL que captação e rentabilidade não explicam | `abs(resíduo) > 1 %` do PL do início do mês | Média | Procurar amortização, distribuição, incorporação ou fluxo entre veículos. |
| 5 | Valores zerados (`zero_values`) | Linha publicada com cota, PL ou cotistas zerados | cota ≤ 0, PL ≤ 0 ou 0 cotistas | Alta | Tratar como erro de envio. A linha com cota ≤ 0 sai do cálculo. |
| 6 | Histórico curto (`short_history`) | Série sem retorno de 12 meses | Janela de 12 meses vazia | Informativo | Fica fora dos pares. Na tabela, os indicadores de 12 meses aparecem com traço. |
| 7 | Informe duplicado (`duplicate_report`) | Mesma série e dia em mais de uma linha, com valores diferentes | Qualquer diferença em cota, PL, patrimônio total, captação, resgate ou cotistas | Média | Vale `CLASSES - FIF`. O alerta guarda quais campos divergiram. |
| 8 | Fonte atrasada (`stale_source`) | Última data da fonte longe do último dia de semana antes da execução | Tolerância em dias de semana: informe CVM 2; CDI, IMA-B e Ibovespa 1 | Média acima da tolerância; alta acima da tolerância + 3 ou sem nenhuma data | Não confiar no dia: os números são de antes. Ver se o portal está no ar. |
| 9 | Cadastro divergente (`registry_mismatch`) | Série no informe (CNPJs da gestora) que não está no cadastro, ou série monitorada do cadastro sem nenhum informe | Qualquer caso | Média | Ver se a classe mudou de situação ou criou subclasse. |

**Contagem nesta rodada** (32.979 pares série × dia útil verificados; 1 alta, 97 médias, 1 baixa, 49 informativos):

| Regra | Alertas |
| --- | --- |
| Salto de cota isolado (média) | 72 |
| Salto de cota em dia de mercado (informativo) | 35 |
| PL sem explicação | 21 |
| Histórico curto | 14 |
| Informe duplicado | 4 |
| Dia sem informe | 1 |
| Valores zerados | 1 |
| Cota repetida, fonte atrasada, cadastro divergente | 0 |

### 5.1 Refinos

**Salto de cota: piso de 0,1 % e dia de mercado** (decidido em 26/09/2026).

- Por que 60 dias: cerca de três meses de pregões, o bastante para estimar o desvio e ainda acompanhar mudança de regime.
- Por que 5 desvios-padrão: é raro o bastante para não disparar toda semana num fundo normal.
- Por que o piso de 0,1 %: num fundo DI o desvio-padrão diário é de 0,001 %, e 5 desvios são centavos. Sem o piso, 19 dos alertas eram imateriais.
- Por que 3 % absoluto em Renda Fixa: um fundo de Renda Fixa mexer 3 % num dia é excepcional, qualquer que seja o histórico.
- **Dia de mercado:** se pelo menos 10 % das séries da mesma classificação CVM saltaram no mesmo dia, o salto vira informativo. Um em cada dez fundos da mesma classe mexendo junto é mercado, não o fundo. A fração é medida no universo de pares (as 3.392 séries candidatas), não em todos os fundos do país.
- Sem esses refinos, a regra gerava 127 alertas médios, e o evento real da gestora ficava escondido no meio deles.

**Classe sem subclasse operacional** (28/09/2026): monitorada como a própria classe (ver 3.5).

**Dia de referência com 90 % das séries** (28/09/2026): ver 4.1.

### 5.2 Exemplos reais

- **Evento de crédito da casa, 09/12/2024.** 13 séries de crédito da gestora caíram no mesmo dia, entre −0,11 % e −0,53 %, em fundos cujo dia normal é +0,04 %. No universo de pares, só 4,3 % dos fundos de Renda Fixa saltaram nesse dia. Não foi mercado: foi algo comum às carteiras da gestora, provavelmente a remarcação de um mesmo emissor. Ficou como alerta médio. Séries: `05755769000133`, `07900255000150-BQMVJ1750171627`, `07900255000150-FR33D1750172064`, `32760042000117`, `32760072000123`, `34081211000118`, `35609382000130-A8AAW1750173152`, `35609382000130-ZN9EI1750172960`, `36521750000156`, `44917374000141-UYXKV1750167974`, `44917374000141-WJPUK1750168728`, `45444067000153`, `48953198000154`.
- **Dia de mercado, 05/12/2025.** 72 % dos fundos de ações, 32 % dos multimercados e 19 % dos de renda fixa do universo de pares tiveram salto. O Dividendos (`08279304000141-9WCV01767643284`) caiu −4,53 % e o IBX (`06224719000192`) −4,29 %. Os 24 alertas do dia ficaram informativos. Em 13/03/2026, 13 % da renda fixa saltou.
- **Distribuição informada como resgate: `54023112000197`** (Incentivado em Infraestrutura, 1 cotista, R$ 49,4 mi). O informe traz resgate de cerca de R$ 505 mil todo mês, cerca de 1 % do PL, mas o PL não cai esse valor. O resíduo fica entre +0,97 % e +1,03 % em todos os 24 meses; 11 passam do limite. Leitura provável, **a confirmar**: pagamento de rendimentos que sai da cota e aparece como resgate. O alerta de PL é legítimo.
- **Duplicidade de 24/04/2025.** Quatro séries monitoradas têm cota, PL e resgates diferentes entre a linha `FI` e a `CLASSES - FIF`: `07900255000150-BQMVJ1750171627`, `07900255000150-FR33D1750172064`, `44917374000141-UYXKV1750167974` e `44917374000141-WJPUK1750168728`. Fora das monitoradas, o CNPJ `03537494000136` em 06/11/2024 tem captação de R$ 9.082,08 numa linha e R$ 64.743,05 na outra.
- **Linha zerada de 16/03/2026.** `34793170000192-BNAX91750170440` informou cota 0, PL 0 e 0 cotistas, no meio de uma série com cerca de 1.380 cotistas e R$ 120 mi. A linha sai do cálculo e gera dois alertas: valores zerados (alta) e o dia sem informe que ela deixa (baixa).
- **Subclasse que não herda.** `58327943000103-NANFG1779473395`, pela regra dos 7 dias (ver 4.1).
- **Fonte atrasada, 27/09/2026.** Com o portal da CVM fora do ar, a última data do informe estava em 22/09/2026: 3 dias úteis de atraso contra a tolerância de 2. Na rodada de 28/09/2026, com o portal de volta, o alerta sumiu.

## 6. O que cada gráfico e tabela mostra

Regras que valem para todas as telas:

- **Um eixo por gráfico.** Fundo e benchmark ficam na mesma unidade (retorno acumulado com base 100), para a comparação ser direta.
- **A cor segue a entidade.** O fundo tem sempre a mesma cor; CDI, IMA-B e Ibovespa têm cada um a sua em todas as páginas; Renda Fixa, Multimercado e Ações também.
- **Toda visualização tem tabela.** O botão "Ver tabela" troca o gráfico pelos números.
- Números com algarismos de largura fixa e o mesmo número de casas na mesma coluna.
- Gráfico com menos de 2 pontos não é desenhado: aparece um aviso explicando por quê.
- Todo gráfico de linha e de barra tem tooltip.

### 6.1 Visão geral

- **Faixa de qualidade.** "Dados até" o dia de referência, hora de geração, séries e dias verificados, última data de cada fonte e alertas por severidade. Como ler: se uma fonte está atrasada, os números dependentes dela são de antes.
- **Destaques.** Não seguem os filtros da página.
  - Contra o CDI em 12 meses: quantas séries de Público Geral (sem veículos estruturais) renderam acima do CDI e quais lideram.
  - Maiores captações e maiores resgates em 12 meses, no mesmo recorte.
  - Evento de crédito de 09/12/2024: o dia com mais saltos isolados entre todas as séries monitoradas, com a queda de cada uma.
  - Fundos incentivados: aviso de que o retorno pela cota provavelmente está subestimado, com o retorno e o percentil de cada um (ver 7).
- **Filtros.** Público (padrão Público Geral), classificação CVM e "Incluir veículos estruturais" (desligado). Mudam os tiles "Dos fundos exibidos" e a tabela.
- **Tiles "Dos fundos exibidos".** PL e captação líquida em 12 meses, somados das séries visíveis. O texto de apoio diz quantas séries têm captação com janela parcial.
- **Tiles "Da gestora".** PL e captação em 12 meses das 69 classes não exclusivas. "Incluir exclusivos" troca para as 246 classes. Não seguem os filtros de público e classificação, e incluem os veículos estruturais.
- **Captação líquida mensal por classificação.** Barras agrupadas por mês, uma por classificação CVM, nos últimos 12 meses. Barra abaixo de zero é saída líquida. O último mês é parcial até o dia de referência. Segue "Incluir exclusivos", não os outros filtros.
- **Tabela de fundos.** Uma linha por série, ordenada por PL. Retorno, % do CDI, volatilidade, drawdown e Sharpe de 12 meses; PL; captação em 12 meses (`*` = janela parcial); cotistas; posição entre pares (percentil do retorno e número de pares); alertas altos e médios. Classificação ANBIMA e público são colunas escondidas que podem ser ligadas. O nome leva à página do fundo.

### 6.2 Página do fundo

- **Cadastro.** CNPJ da classe, ID da subclasse, classificações, público, condomínio, indicador de desempenho declarado, benchmarks usados na comparação, início da série e última cota. Quando há herança, diz até que dia a cota veio da classe.
- **Tiles.** PL (com data e cotistas), captação em 12 meses, retorno em 12 meses (com o % do CDI), volatilidade, Sharpe, drawdown máximo (com pico, vale e recuperação), posição entre pares. Beta e tracking error só aparecem quando a série tem benchmark de mercado. Quando um número falta, o tile diz por quê ("menos de 12 meses de série", "menos de 60 observações").
- **Retorno acumulado contra o benchmark.** Linhas com base 100 no início da janela de 24 meses: o fundo e os benchmarks da série. Como ler: a distância entre as linhas no fim é a diferença de retorno acumulado. A tabela traz o valor no fim de cada mês.
- **Janelas de retorno.** Uma linha por janela: período e dias úteis, retorno do fundo, CDI, % do CDI, benchmark de mercado, excesso sobre o CDI e retorno anualizado (só a partir de 12 meses).
- **Drawdown.** Área abaixo de zero ao longo de 24 meses: quanto a cota está abaixo da sua máxima anterior. Zero é estar na máxima. A tabela traz, para 12 e 24 meses, o drawdown máximo, pico, vale, recuperação, melhor e pior dia, dias positivos e observações.
- **Captação líquida mensal.** Uma barra por mês, com cor de entrada ou de saída pelo sinal. A tabela traz captação, resgate, líquido, PL no fim do mês, cotistas, retorno no mês e resíduo do PL, destacado quando passa de 1 %.
- **Posição entre pares.** Para retorno, volatilidade e drawdown de 12 meses: uma faixa com o intervalo P25 a P75 dos pares, um traço na mediana e um ponto no fundo. Ao lado, o valor do fundo, a mediana e o percentil, com uma frase de leitura ("X % dos pares renderam menos"). Sem grupo de pares, o card explica o motivo.
- **Alertas de qualidade.** Lista dos alertas da série, com severidade, regra, data e uma frase montada a partir dos campos do alerta.

### 6.3 Qualidade

Todos os alertas do universo monitorado, filtráveis por regra, severidade e fundo, cada um com link para o fundo.

### 6.4 Metodologia

Este documento.

## 7. Limitações conhecidas

- **Cota não ajustada por evento.** O informe traz a cota depois de amortizações e distribuições, sem dizer que houve evento. O retorno pela cota subestima o que o cotista recebeu. Os fundos incentivados de infraestrutura, que pagam rendimentos, aparecem no fim da fila: `54023112000197` com −4,36 % em 12 meses e percentil 4 % entre 363 pares; `34793170000192-BNAX91750170440`, `34793170000192-D36IH1750170657` e `53248945000193` com percentil zero. Parte disso é provavelmente esse efeito; **a confirmar** com a lâmina. Quando a distribuição sai como resgate, a regra 4 também dispara.
- **Pares por classificação ANBIMA não separam incentivados.** Um fundo incentivado, isento de IR para a pessoa física, compete com fundos de crédito comuns da mesma classificação. A comparação é antes do IR do cotista, o que tira a vantagem do incentivado.
- **Decomposição mensal do PL supõe fluxo no fim do mês.** Com fluxo grande perto do PL, o resíduo infla. Exemplo: `54198519000155-TY3I61766775472` (Igaraté Long Biased IBOV) em fev/2026. O PL passou de R$ 1,8 mi para R$ 42,5 mi com aplicação de R$ 39,9 mi, e o resíduo deu 44 % do PL inicial. Trocar a base para o maior PL não resolve (ainda dá 1,9 %). Decidido em 28/09/2026: a regra fica como está; a decomposição diária está em `PRODUCTION.md`.
- **Benchmark por classificação, não por regulamento.** Um fundo que declara IPCA, IMA-B 5 ou IRF-M é comparado com o IMA-B; um de ações que declara IBrX, com o Ibovespa. Fundo de crédito de Renda Fixa que não declara "DI de um dia" (por exemplo, "Não se aplica") ainda recebe beta contra o IMA-B.
- **IMA-B pelo download diário público da ANBIMA.** Um POST por dia, sem contrato nem API. Se a ANBIMA mudar o formulário, a coleta quebra. Os outros IMAs são coletados e não usados.
- **Pares só para Público Geral e PL acima de R$ 50 milhões.** Séries de Profissional e Qualificado não têm posição entre pares. O grupo inclui outros fundos da própria gestora com CNPJ diferente (30 séries da gestora são pares elegíveis).
- **Dia de mercado medido no universo de pares.** A fração de 10 % da regra 2 é calculada nas 3.392 séries candidatas, não em todos os fundos do país.
- **Sem IR e sem come-cotas.** Os retornos são líquidos de taxa de administração e brutos de imposto do cotista.
- **Sem carteira.** O monitor não mostra exposição por emissor nem por setor. O evento de 09/12/2024 é inferido pela cota, não confirmado pela carteira.
- **Volatilidade supõe retornos independentes.** Em fundo de crédito com marcação suave, os retornos diários se parecem de um dia para o outro, e `√252` subestima o risco.
- **Ibovespa como publicado.** São os pontos de fechamento da B3, sem outro ajuste, e o dia corrente é descartado.
- **Veículo estrutural por nome.** É uma regra sobre o nome da classe, não um campo do cadastro.
- **Cadastro é a foto do dia.** Classificação, público e exclusividade de hoje valem para os 24 meses de histórico.
- **Janela fixa desde 01/09/2024.** "Desde o início" é desde o início da coleta, não da criação do fundo.
- **Fonte atrasada conta dias de semana, sem feriados.** Depois de um feriado, o atraso pode aparecer um dia maior do que é.

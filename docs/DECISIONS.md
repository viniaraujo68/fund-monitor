# Decisões e metodologia

Este documento explica o que o fund-monitor calcula, de onde vêm os dados e por que cada corte foi feito. **Os números citados são da rodada com dados até 24/09/2026** (último dia completo do informe diário), recalculada em 29/09/2026 com as regras deste documento; quando um número é de outro dia, a data vem junto. O site é atualizado todo dia útil pela Action e passa a mostrar números mais novos que os daqui: contagens de alertas, PL e posições entre pares valem para aquela rodada. A fonte da verdade é o código; as constantes estão no apêndice.

## 1. O que é o projeto

Um monitor diário dos fundos geridos pela **Icatu Vanguarda Gestão de Recursos Ltda.** (CNPJ `68622174000120`), feito só com dados públicos da CVM, do Bacen, da ANBIMA e da B3.

Ele responde a três perguntas:

1. **Como cada fundo rendeu** contra o seu benchmark e contra os seus pares?
2. **Para onde o dinheiro está indo?** Captação líquida por fundo e por classificação.
3. **Em que dado não dá para confiar?** Nove regras de qualidade, com alerta por fundo e por dia.

O fluxo tem quatro etapas: coleta → cálculo → qualidade → publicação. O pipeline em Python grava Parquet e depois JSON; o site é estático e só lê o JSON. Uma GitHub Action roda tudo de segunda a sexta, às 20h17 de Brasília.

Convenções que valem para o documento inteiro:

- **Dia útil** é dia com CDI publicado pelo Bacen (série 12 do SGS). É esse calendário que conta dias para anualizar e para saber se faltou informe. Duas contagens usam outro calendário, o dos **dias de semana** (segunda a sexta, feriados incluídos): os dias que a coleta pede à ANBIMA e o atraso da regra 8.
- **Anualização em 252** dias úteis, a convenção do mercado brasileiro.
- **Cota e dinheiro** entram como `Decimal` (a cota tem 12 casas na CVM). O cálculo usa ponto flutuante e arredonda na saída: 6 casas para retornos, volatilidade, tracking error e resíduo do PL; 4 para razões (Sharpe, beta, % do CDI, percentil) e para o índice base 100; 2 para dinheiro.
- No JSON, percentuais são frações: `0,1444` = 14,44 %.
- A data de referência de cada execução (`REFERENCE_DATE`) é o dia corrente no fuso `America/Sao_Paulo`.

## 2. Fontes

| Fonte | Endereço | Formato | Frequência | Uso |
| --- | --- | --- | --- | --- |
| Cadastro CVM (RCVM 175) | `https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip` | ZIP com 3 CSV, Latin-1, `;` | Baixado uma vez por data de referência | Quem é da gestora, classificação, público, exclusividade, benchmark declarado |
| Informe diário CVM | `https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_AAAAMM.zip` | ZIP mensal com 1 CSV, Latin-1, `;`, ponto decimal | Dado diário, arquivo mensal, republicado | Cota, PL, captação, resgate, cotistas |
| Bacen SGS | `https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados?formato=json` | JSON, datas e valores como texto | Diário | CDI como benchmark e taxa livre de risco |
| ANBIMA IMA | `POST https://www.anbima.com.br/informacoes/ima/ima-sh-down.asp` | CSV, Latin-1, `;`, vírgula decimal | Um arquivo por dia de semana (feriado vem vazio) | IMA-B |
| B3 Ibovespa e IBrX-100 | `GET https://sistemaswebb3-listados.b3.com.br/indexStatisticsProxy/IndexCall/GetPortfolioDay/{base64}` | JSON, números em texto pt-BR | Um arquivo por ano e por índice | Ibovespa (`IBOV`) e IBrX-100 (`IBXX`) |

A janela coletada começa em **01/09/2024** (`WINDOW_START`), o que dá 24 meses até setembro de 2026, para a gestora e para os pares.

Nenhuma resposta das fontes de índice é gravada sem ser conferida antes: o Bacen, a ANBIMA e a B3 têm a validação descrita em 2.3 a 2.5. O informe da CVM é baixado para um arquivo `.part` que só substitui o anterior quando o download termina, e o cabeçalho e o CNPJ são conferidos antes de gravar o Parquet (2.2).

### 2.1 Cadastro CVM

- Três arquivos: `registro_fundo.csv` (90.383 linhas), `registro_classe.csv` (36.782) e `registro_subclasse.csv` (10.121), no snapshot de 28/09/2026.
- Só o snapshot da data de referência fica em `data/raw`; os anteriores são apagados. Só as colunas usadas entram no cadastro normalizado; as outras não são convertidas.
- A gestora é filtrada por `CPF_CNPJ_Gestor = 68622174000120`. Por CNPJ, e não por nome, porque o CNPJ é exato.
- O CNPJ que liga cadastro e informe é `registro_classe.CNPJ_Classe`.
- O cadastro normalizado (`registry.parquet`) tem uma linha por `(ID_Registro_Classe, ID_Subclasse)` e a coluna `subclass_reported`, que diz se a subclasse já publicou cota maior que zero em algum informe coletado (ver 3.5).

Armadilhas, contadas no snapshot de 28/09/2026:

- `registro_fundo.csv` tem **uma linha por gestor**. São 1.041 fundos com mais de um gestor no país; 24 deles têm a gestora entre os gestores (10 em funcionamento normal), por exemplo com a Icatu Seguros, a Rio Grande Seguros e a DOJO Capital (o FII GRU Logístico). Os gestores viram uma lista por fundo antes do join.
- `registro_classe.csv` repete a classe quando muda o custodiante ou o controlador: 8 linhas de 4 classes. Essas colunas são descartadas e a linha é deduplicada.
- `registro_subclasse.csv` tem aspas literais nos nomes (`SUBCLASSE "A"`). O CSV é lido sem caractere de aspas.
- `CNPJ_Classe` não é único no país: 5 CNPJs se repetem entre classes em funcionamento normal, 2 deles entre as classes FIF ativas que o monitor usa. Por isso a chave do cadastro normalizado é `(ID_Registro_Classe, ID_Subclasse)`. O informe, porém, só traz CNPJ e `ID_SUBCLASSE`, então a série de cota é `(CNPJ_Classe, ID_Subclasse)` (ver 3.5) e é essa a chave do join. Um CNPJ repetido vira duas séries com a mesma chave. Na gestora, isso para o pipeline com erro (`ensure_unique`). Nos pares, as séries ativas com chave repetida ficam fora do universo, com aviso no log: hoje são 4 séries de 2 CNPJs, todas de Profissional, que já estariam fora dos pares de Público Geral.
- Em 27/09/2026 uma classe em transição sumiu do cadastro (ver 3.5).

### 2.2 Informe diário CVM

- Colunas usadas: `TP_FUNDO_CLASSE`, `CNPJ_FUNDO_CLASSE`, `ID_SUBCLASSE`, `DT_COMPTC`, `VL_TOTAL`, `VL_QUOTA`, `VL_PATRIM_LIQ`, `CAPTC_DIA`, `RESG_DIA`, `NR_COTST`. Se o cabeçalho mudar, a coleta para com erro.
- O arquivo é lido em streaming e filtrado pelos CNPJs da gestora e dos pares **na leitura**. Sem isso, 24 meses do país ocupam gigabytes. Dos pares, só cota e PL são guardados.
- O CNPJ vem com máscara (`00.017.024/0001-53`). Só a pontuação da máscara (`.`, `/`, `-`) é removida; letras ficam, por causa do CNPJ alfanumérico da IN RFB 2.229/2024. O resultado precisa ter 14 caracteres, ou a coleta para com erro.

Armadilhas:

- Confirmado em 24/09/2026: todo mês desde jan/2021 está em `DADOS/`; `HIST/` só tem arquivos anuais até 2020.
- A CVM **republica meses antigos**. O de 202409 tinha Last-Modified de 30/08/2025. Em 27/09/2026 ela regravou os 25 meses. Por isso o coletor pergunta tamanho e Last-Modified antes de baixar e refiltra o bruto a cada execução. O efeito nas séries da gestora está em `findings.md`.
- 72 linhas de 23 CNPJs aparecem duas vezes no mesmo dia, uma como `FI` e outra como `CLASSES - FIF`, em 19 datas entre 15/10/2024 e 01/07/2025, na passagem para a RCVM 175 (ver 4.1).
- O último dia do arquivo pode estar incompleto: em 28/09/2026, o dia 25/09/2026 tinha só 8 das 246 classes da gestora (ver 4.1).
- A CVM consolida o arquivo mensal com atraso de 2 a 3 dias úteis: em 28/09/2026 às 21h, o arquivo de setembro ainda tinha o dia 25 (sexta) incompleto e nada do dia 28 (segunda); o informe não tem linhas de fim de semana. Por isso o "Dados até" do site anda nesse passo, atrás do calendário.
- Em 26 e 27/09/2026 o portal `dados.cvm.gov.br` não respondeu. A regra 8 existe para esse caso (ver 5).

### 2.3 Bacen SGS

- Só a série 12 (CDI diário) é coletada, a janela inteira numa chamada. O JSON é pedido e regravado a cada execução.
- A resposta só é gravada se for uma lista não vazia de registros com `data` e `valor`. O Bacen às vezes devolve uma página HTML com status 200: nesse caso nada é gravado e o pedido é repetido, até 3 tentativas com 2 s de pausa. Depois da terceira, a coleta para com erro.
- O CDI vem em percentual ao dia: `0,050788` significa 0,050788 % no dia. Fator diário = `1 + valor / 100`.
- A taxa publicada para o dia d rende de d até o dia útil seguinte. No código, o nível do CDI acumulado do dia d entra na data d + 1.

### 2.4 ANBIMA IMA

- Um POST por dia de semana, sem login, com a data no corpo do formulário, com pausa de 1 s entre eles. De 02/09/2024 a 25/09/2026 são 540 dias de semana; os 20 feriados voltam como um arquivo de 46 bytes que começa com "Não há dados disponíveis".
- A resposta só é gravada se tiver a linha de cabeçalho (`Índice;...`) ou começar com "Não há dados disponíveis". Qualquer outra coisa não é gravada, e o dia é pedido de novo na execução seguinte.
- Um dia já gravado não é pedido de novo, com duas exceções: o arquivo gravado não é uma resposta esperada, ou o dia é recente (até 7 dias antes da referência, `ANBIMA_RETRY_EMPTY_DAYS`) e veio sem dados.
- Linhas guardadas: IMA-B, IMA-B 5, IMA-B 5+, IRF-M, IMA-S e IMA-GERAL. **Só o IMA-B entra no cálculo.**
- Histórico confirmado em 24/09/2026: a linha do IMA-B vem preenchida desde pelo menos 03/01/2022. A janela de 24 meses cabe inteira.
- Linha com data diferente da pedida é descartada.
- Conferência externa: o IMA-B de 12 e 24 meses publicado nesta rodada (12,5782 % e 19,2681 %, de 24/09/2025 e 24/09/2024 até 24/09/2026) é igual, nas 4 casas, às colunas "Variação 12 Meses(%)" e "Variação 24 Meses(%)" do próprio arquivo da ANBIMA de 24/09/2026.

### 2.5 B3 Ibovespa e IBrX-100

- Uma chamada por ano e por índice, com `{"index":"IBOV","language":"pt-br","year":"AAAA"}` em base64 no caminho; para o IBrX-100 o código é `IBXX` (conferido em 29/09/2026: o mesmo endpoint devolve o IBrX-100 com o mesmo formato; `IBXL` é o IBrX-50). A resposta tem uma linha por dia do mês e uma coluna por mês (`rateValue1` a `rateValue12`), com o fechamento em texto (`"183.965,91"`).
- A resposta é lida antes de ser gravada. Se não for legível, ou se for de um ano passado e vier sem nenhum fechamento, nada é gravado e a coleta para com erro.
- Cobertura em 28/09/2026: 2024 com 251 pregões, 2025 com 250, 2026 com 184 até 25/09. O IBrX-100 tem os mesmos pregões (517 fechamentos de 02/09/2024 a 28/09/2026).
- O IBrX-100 entrou em 29/09/2026 para as três séries de ações que declaram IBrX (4.5). Em 12 meses até 24/09/2026 ele rendeu 25,15 %, contra 25,58 % do Ibovespa: comparar essas séries com o Ibovespa custava 0,43 p.p. de excesso.
- Armadilha: **o valor do dia corrente aparece antes do fechamento**. O coletor descarta a data de execução e fica só com dias encerrados.
- O ano corrente é baixado de novo a cada execução. Um ano passado é baixado de novo até o arquivo ser final: gravado depois de 31/12 e com o último pregão esperado do ano (o último dia de semana até 30/12), ou gravado mais de 10 dias depois do fim do ano (`REFRESH_GRACE_DAYS`), o que vier primeiro.

### 2.6 O que foi descartado

| Fonte | Motivo |
| --- | --- |
| `cad_fi.csv` (cadastro legado) | Só tem 22 fundos "EM FUNCIONAMENTO NORMAL" no país; os 59 da gestora aparecem como cancelados. O cadastro certo é `registro_fundo_classe.zip`. |
| SGS 11, 433 e 189 (Selic, IPCA e IGP-M) | Nenhum indicador do monitor usa. Deixaram de ser coletados. |
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
| Em séries de cota | 253 séries | Subclasses fora de funcionamento normal ou que ainda não publicaram cota | 8 classes informam por subclasse (ver 3.5) |
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
- **Subclasse operacional** (28/09/2026): a subclasse só vira série quando está em funcionamento normal **e** já publicou cota maior que zero em algum informe coletado (`subclass_reported`). Até lá, a classe é monitorada como ela mesma.
- **Classe sem subclasse operacional** (28/09/2026): é monitorada como a própria classe, com `series_id` igual ao CNPJ. Exclusividade, público e condomínio vêm do consenso das subclasses. Caso real: entre 24 e 27/09/2026, a classe `35637151000130` (Igaraté Long Biased, Público Geral, R$ 600 mi) criou as subclasses `HGO9N1790345272` e `S8AUG1790345378`, ambas pré-operacionais desde 25/09/2026. O cadastro normalizado passou a ter só as linhas das subclasses, mas o informe continuou publicando a cota da classe. Sem a regra, o fundo sumia do monitor. Quando as subclasses começarem a informar, elas herdam a cota da classe e o `series_id` muda.
- **Quando as subclasses discordam**, o consenso fica vazio. Com exclusividade vazia, a classe sai do monitor sem alerta: não conta como monitorada nem como exclusiva, e a soma das duas deixa de dar o total de séries da gestora. Com público vazio, ela fica fora dos pares. Hoje nenhuma classe da gestora está nesse caso; no país, das 509 classes em transição, 13 têm exclusividade vazia e 17 têm público vazio.

### 3.6 FII fora

Decidido em 24/09/2026. O filtro é `Tipo_Classe = "Classes de Cotas de Fundos FIF"`. FII não entrega informe diário. Eram as 2 classes "sem classificação" da contagem original.

## 4. Indicadores

### 4.1 Montagem da série de cota

**Dia de referência.** É o último dia em que pelo menos 90 % das séries monitoradas informaram cota, comparando com o dia de maior cobertura entre os 20 últimos dias com informe. Linhas posteriores ficam de fora do cálculo **e das regras de qualidade** até o dia completar: uma linha zerada ou duplicada no dia parcial só gera alerta quando o dia entra. Por quê: em 28/09/2026, o dia 25/09/2026 tinha só 8 das 246 classes. Usar "a última data com cota" criaria um falso "dia sem informe" para as outras séries e faria cada fundo terminar num dia diferente.

**FI × CLASSES - FIF** (24/09/2026). Quando a mesma série tem uma linha `FI` e outra `CLASSES - FIF` no mesmo dia, vale `CLASSES - FIF`, que é o regime atual; a linha `FI` é descartada. A divergência vira alerta da regra 7. Por quê: 72 linhas de 23 CNPJs vêm duplicadas, e em alguns casos com cota e captação diferentes.

**Herança de cota da subclasse** (24/09/2026).

- Quando a classe cria subclasses, cada subclasse nasce com a mesma cota da classe. Antes disso, a história está na linha sem subclasse.
- A série da subclasse herda **só a cota** das linhas da classe anteriores à sua primeira cota própria. Exemplo: `44917374000141-UYXKV1750167974` herda a cota até 16/06/2025. O site avisa no cadastro do fundo.
- PL, captação e cotistas **não** são herdados: usam só as linhas da própria série. Herdar a linha inteira contaria o PL em dobro nas classes com duas subclasses não exclusivas. A captação de 12 meses só fica marcada como parcial quando a primeira linha própria é posterior ao início da janela (ver 4.4). As subclasses criadas em 17/06/2025, como `44917374000141-UYXKV1750167974`, já têm os 12 meses inteiros e não levam a marca; as criadas depois de 24/09/2025 levam.
- Nas classes com duas subclasses, as duas herdam a mesma história de cota. Até a divisão, elas não são duas medidas independentes (ver 5).
- **Regra dos 7 dias:** a herança só vale se a classe publicou cota nos 7 dias corridos antes da primeira cota da subclasse. Caso real: `58327943000103-NANFG1779473395` (Dinâmico CDI IU) nasceu em 12/08/2026 de uma subclasse irmã, três meses depois de a classe parar de publicar. Herdar a cota da classe criaria um "retorno diário" de +3,6 % que não existiu. Das 14 subclasses monitoradas, 13 herdam.

**Cota inválida.** Linha com cota ≤ 0 sai de todo o cálculo: série de cota, PL, captação, cotistas, agregados da gestora e pares (ver regra 5). Uma linha com cota válida e PL ou cotistas zerados continua no cálculo e gera o alerta da regra 5.

As linhas descartadas pelo cálculo são, portanto, três: a linha com cota ≤ 0, a linha `FI` de uma duplicidade e as linhas posteriores ao dia de referência.

### 4.2 Retornos

**Retorno diário.** `r_t = cota_t / cota_(t-1) − 1`, entre dois informes seguidos da série.

- Sem ajuste por come-cotas: o come-cotas reduz a quantidade de cotas do cotista, não o valor da cota.
- A cota do informe já é líquida da taxa de administração.

**Retorno acumulado.** `R = cota_fim / cota_base − 1`, que é o mesmo que `∏(1 + r_t) − 1`. A cota base é a última cota até a data-âncora da janela. A cota do fim é a última cota da série até o dia de referência.

**Janelas.**

| Janela | Data-âncora |
| --- | --- |
| No mês | Último dia do mês anterior |
| No ano | 31/12 do ano anterior |
| 3, 6, 12 e 24 meses | Mesma data, N meses antes do dia de referência |
| Desde o início | Primeira cota da série **no período coletado** (desde 02/09/2024), não a data de criação do fundo |

Se a série começou depois da âncora, a janela fica vazia ("sem histórico"). O número de dias úteis `n` de cada janela é o número de dias de CDI entre a base e o fim.

**Série parada.** Se a última cota da série tem mais de 7 dias corridos antes do dia de referência (`MAX_QUOTA_STALENESS`), o retorno da janela ainda é publicado, mas sem anualização, sem % do CDI e sem Sharpe, e a série sai dos pares. Hoje todas as 75 séries têm cota em 24/09/2026.

**Retorno anualizado.** `(1 + R)^(252 / n) − 1`. Só para as janelas de 12 e 24 meses, e para "desde o início" com `n ≥ 252`, e só com a série em dia. Por quê: anualizar uma janela curta multiplica o ruído. Um mês bom vira uma taxa anual que ninguém recebeu. O site não mostra o anualizado na janela de 12 meses: com 251 dias úteis na janela, ele sai um pouco acima do próprio retorno (IBX: 24,85 % contra 24,74 %) e confunde mais do que informa. O Sharpe de 12 meses continua usando a taxa anualizada.

**Benchmark no período.**

- CDI: `∏(1 + CDI_d / 100) − 1` sobre os dias de CDI entre a base e o fim.
- IMA-B: número-índice no fim / número-índice na base − 1.
- Ibovespa: pontos no fim / pontos na base − 1.
- Em cada data vale o último nível publicado, com tolerância de 7 dias. A mesma tolerância vale para a contagem de dias de CDI: se o CDI parou de ser publicado há mais de 7 dias, `n`, o CDI do período e o retorno anualizado ficam vazios.

**% do CDI.** `R_fundo / R_CDI` no mesmo período. É a razão dos retornos acumulados, não das taxas anualizadas. É calculado em **todas as janelas**, desde que a série esteja em dia e o CDI do período seja positivo (decidido em 29/09/2026). Por quê: toda lâmina de fundo mostra o % do CDI no mês e no ano, e com o CDI perto de 14 % ao ano a razão não explode nem em um mês. A versão anterior só publicava a partir de 12 meses, com medo da janela curta; o risco real é o CDI perto de zero, e o filtro de CDI positivo cobre esse caso. Em janela de poucos dias no começo do mês, o % do CDI de um fundo de ações ainda oscila muito: é o número certo, só que pouco informativo. Com retorno negativo, o % do CDI fica negativo: `54023112000197` tem −30,09 % do CDI em 12 meses.

**Excesso de retorno.** `R_fundo − R_benchmark`, diferença simples dos acumulados no período, em pontos percentuais. É calculado contra CDI, IMA-B, Ibovespa e IBrX-100. O site mostra o excesso sobre o **benchmark principal** da série (4.5) na tabela de fundos e no tile de retorno, e, na tabela de janelas, o excesso sobre o CDI e sobre o benchmark de mercado.

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

**Sharpe (ex-post).** `(R_anual_fundo − R_anual_CDI) / volatilidade`, em 12 e 24 meses. Fica vazio quando a janela não é anualizável (4.2).

- É um Sharpe com o **CDI como taxa livre de risco**. O CDI é o que o investidor brasileiro ganha sem risco de mercado, e é o que um fundo DI entrega.
- Leitura: quanto de retorno acima do CDI o fundo entregou por unidade de oscilação.
- Cuidado: em fundo de volatilidade muito baixa, uma diferença pequena contra o CDI vira um Sharpe grande em módulo.
- **Escondido no site para série "DI de um dia"** (decidido em 29/09/2026). O Gold (`10756556000166`) rendeu 0,29 p.p. abaixo do CDI com vol de 0,11 % e teria Sharpe de −2,66; o Veículo Especial DC (`54514671000108`) teria 16,24. Nos dois casos o número é ruído. O pipeline continua calculando e publicando o Sharpe; a tabela de fundos e o tile da página do fundo mostram um traço com o motivo. Foi a opção mais simples: a mesma marca "DI de um dia" que já tira o beta e o tracking error (4.5).

**Beta e tracking error.** Só contra o benchmark de mercado da série: IMA-B para Renda Fixa, Ibovespa para Ações, IBrX-100 para as ações que declaram IBrX. Multimercado não tem.

- `beta = cov(r_fundo, r_bench) / var(r_bench)`, com os retornos do benchmark medidos entre as mesmas datas dos informes do fundo.
- `tracking error = desvio-padrão amostral(r_fundo − r_bench) × √252`.
- Mínimo de 60 observações, como a volatilidade.
- **Nunca para série "DI de um dia"** (decidido em 28/09/2026). 24 das 45 séries de Renda Fixa declaram "DI de um dia" como indicador de desempenho. Um fundo DI não tenta seguir o IMA-B; o beta dele contra o IMA-B pareceria informação e seria ruído. Foi escolhida a versão mais simples por prazo, em vez de um mapa de benchmark por fundo.

**Métricas auxiliares.** Fração de dias positivos, melhor dia e pior dia, com a data de cada um.

### 4.4 Fluxos e tamanho

**Captação líquida.** Diária: `CAPTC_DIA − RESG_DIA`. Mensal: soma dos dias do mês. Em 12 meses: soma dos dias depois de (dia de referência − 12 meses). Usa só as linhas da própria série. Quando a primeira linha própria da série é posterior ao início da janela de 12 meses, a captação é marcada como parcial (`*` na tabela).

**PL.** Último `VL_PATRIM_LIQ` da série até o dia de referência.

**Decomposição do PL.** Para cada mês:

```
resíduo = PL_fim − PL_início − captação_líquida − PL_início × r_mês
```

- `PL_início` é o PL do último informe do mês anterior. `r_mês` é a cota no fim do mês sobre a cota no fim do mês anterior, menos 1.
- O resíduo é publicado como fração de `PL_início`, com 6 casas.
- Por quê: o PL só deveria mudar por dinheiro que entra ou sai e pela rentabilidade. O que sobra aponta dado errado ou evento que o informe não descreve. Resíduo acima de 1 % em módulo, para mais ou para menos, vira alerta da regra 4.
- Supõe que todo fluxo acontece no fim do mês (ver limitação em 7).

**Cotistas.** Último `NR_COTST` da série, e o número no fim de cada mês na tabela de captação. A variação em 12 meses é calculada no pipeline, mas não é publicada no site nesta versão.

**Agregados da gestora.** PL total, captação em 12 meses e captação mensal por classificação CVM e ANBIMA, em dois escopos.

- PL: soma do último PL de cada série `(CNPJ, subclasse)` até o dia de referência. A linha da classe sai da soma quando alguma subclasse do mesmo CNPJ já informou no período (a janela inteira no total, o mês no gráfico mensal), para não contar o PL duas vezes.
- Captação: linhas da classe até a primeira linha de subclasse do CNPJ, e as linhas das subclasses depois.

| Escopo | Classes | PL em 24/09/2026 | Captação em 12 meses |
| --- | --- | --- | --- |
| Não exclusivas | 69 | R$ 27,1 bi | R$ 9,2 bi |
| Toda a gestora | 246 | R$ 93,3 bi | R$ 13,5 bi |

### 4.5 Benchmark por série

| Classificação CVM | Comparado com | Benchmark de mercado (beta e tracking error) | Benchmark principal |
| --- | --- | --- | --- |
| Renda Fixa | CDI e IMA-B | IMA-B | IMA-B |
| Multimercado | CDI | — | CDI |
| Ações | CDI e Ibovespa | Ibovespa | Ibovespa |
| Ações com `Indicador_Desempenho` = "IBrX" | CDI e IBrX-100 | IBrX-100 | IBrX-100 |
| Qualquer uma com `Indicador_Desempenho` = "DI de um dia" | CDI | — | CDI |

**Benchmark principal** (decidido em 29/09/2026). É o benchmark de mercado quando a série tem um, e o CDI quando não tem. É contra ele que o site diz se o fundo "bateu o benchmark" (excesso de 12 meses em p.p.). Por quê: comparar todo fundo com o CDI dizia que fundos de inflação e de ações perderam do CDI, o que é verdade mas não é o mandato deles. Na rodada de 24/09/2026, **6 de 36** séries de Público Geral (sem estruturais) bateram o próprio benchmark em 12 meses: Inflação Curta (+1,24 p.p. sobre o IMA-B), Dinâmico CDI (+0,50), Inflação Curta FIC (+0,50), Dinâmico Institucional (+0,22), Crédito Privado IU Seleção (+0,05) e Inflação (+0,05). Contra o CDI eram 5 de 36. O excesso mediano é −0,72 p.p., e 12 das 36 ficam a menos de 0,5 p.p. do benchmark, perto do que custa a taxa de administração. A correção é de método: a leitura sobre a gestora muda pouco.

Em Público Geral, todos os fundos de crédito de Renda Fixa declaram "DI de um dia", então nenhum deles é comparado com o IMA-B. Os de Renda Fixa comparados com o IMA-B são os de inflação, o pré-fixado e os incentivados.

- A regra é por classificação porque o `Indicador_Desempenho` do cadastro não é uniforme. Nas 75 séries: 32 "DI de um dia", 15 "OUTROS", 14 "Não se aplica", 4 IPCA, 4 IMA-B 5, 3 IBrX, e um cada de IMA-B 5+, IMA-B e IRF-M.
- **IBrX-100** (29/09/2026): IBX (`06224719000192`), IBX FIFE (`34798905000170`) e Dividendos (`08279304000141-9WCV01767643284`) declaram IBrX. A B3 publica o IBrX-100 no mesmo endpoint do Ibovespa, então ele passou a ser coletado. Efeito em 12 meses: o IBX fica em −0,42 p.p. contra o IBrX-100, em vez de −0,84 p.p. contra o Ibovespa.
- A exceção DI é a versão mínima da decisão de 28/09/2026 (ver 4.3). Ela afeta 24 séries de Renda Fixa e 8 Multimercado; nestas últimas nada muda, porque Multimercado já é comparado só com o CDI.
- O cadastro do fundo no site mostra o indicador declarado e, ao lado, com o que ele está sendo comparado.

### 4.6 Pares

Implementado em 26–28/09/2026.

**Grupo.** Todas as séries **do país** com a mesma `Classificacao_Anbima` e o mesmo `Publico_Alvo` do fundo, não exclusivas, em funcionamento normal, com chave `(CNPJ, subclasse)` única (ver 2.1).

**Só Público Geral.** Por custo de leitura, os pares foram calculados só para as séries de Público Geral, nas classificações ANBIMA que as séries de Público Geral da gestora usam: **3.392 séries candidatas** (3.291 classes em 13 classificações ANBIMA).

**Elegibilidade de um par.**

- Retorno de 12 meses calculado, ou seja, cota desde antes da âncora de 12 meses.
- Volatilidade e drawdown de 12 meses calculados (a volatilidade pede pelo menos 60 observações).
- Última cota a no máximo 7 dias do dia de referência (4.2).
- PL acima de R$ 50 milhões. Por quê: tira fundos pequenos demais para serem alternativa real e mais sujeitos a cota ruidosa (fundo começando ou encerrando).
- Resultado: **1.649 elegíveis**. Saíram 387 sem 12 meses, 1.352 com PL até R$ 50 milhões e 4 paradas há mais de 7 dias.

**O fundo avaliado.**

- A própria classe e as subclasses irmãs (mesmo CNPJ) ficam fora do grupo: o fundo não é par de si mesmo.
- O limite de PL vale para os pares, não para o fundo avaliado. `54023112000197`, com R$ 49,4 mi, tem posição entre 359 pares. O fundo avaliado precisa das três métricas de 12 meses e de estar em dia.
- A posição e o percentil só são publicados com **pelo menos 5 pares**.
- 36 das 44 séries de Público Geral têm posição; as outras 8 ainda não têm 12 meses de série.

**Percentil.**

A tabela de fundos mostra o percentil do retorno **e** o da volatilidade lado a lado ("P71 ret · P2 vol · 358"), decidido em 29/09/2026. Por quê: os grupos ANBIMA são heterogêneos. "Multimercados Livre" tem 359 pares com vol de 12 meses de 0,6 % (P10) a 13,8 % (P90); "Renda Fixa Duração Livre Crédito Livre" tem 471 pares com vol de 0,13 % a 4,9 %. O Dinâmico Institucional (`52163627000167`), com vol de 0,20 %, fica em P71 de retorno nesse grupo, o que sozinho quase não informa; ao lado de "P2 vol" a leitura fica clara: rendeu mais que 71 % dos pares oscilando menos que 98 % deles. Foram descartados o percentil do Sharpe, que herda o ruído do Sharpe em fundo de vol baixa (o sinal de uma diferença mínima contra o CDI joga o fundo para um extremo: o mesmo Dinâmico Institucional iria a P94, o Multiestratégia de P62 de retorno a P32), e pares por faixa de vol, que encolhe os grupos e acrescenta um limiar.

```
percentil = (pares com valor abaixo + ½ × pares com valor igual) / número de pares
```

- Empate conta pela metade para não favorecer nem penalizar o fundo.
- É calculado para retorno, volatilidade e drawdown máximo de 12 meses. Os quartis dos pares (P25, mediana, P75) são publicados com interpolação linear.
- Leitura: no retorno, percentil alto é ter rendido mais que a maioria. Na volatilidade, percentil alto é ter oscilado mais. No drawdown, que é negativo, percentil alto é ter caído menos.

Os pares usam 24 meses de informe (18 MB de Parquet).

**Duas ressalvas do grupo de pares.**

- **Viés de sobrevivência.** Exigir 12 meses de cota, PL acima de R$ 50 milhões e cota em dia **hoje** tira do grupo os fundos que fecharam ou encolheram no período, que em média renderam pior. A mediana dos pares tende a sair melhor do que o universo que existia 12 meses atrás, e a posição do fundo, um pouco pior.
- **FIC e master da mesma estratégia contam como pares distintos**, na gestora e no mercado inteiro. Um fundo com FIC e master na mesma classificação aparece duas vezes no grupo, com quase o mesmo retorno. Não há deduplicação: o cadastro não liga o FIC ao master.

## 5. Regras de qualidade

**Princípio: marcar, não excluir.** Um alerta não tira o dado do cálculo. Ele aparece na página do fundo, na página Qualidade e na contagem do topo do site. O que fazer com cada alerta depois de lido, isto é, registrar a tratativa e o desfecho, está em 5.3. As exceções são explícitas:

- a linha com cota ≤ 0 sai de todo o cálculo (regra 5 e 4.1);
- na duplicidade, vale a linha `CLASSES - FIF` (regra 7);
- as linhas depois do dia de referência ficam de fora do cálculo e das regras até o dia completar (4.1);
- a série sem 12 meses fica fora dos pares e sem % do CDI (regra 6);
- a série parada há mais de 7 dias perde anualização, % do CDI e Sharpe e sai dos pares (4.2).

**Severidades.** Alta: dado claramente errado (linha zerada) ou fonte tão atrasada que os números do site são de dias antes (regra 8). Média: pede investigação. Baixa: falha pequena. Informativo: real, mas explicado.

**Linhas herdadas.** As regras que olham o informe (5 e 7) atribuem uma linha da classe anterior à divisão a cada subclasse que herda a cota dela, pela regra dos 7 dias (4.1). As regras que olham a série de cota (1, 2 e 3) veem a história herdada, que é igual nas subclasses irmãs. Numa classe com duas subclasses, um fato da classe antes da divisão vira dois alertas iguais, um por subclasse. A contagem abaixo é de alertas por série, não de fatos distintos.

| # | Regra (código) | O que detecta | Limiar no código | Severidade | O que fazer |
| --- | --- | --- | --- | --- | --- |
| 1 | Dia sem informe (`missing_report`) | Dia útil, depois da primeira cota da série (herdada inclusive) e até o dia de referência, sem cota válida da série. Dias seguidos viram um alerta só. | Qualquer dia | Média com 5 ou mais dias úteis seguidos; baixa com menos | Ver se o fundo suspendeu a cota. O retorno do informe seguinte cobre os dias que faltaram. |
| 2 | Salto de cota (`quota_jump`) | Retorno entre dois informes seguidos fora do padrão do próprio fundo | `k` = dias de CDI que o retorno cobre; média e desvio-padrão σ dos 60 retornos anteriores, convertidos em retorno diário equivalente `(1 + r)^(1/k) − 1`. Dispara se `abs(r − k × média) > 5σ√k` **e** `abs(r − k × média) ≥ 0,1 %`; ou, em Renda Fixa, se `abs(r) > 3 %` | Média; informativo se for dia de mercado: o índice mais correlacionado com o fundo (Ibovespa ou IMA-B, \|ρ\| ≥ 0,5) mexeu mais de 2,5σ no mesmo sentido, ou 10 % dos pares da mesma classificação CVM saltaram | Procurar evento de crédito ou remarcação. Comparar com outros fundos da gestora no mesmo dia; subclasses irmãs antes da divisão têm a mesma cota e sempre concordam. |
| 3 | Cota repetida (`repeated_quota`) | Mesma cota em informes seguidos | 3 ou mais informes | Média | Fundo parado ou dado congelado. Perguntar ao administrador. |
| 4 | PL sem explicação (`unexplained_net_assets`) | Variação mensal do PL que captação e rentabilidade não explicam | `abs(resíduo) > 1 %` do PL do início do mês | Média | Procurar amortização, distribuição, incorporação ou fluxo entre veículos. |
| 5 | Valores zerados (`zero_values`) | Linha publicada com cota, PL ou cotistas zerados | cota ≤ 0, PL ≤ 0 ou 0 cotistas | Alta | Tratar como erro de envio. A linha com cota ≤ 0 sai de todo o cálculo e deixa um dia sem informe (regra 1). |
| 6 | Histórico curto (`short_history`) | Série sem retorno de 12 meses | Janela de 12 meses vazia | Informativo | Fica fora dos pares e do ranking contra o CDI. Continua na tabela e nos destaques de captação, com a captação marcada como parcial. |
| 7 | Informe duplicado (`duplicate_report`) | Mesma série e dia em mais de uma linha, com valores diferentes | Qualquer diferença em cota, PL, patrimônio total, captação, resgate ou cotistas | Média | Vale `CLASSES - FIF`. O alerta guarda quais campos divergiram. |
| 8 | Fonte atrasada (`stale_source`) | Última data da fonte longe do último dia de semana antes da execução | Atraso em dias de semana, sem descontar feriados. Tolerância: informe CVM 2; CDI, IMA-B e Ibovespa 1 | Média acima da tolerância; alta acima da tolerância + 3 ou sem nenhuma data | Não confiar no dia: os números são de antes. Ver se o portal está no ar. |
| 9 | Cadastro divergente (`registry_mismatch`) | Três casos: série no informe (CNPJs da gestora) que não está no cadastro; série monitorada do cadastro sem nenhum informe; série no informe que está no cadastro da gestora mas não entre as séries ativas (por exemplo, fora de funcionamento normal) | Qualquer caso | Média | Ver se a classe mudou de situação ou criou subclasse. |

No salto de cota, o `threshold` publicado é o limite que disparou: 3 % no critério absoluto de Renda Fixa; senão o maior entre o piso de 0,1 % e `5σ√k`. O alerta também publica o `deviation`, o desvio `r − k × média` que é comparado com o limite. O site mostra o desvio ao lado do limite e o retorno do dia como informação secundária: "retorno −0,20 %, limite 0,23 %" parecia um valor abaixo do limite, quando o que passou foi o desvio de −0,25 %.

**Contagem na rodada de 24/09/2026** (32.979 pares série × dia útil verificados; 1 alta, 81 médias, 1 baixa, 65 informativos, 148 no total):

| Regra | Alertas |
| --- | --- |
| Salto de cota isolado (média) | 56 |
| Salto de cota em dia de mercado (informativo) | 51 |
| PL sem explicação | 21 |
| Histórico curto | 14 |
| Informe duplicado | 4 |
| Dia sem informe | 1 |
| Valores zerados | 1 |
| Cota repetida, fonte atrasada, cadastro divergente | 0 |

### 5.1 Refinos

**Salto de cota: piso de 0,1 % e dia de mercado** (decidido em 26/09/2026).

- Por que 60 retornos: cerca de três meses de pregões, o bastante para estimar o desvio e ainda acompanhar mudança de regime.
- Por que 5 desvios-padrão: é raro o bastante para não disparar toda semana num fundo normal.
- Por que `k`: quando falta informe, o retorno seguinte cobre vários dias. Compará-lo com a média de um dia marcaria como salto o simples acúmulo dos dias que faltaram.
- Por que o piso de 0,1 %: num fundo DI o desvio-padrão diário é de 0,001 %, e 5 desvios são centavos. O piso vale para o desvio em relação à média esperada, não para o desvio-padrão. Nesta rodada, sem o piso, 20 dos alertas seriam imateriais.
- Por que 3 % absoluto em Renda Fixa: um fundo de Renda Fixa mexer 3 % num dia é excepcional, qualquer que seja o histórico. Nesta rodada, nenhum alerta veio só por esse critério.
- **Dia de mercado pelos pares:** se pelo menos 10 % das séries da mesma classificação CVM saltaram no mesmo dia, o salto vira informativo. Um em cada dez fundos da mesma classe mexendo junto é mercado, não o fundo. A fração é medida no universo de pares (as 3.392 séries candidatas), não em todos os fundos do país, com o critério estatístico da regra (sem o absoluto de 3 %) e só entre as séries que já têm 60 retornos anteriores. Essa fração é calculada na etapa de qualidade e não é publicada; o alerta só guarda a marca `market-wide`.
- Sem esses refinos, a regra gerava 127 alertas médios, e o evento real da gestora ficava escondido no meio deles.

**Salto de cota: dia de mercado pelo índice** (decidido em 29/09/2026).

- **O problema.** Na revisão de 29/09/2026, o site dizia "queda isolada" em dias em que o mercado mexeu forte: 18/12/2024 (Ibovespa −3,15 %), 04/04/2025 (−2,96 %), 13/03/2026 (IMA-B −1,21 %), 16/03/2026 (IMA-B +1,56 %). A fração de pares é medida por classificação CVM, e o Multimercado e a Renda Fixa do universo são dominados por fundos DI: um dia forte de bolsa ou de IMA-B quase nunca chega a 10 % da classe. Na prática, a regra só reconhecia mercado em Ações.
- **A regra.** Para cada série, olha-se a correlação dos 60 retornos anteriores com o Ibovespa e com o IMA-B e fica o índice de maior correlação em módulo. O salto vira informativo quando, no mesmo dia, esse índice teve um movimento acima de 2,5 desvios-padrão do próprio padrão (60 retornos anteriores do índice), no mesmo sentido do desvio do fundo, e a correlação é de pelo menos 0,5. A fração de pares continua como segunda via, para os fundos sem índice. O alerta leva a marca `index ibov` ou `index ima_b`.
- **Em uma frase:** o salto é de mercado quando o índice que mais se parece com o fundo também saiu do padrão, no mesmo dia e no mesmo sentido.
- **Efeito na rodada de 24/09/2026:** de 72 para 56 saltos médios, de 35 para 51 informativos. Os 16 que mudaram: 18/12/2024 (7 séries: Data Alvo 2050 e 2060 e os cinco Igaraté, com o Ibovespa a −3,30σ), 04/04/2025 (os cinco Igaraté, −2,96σ), 13/03/2026 (IPCA Dinâmico e Iporã PG Inflação, IMA-B a −4,86σ) e 16/03/2026 (Inflação Longa e Inflação Longa FIC, IMA-B a +5,12σ, correlação 0,997).
- **O que não mudou, de propósito.** O evento de crédito de 09/12/2024 continua médio nas 13 séries: nesse dia o Ibovespa subiu 1,00 % (+1,32σ) e o IMA-B caiu 0,24 % (−0,65σ), e os fundos de crédito têm correlação baixa com os dois. O 05/12/2025 continua informativo.
- **Por que 2,5σ e não 3σ.** Com 3σ, o 04/04/2025 ficaria de fora por 0,04σ (o Ibovespa caiu 2,96σ). Com 2σ o resultado é o mesmo de 2,5σ. O índice é uma condição de confirmação: o fundo já teve um desvio de 5σ, e o índice só precisa ter tido um dia incomum (2,5σ é cerca de um dia em 80). É uma calibração feita olhando os dados desta janela, e está dita como tal.
- **Por que correlação de 0,5.** Com 0,3, o Veículo Especial no Exterior 2 (correlação de 0,34 com o Ibovespa) passaria a ter o 09/04/2025 explicado pelo Ibovespa, quando o que mexeu foi a bolsa americana.
- **Alternativas descartadas.** Aplicar o teste ao resíduo contra o índice (`r − β × r_índice`) piorou: 103 saltos médios, porque em fundo com correlação alta o desvio do resíduo fica minúsculo e surgem alertas novos. Medir a fração de pares por classificação ANBIMA não mudou a contagem (72) e transformava o 09/12/2024 do Crédito Privado em informativo, porque o grupo ANBIMA dele tem 16 pares.
- **Desvio robusto, testado e descartado.** O desvio-padrão móvel inclui os saltos anteriores, então um salto grande esconde os seguintes por três meses. Trocar média e desvio por mediana e MAD (desvio absoluto mediano × 1,4826) levaria a regra de 107 para 322 disparos: o retorno diário dos fundos de crédito é muito concentrado e a MAD fica minúscula. Ficou a média e o desvio-padrão.

**Classe sem subclasse operacional** (28/09/2026): monitorada como a própria classe (ver 3.5).

**Dia de referência com 90 % das séries** (28/09/2026): ver 4.1.

### 5.2 Exemplos reais

- **Evento de crédito da casa, 09/12/2024.** 13 séries de crédito da gestora caíram no mesmo dia, entre −0,11 % e −0,53 %, em fundos cujo retorno médio nos 60 dias anteriores era de +0,04 % ao dia. São 10 CNPJs: três classes (`07900255000150`, `35609382000130` e `44917374000141`) ainda não tinham subclasses, e a cota de cada uma aparece nas duas subclasses que a herdam. Na mesma data, só 2,3 % dos fundos de Renda Fixa do universo de pares saltaram. Não foi mercado: foi algo comum às carteiras da gestora, provavelmente a remarcação de um mesmo emissor. Ficou como alerta médio. Séries: `05755769000133`, `07900255000150-BQMVJ1750171627`, `07900255000150-FR33D1750172064`, `32760042000117`, `32760072000123`, `34081211000118`, `35609382000130-A8AAW1750173152`, `35609382000130-ZN9EI1750172960`, `36521750000156`, `44917374000141-UYXKV1750167974`, `44917374000141-WJPUK1750168728`, `45444067000153`, `48953198000154`.
- **Dia de mercado, 05/12/2025.** 72 % dos fundos de ações, 32 % dos multimercados e 16 % dos de renda fixa do universo de pares tiveram salto. O Dividendos (`08279304000141-9WCV01767643284`) caiu −4,53 % e o IBX (`06224719000192`) −4,29 %. Os 24 alertas do dia ficaram informativos. Em 13/03/2026, 12 % da renda fixa saltou e o IMA-B caiu 4,86σ: os 13 alertas do dia ficaram informativos (os dois últimos, IPCA Dinâmico e Iporã PG Inflação, pela regra do índice).
- **Dia de mercado que a regra antiga não via, 18/12/2024.** Ibovespa −3,15 %. Sete séries de multimercado e ações ligadas à bolsa apareciam como queda isolada; pela regra do índice (5.1), viraram informativas. O caso completo está em `findings.md`, item 13.
- **Distribuição informada como resgate: `54023112000197`** (Incentivado em Infraestrutura, 1 cotista, R$ 49,4 mi). O informe traz resgate de cerca de R$ 505 mil todo mês, cerca de 1 % do PL, mas o PL não cai esse valor. O resíduo fica entre +0,97 % e +1,03 % em todos os 24 meses; 11 passam do limite. Leitura provável, **a confirmar**: pagamento de rendimentos que sai da cota e aparece como resgate. O alerta de PL é legítimo.
- **Duplicidade de 24/04/2025.** Duas classes, `07900255000150` e `44917374000141`, ainda sem subclasses, têm cota, PL e resgates diferentes entre a linha `FI` e a `CLASSES - FIF`. Cada linha aparece como alerta nas duas subclasses que herdam a cota: `07900255000150-BQMVJ1750171627`, `07900255000150-FR33D1750172064`, `44917374000141-UYXKV1750167974` e `44917374000141-WJPUK1750168728`. Fora das monitoradas, o CNPJ `03537494000136` em 06/11/2024 tem captação de R$ 9.082,08 numa linha e R$ 64.743,05 na outra.
- **Linha zerada de 16/03/2026.** `34793170000192-BNAX91750170440` informou cota 0, PL 0 e 0 cotistas, no meio de uma série com cerca de 1.470 cotistas e R$ 119 mi. A linha sai de todo o cálculo e gera dois alertas: valores zerados (alta) e o dia sem informe que ela deixa (baixa).
- **Subclasse que não herda.** `58327943000103-NANFG1779473395`, pela regra dos 7 dias (ver 4.1).
- **Fonte atrasada, 27/09/2026.** Com o portal da CVM fora do ar, a última data do informe estava em 22/09/2026: 3 dias de semana de atraso (23, 24 e 25/09) contra a tolerância de 2. Foi numa execução local, não publicada. Na rodada de 28/09/2026, com o portal de volta, não há alerta.

### 5.3 Tratativas

Um alerta tem estado, como no log de operações de uma mesa: fica **aberto** até alguém ler e concluir; depois fica **tratado**, com o motivo. Tratar não altera dado nenhum: o alerta continua na lista, o cálculo não muda e a exclusão de linhas segue só as exceções do princípio acima. A tratativa registra a leitura.

- **Três desfechos.** `explained`: o dado está certo e o movimento tem explicação (evento de crédito, remarcação). `source_error`: a fonte publicou errado (linha zerada, duplicidade). `limitation`: o dado é o que a fonte dá, mas a regra ou o informe não conseguem representá-lo (distribuição informada como resgate, cota sem ajuste por evento).
- **O arquivo.** `data/triage.json`, editado à mão e versionado no Git, fora do que a Action grava (ela só adiciona `data/parquet` e `data/site`). Cada entrada diz a regra, a série (ou nenhuma, para valer para todas), o período (`date_from` a `date_to`, inclusivo), o desfecho, uma nota de uma ou duas frases e o dia da tratativa. Regra desconhecida, período invertido ou campo a mais param a publicação com erro.
- **Casamento.** A entrada vale para os alertas da mesma regra e da mesma série (ou de qualquer série, se a entrada não tem série) cuja data cai no período; nas regras com período (dia sem informe, PL sem explicação, cota repetida, fonte atrasada, cadastro), basta sobrepor. Se mais de uma entrada casa, vale a que tem série; no empate, a de tratativa mais recente. Um alerta sem data (série do cadastro que nunca informou) não casa com nenhuma entrada. A entrada vale para as rodadas seguintes: um alerta novo da mesma regra, série e período já nasce tratado.
- **Informativo não é aberto.** O alerta `info` (dia de mercado, histórico curto) já é explicado pela própria regra. Ele pode receber tratativa, mas as contagens de abertos, do site e de cada fundo, só olham alta, média e baixa.
- **Eventos.** Saltos de cota de 3 ou mais séries na mesma data viram um evento na página Qualidade, com a severidade mais alta do grupo, o número de CNPJs distintos e o estado comum às séries com alerta alto, médio ou baixo (se uma estiver aberta, o evento está aberto; os informativos não contam, porque não se tratam). Um evento se trata com uma entrada sem série para a data.

Tratativas registradas em 29/09/2026, depois de ler um por um os alertas abertos. Critério: só se trata o que tem leitura com evidência; o resto fica aberto.

| Regra | Série | Período | Desfecho | Alertas |
| --- | --- | --- | --- | --- |
| Salto de cota | todas | 09/12/2024 | `explained`: evento de crédito da casa (5.2) | 13 |
| Salto de cota | `55298739000113` (Veículo Especial no Exterior 2) | 13/03 a 09/04/2025 e 10/10/2025 | `explained`: o S&P 500 mexeu no mesmo dia e no mesmo sentido (FRED `SP500`; ρ 0,65 com o fundo) | 9 |
| Salto de cota | `44212682000171` (FOF Ações Globais USD) | 03/04 a 09/04/2025 | `explained`: S&P 500 −4,84 % e +9,52 % | 2 |
| Salto de cota | `54023112000197` e `53248945000193` (incentivados) | 4 datas | `limitation`: queda de cerca de 1 % da cota no dia do pagamento mensal, provável distribuição de rendimentos, a confirmar com a lâmina | 4 |
| PL sem explicação | `54023112000197` | 01/09/2024 a 30/09/2026 | `limitation`: distribuição informada como resgate (5.2 e 7) | 11 |
| PL sem explicação | `19719727000151` (Inflação) | nov e dez/2024 | `limitation`: resgate de R$ 19,1 mi informado em 29/11 e baixa do PL em 06/12; os resíduos se anulam | 2 |
| PL sem explicação | 6 séries com fluxo grande no mês | um mês cada | `limitation`: dia a dia o resíduo é zero; é a decomposição mensal, que supõe o fluxo no fim do mês (7) | 6 |
| Valores zerados | `34793170000192-BNAX91750170440` | 16/03/2026 | `source_error`: linha zerada da CVM | 1 |
| Dia sem informe | `34793170000192-BNAX91750170440` | 16/03/2026 | `source_error`: consequência da linha zerada | 1 |
| Informe duplicado | todas | 24/04/2025 | `source_error`: `FI` e `CLASSES - FIF` com valores diferentes | 4 |

Na rodada de 24/09/2026 são 53 alertas tratados dos 148 (24 explicados, 6 erros da fonte, 23 limitações) e 65 informativos. Ficam **30 abertos, todos médios**: 28 saltos de cota e 2 PL sem explicação (FOF Global BRL em mar/2025 e Credit Plus K em set/2026). Entre os abertos há três dias com várias séries de crédito da casa caindo juntas, como no 09/12/2024: 18 e 19/03/2026 e 13/08/2026. Ficam abertos, a investigar com a carteira. Só 4 dos 30 abertos são dos últimos 30 dias.

**Taxa de acerto das regras** (a resposta para "como você sabe que o limiar está certo?"):

| Regra | Alertas | Fato real ou erro da fonte | Mercado | Limitação do informe ou da regra | Sem leitura |
| --- | --- | --- | --- | --- | --- |
| Salto de cota | 107 | 13 (evento de crédito) | 62 (51 pela regra, 11 por mercado global) | 4 (incentivados) | 28 |
| PL sem explicação | 21 | 0 | — | 19 | 2 |
| Valores zerados, dia sem informe, informe duplicado | 6 | 6 | — | 0 | 0 |

Dos 56 saltos médios, metade tem leitura. A regra de PL quase só pega limitação da própria fórmula (fluxo no meio do mês, distribuição como resgate): é o sinal de que a decomposição diária (`PRODUCTION.md`) vale mais que ajustar o limiar de 1 %.

## 6. O que cada gráfico e tabela mostra

Regras que valem para todas as telas:

- **Um eixo por gráfico.** Fundo e benchmark ficam na mesma unidade (retorno acumulado com base 100), para a comparação ser direta.
- **Cor por papel, com paleta curta.** São cinco cores de série, reaproveitadas entre papéis. O que é fixo: cada benchmark tem sempre a mesma cor (CDI, IMA-B, Ibovespa), cada classificação também (Renda Fixa, Multimercado, Ações), e o fundo tem a mesma cor no retorno acumulado e no ponto da faixa de pares. O que não é: a mesma cor serve a papéis diferentes. O CDI tem a cor da entrada líquida, o IMA-B a de Renda Fixa, o Ibovespa a de Ações, o fundo a de Multimercado, e o drawdown do fundo usa a cor da saída líquida. A legenda de cada gráfico é que diz o que a cor é.
- **Os gráficos de linha e de barras verticais têm tabela e tooltip.** O botão "Ver tabela" troca o gráfico pelos números, e o tooltip mostra o valor de cada ponto. Duas visualizações ficam de fora: as barras horizontais dos destaques de captação e resgate, que escrevem o valor ao lado de cada barra, sem tooltip nem tabela; e as faixas de pares da página do fundo, que mostram fundo, mediana e percentil ao lado da faixa e repetem tudo no texto que aparece ao passar o mouse, sem botão de tabela.
- Números com algarismos de largura fixa. Percentuais e razões têm sempre 2 casas. Dinheiro na tabela de fundos, nos tiles e nos destaques aparece em forma compacta, com até uma casa e a escala que couber (R$ 450 mi, R$ 6,5 bi); na tabela de fundos e nos tiles, o valor completo aparece ao passar o mouse. As tabelas dos gráficos de captação trazem o dinheiro por extenso.
- Gráfico com menos de 2 pontos não é desenhado: aparece um aviso explicando por quê.

### 6.1 Visão geral

- **Faixa de qualidade.** "Dados até" o dia de referência, hora de geração, séries e pares série × dia útil verificados, última data de cada fonte e alertas por severidade. O cartão leva à página Qualidade. Como ler: se uma fonte está atrasada, os números dependentes dela são de antes.
- **Destaques.** Não seguem os filtros da página.
  - Contra o próprio benchmark em 12 meses: quantas séries de Público Geral (sem veículos estruturais) bateram o benchmark principal (4.5), com fundo, benchmark e excesso em p.p. Na rodada de 24/09/2026, 6 de 36. Numa linha pequena, a leitura contra o CDI (5 de 36).
  - Maiores captações e maiores resgates em 12 meses, no mesmo recorte, cada barra com link para o fundo. Séries com menos de 12 meses entram, com `*` de janela parcial.
  - Evento de crédito: o dia, na janela inteira (desde 01/09/2024), com mais quedas isoladas, isto é, alertas médios de salto de cota com retorno negativo e fora de dia de mercado, desde que em pelo menos 3 CNPJs distintos. Na rodada de 24/09/2026 é 09/12/2024. O cartão mostra os fundos (CNPJs distintos) e, entre parênteses, as séries: "10 fundos (13 séries)", porque as subclasses que herdam a mesma cota repetem a queda (ver 5.2).
  - Fundos incentivados: aviso de que o retorno pela cota provavelmente está subestimado, com o retorno e a posição entre pares de cada série de Público Geral com "incentivad" no nome e retorno de 12 meses (ver 7).
- **Frase de resumo, no topo.** PL e captação de 12 meses das classes não exclusivas sem veículos estruturais, quantas séries de Público Geral bateram o próprio benchmark e quantos alertas estão abertos. Na rodada de 24/09/2026: R$ 14,8 bi, R$ 1,9 bi, 6 de 36 e 30. Não segue os filtros. O selo de abertos só fica colorido quando há alerta alto aberto.
- **Filtros.** Público (padrão Público Geral), classificação CVM e "Incluir veículos estruturais" (desligado). Mudam os tiles "Dos fundos exibidos" e a tabela. Os filtros e o "Incluir exclusivos" são mantidos ao voltar para a página.
- **Tiles "Dos fundos exibidos".** PL e captação líquida em 12 meses, somados das séries visíveis. O texto de apoio diz quantas séries têm captação com janela parcial.
- **Tiles "Da gestora".** PL e captação em 12 meses de todas as classes do escopo, de todos os públicos: por padrão, as 58 classes não exclusivas sem veículos estruturais (R$ 14,8 bi e R$ 1,9 bi na rodada de 24/09/2026). "Incluir veículos estruturais" passa para as 69 classes não exclusivas (R$ 27,1 bi e R$ 9,2 bi); "Incluir exclusivos", para as 246 classes (R$ 93,3 bi). Não seguem os filtros de público e classificação. A diferença para "Dos fundos exibidos" é o recorte: lá é a soma das séries visíveis na tabela.
- **Captação líquida mensal por classificação.** Barras agrupadas por mês, uma por classificação CVM, nos últimos 12 meses. Barra abaixo de zero é saída líquida. O último mês é parcial até o dia de referência. Segue "Incluir exclusivos" e "Incluir veículos estruturais". Sem os estruturais, o pico de jan/2026 do Veículo Especial Bancário (`64203379000110`) sai do gráfico.
- **Tabela de fundos.** Uma linha por série, ordenada por PL. Classificação CVM; retorno, % do CDI, volatilidade, drawdown e Sharpe de 12 meses (traço em série "DI de um dia", com o motivo ao passar o mouse, ver 4.3); PL; captação em 12 meses (`*` = janela parcial); cotistas; excesso de 12 meses sobre o benchmark principal, em p.p., com o nome do benchmark; posição entre pares ("P71 ret · P2 vol · 358": percentil do retorno, da volatilidade e número de pares); alertas altos e médios. No celular, cada fundo vira um cartão com retorno, % do CDI, PL e uma linha com o excesso, os pares e os alertas. Classificação ANBIMA e público são colunas escondidas que podem ser ligadas. O nome leva à página do fundo. O nome exibido é o da subclasse ou da classe sem o prefixo da gestora e o sufixo jurídico; nomes iguais ganham um qualificador (FIFE, FIC, IU) e, se ainda se repetem, um número.

### 6.2 Página do fundo

- **Cadastro.** CNPJ da classe, ID da subclasse, classificações, público, condomínio, indicador de desempenho declarado, benchmarks usados na comparação, primeira cota na janela (desde 01/09/2024) e última cota. Quando há herança, diz até que dia a cota veio da classe.
- **Tiles.** PL (com data e cotistas), captação em 12 meses, retorno em 12 meses (com o excesso sobre o benchmark principal e o % do CDI), volatilidade, Sharpe (em série "DI de um dia", um traço com o motivo, ver 4.3), drawdown máximo (com pico, vale e recuperação), posição entre pares. Beta e tracking error só aparecem quando a série tem benchmark de mercado. Quando um número falta, o tile diz por quê ("menos de 12 meses de série", "menos de 60 observações").
- **Retorno acumulado contra o benchmark.** Linhas com base 100 no início da janela de 24 meses, ou na primeira cota se a série é mais curta: o fundo e os benchmarks da série. Como ler: a distância entre as linhas no fim é a diferença de retorno acumulado. A tabela traz o valor no fim de cada mês.
- **Janelas de retorno.** Uma linha por janela: período e dias úteis, retorno do fundo, CDI, % do CDI (em todas as janelas), benchmark de mercado, excesso sobre o CDI e sobre o benchmark de mercado em p.p. e retorno anualizado (24 meses e "desde o início" com pelo menos 252 dias úteis; não na janela de 12 meses, ver 4.2).
- **Drawdown.** Área abaixo de zero no período do gráfico de 24 meses: quanto a cota está abaixo da sua máxima desde o início do gráfico. Zero é estar na máxima. Se a cota nunca caiu, aparece um aviso no lugar do gráfico. A tabela traz, para 12 e 24 meses, o drawdown máximo, pico, vale, recuperação, melhor e pior dia, dias positivos e observações.
- **Captação líquida mensal.** Uma barra por mês, com cor de entrada ou de saída pelo sinal. A tabela traz captação, resgate, líquido, PL no fim do mês, cotistas, retorno no mês e resíduo do PL, destacado quando passa de 1 % em módulo.
- **Posição entre pares.** Para retorno, volatilidade e drawdown de 12 meses: uma faixa com o intervalo P25 a P75 dos pares, um traço na mediana e um ponto no fundo. Ao lado, o valor do fundo, a mediana e o percentil, com uma frase de leitura ("X % dos pares renderam menos"). Sem grupo de pares, o card e o tile dizem o motivo: "só para Público Geral", "menos de 12 meses de série" ou "menos de 5 pares na classificação". Uma série parada há mais de 7 dias (4.2) também cai no último texto, embora o motivo real seja a cota antiga; hoje nenhuma série está parada.
- **Alertas de qualidade.** Lista dos alertas da série, com severidade, regra, data e uma frase montada a partir dos campos do alerta.

### 6.3 Qualidade

- **Situação de cada alerta.** Alertas marcam, não excluem, e tratar um alerta não altera o dado. Cada alerta tem uma situação: aberto (ainda precisa de leitura), explicado, erro da fonte ou limitação do informe. Alerta informativo nunca conta como aberto.
- **Tiles de abertos por severidade** (alta, média, baixa), um tile **Tratados** com a divisão por situação e, abaixo, a contagem de informativos. Em seguida a tabela **Alertas por regra**, com as nove regras, o que cada uma detecta, o limiar, a severidade típica e o número de alertas, zero inclusive.
- **Lista de alertas** do universo monitorado, filtrável por situação (Abertos, o padrão; Tratados; Informativos; Todos), regra e fundo, e com busca livre no texto do alerta, na nota, no nome e no CNPJ da série. Os filtros são mantidos ao voltar para a página. A lista abre com os abertos primeiro, depois por severidade e data mais recente. A coluna "Situação" mostra a nota e a data do tratamento ao passar o mouse; no celular a nota aparece no cartão. A coluna "Valor / limiar" mostra, no salto de cota, o desvio em relação à média esperada ao lado do limite que disparou ("desvio −1,09 % / limite ±1,04 % (5σ)"), com o retorno do dia embaixo; no critério absoluto de Renda Fixa, o retorno e o limite de 3 %. No PL sem explicação, o resíduo e o limite. No celular a mesma linha aparece no cartão. A frase do alerta diz o motivo: isolado, dia de mercado pelo índice ou dia de mercado pelos pares.
- **Eventos**, entre os filtros e a lista: um cartão por dia com salto de cota em 3 ou mais séries, com a data, séries e CNPJs, severidade, situação, nota e as séries com link. Seguem os mesmos filtros. O evento informativo aparece como "Dia de mercado", só em Informativos e Todos.
- O fundo tem link para a página dele quando a série é monitorada. Os alertas de fonte atrasada (regra 8) não têm série e mostram um traço; um alerta de cadastro de série que não está entre as monitoradas mostra o identificador sem link.

### 6.4 Como funciona

Uma página curta que serve de roteiro da apresentação: o problema, as fontes e o universo, o fluxo, os cálculos principais, a qualidade com a taxa de acerto das regras, três achados, as limitações que importam e como seria em produção. Os números vivos vêm do JSON; o detalhe está neste documento, em `findings.md` e em `PRODUCTION.md`, com link no fim da página.

## 7. Limitações conhecidas

- **Cota não ajustada por evento.** O informe traz a cota depois de amortizações e distribuições, sem dizer que houve evento. O retorno pela cota subestima o que o cotista recebeu. Os fundos incentivados de infraestrutura, que pagam rendimentos, aparecem no fim da fila: `54023112000197` com −4,36 % em 12 meses e percentil 4 % entre 359 pares; `34793170000192-BNAX91750170440`, `34793170000192-D36IH1750170657` e `53248945000193` com percentil zero. Parte disso é provavelmente esse efeito; **a confirmar** com a lâmina. Quando a distribuição sai como resgate, a regra 4 também dispara.
- **Pares por classificação ANBIMA não separam incentivados.** Um fundo incentivado, isento de IR para a pessoa física, compete com fundos de crédito comuns da mesma classificação. A comparação é antes do IR do cotista, o que tira a vantagem do incentivado.
- **Decomposição mensal do PL supõe fluxo no fim do mês.** Com fluxo grande perto do PL, o resíduo infla. Exemplo: `54198519000155-TY3I61766775472` (Igaraté Long Biased IBOV) em fev/2026. O PL passou de R$ 1,8 mi para R$ 42,5 mi com aplicação de R$ 39,9 mi, e o resíduo deu 44 % do PL inicial. Trocar a base para o maior PL não resolve (ainda dá 1,9 %). Decidido em 28/09/2026: a regra fica como está; a decomposição diária está em `PRODUCTION.md`.
- **Benchmark por classificação, não por regulamento.** Um fundo que declara IPCA, IMA-B 5 ou IRF-M é comparado com o IMA-B: o Pré-Fixado declara IRF-M (coletado, mas não usado) e a Inflação Curta, de duração média, seria mais bem comparada com o IMA-B 5. O Iporã PG Inflação é Multimercado e é comparado com o CDI; os Igaraté Long Biased da classe Ações, com o Ibovespa, embora um long biased raramente persiga o índice. Fundo de crédito de Renda Fixa que não declara "DI de um dia" (por exemplo, "Não se aplica") ainda recebe beta contra o IMA-B. Só o IBrX foi resolvido (4.5).
- **IMA-B pelo download diário público da ANBIMA.** Um POST por dia, sem contrato nem API. Se a ANBIMA mudar o formulário, a coleta quebra. Os outros IMAs são coletados e não usados.
- **Pares só para Público Geral e PL acima de R$ 50 milhões.** Séries de Profissional e Qualificado não têm posição entre pares. O grupo inclui outros fundos da própria gestora com CNPJ diferente (30 séries da gestora são pares elegíveis).
- **Viés de sobrevivência nos pares, e FIC e master como pares distintos** (4.6).
- **Dia de mercado sem índice global.** A regra 2 reconhece mercado pelo Ibovespa, pelo IMA-B e pela fração de pares da mesma classificação. Fundos no exterior (FOF Ações Globais USD, Veículo Especial no Exterior 2) não têm índice coletado: os dias de mercado global deles viram tratativa à mão (5.3). A fração de pares é calculada nas 3.392 séries candidatas, não em todos os fundos do país.
- **Alertas de linhas herdadas contam por subclasse.** Antes da divisão de uma classe, o mesmo fato aparece em cada subclasse que herda a cota (ver 5).
- **Transição com subclasses que discordam.** A classe some do monitor sem alerta (ver 3.5).
- **Sem IR e sem come-cotas.** Os retornos são líquidos de taxa de administração e brutos de imposto do cotista.
- **Sem carteira.** O monitor não mostra exposição por emissor nem por setor. O evento de 09/12/2024 é inferido pela cota, não confirmado pela carteira.
- **Volatilidade supõe retornos independentes.** Em fundo de crédito com marcação suave, os retornos diários se parecem de um dia para o outro, e `√252` subestima o risco.
- **Ibovespa como publicado.** São os pontos de fechamento da B3, sem outro ajuste, e o dia corrente é descartado.
- **Veículo estrutural por nome.** É uma regra sobre o nome da classe, não um campo do cadastro.
- **Cadastro é a foto do dia.** Classificação, público e exclusividade de hoje valem para os 24 meses de histórico.
- **Janela fixa desde 01/09/2024.** "Desde o início" é desde o início da coleta, não da criação do fundo.
- **Fonte atrasada conta dias de semana, sem feriados.** Depois de um feriado, o atraso pode aparecer um dia maior do que é.

## Apêndice: constantes

Os limiares do cálculo e da qualidade são constantes com nome em `pipeline/src/fund_monitor/`; mudar um limiar é mudar uma linha e um teste.

| Constante | Valor | Onde | Uso |
| --- | --- | --- | --- |
| `WINDOW_START` | 01/09/2024 | `config.py` | Início da coleta |
| `COMPLETE_DAY_SHARE` | 90 % | `calc/series.py` | Dia de referência (4.1) |
| `MAX_HANDOFF_GAP` | 7 dias | `calc/series.py` | Herança de cota da subclasse (4.1) |
| `MAX_QUOTA_STALENESS` | 7 dias | `calc/returns.py` | Série parada (4.2) |
| `TRADING_DAYS_PER_YEAR` | 252 | `calc/returns.py` | Anualização |
| `MIN_OBSERVATIONS` | 60 | `calc/risk.py` | Mínimo para vol, Sharpe, beta e tracking error |
| `MIN_PEER_NET_ASSETS` | R$ 50 mi | `calc/peers.py` | Elegibilidade de par |
| `MIN_PEERS` | 5 | `calc/peers.py` | Mínimo para publicar posição |
| `JUMP_LOOKBACK`, `JUMP_SIGMAS` | 60, 5 | `quality/checks.py` | Salto de cota (regra 2) |
| `MATERIAL_DEVIATION` | 0,1 % | `quality/checks.py` | Piso do salto |
| `FIXED_INCOME_JUMP` | 3 % | `quality/checks.py` | Salto absoluto em Renda Fixa |
| `MARKET_JUMP_SHARE` | 10 % | `quality/checks.py` | Dia de mercado pelos pares |
| `INDEX_MOVE_SIGMAS`, `MIN_INDEX_CORRELATION` | 2,5, 0,5 | `quality/checks.py` | Dia de mercado pelo índice |
| `LONG_GAP_DAYS` | 5 | `quality/checks.py` | Dia sem informe médio |
| `REPEATED_QUOTA_DAYS` | 3 | `quality/checks.py` | Cota repetida |
| `UNEXPLAINED_SHARE` | 1 % | `quality/checks.py` | PL sem explicação |
| `SOURCE_TOLERANCE_WEEKDAYS` | CVM 2; CDI, IMA-B, Ibovespa e IBrX-100 1 | `quality/checks.py` | Fonte atrasada |

Alguns limiares de exibição ficam só no site, em `web/src/`: o destaque do resíduo do PL na tabela de captação (`RESIDUAL_LIMIT`, 1 %, em `MonthlyFlowCard.svelte`, separado de `UNEXPLAINED_SHARE` da regra 4), os 12 meses do gráfico de captação da visão geral (`CHART_MONTHS` em `routes/+page.svelte`), o mínimo de 3 CNPJs do destaque de evento de crédito (`EVENT_MIN_CNPJS` em `highlights.ts`) e uma cópia do mínimo de 5 pares (`MIN_PEERS` em `fund.ts`). Mudar a constante do pipeline não muda a do site.
